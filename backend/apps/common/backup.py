"""
Backup and restore of FirmFlow data (Phase C).

A backup is one file: <BACKUP_DIR>/firmflow-YYYYMMDD-HHMMSS.tar.gz with
  manifest.json          time, database type, applied migrations, row counts
  database.sqlite3       (SQLite)  or  database.pgdump  (PostgreSQL, pg_dump custom format)
  private_media/...      task attachments
  media/...              firm logo
NOT in the backup: PAN_ENCRYPTION_KEY and SECRET_KEY. Keep a copy of the .env file in a safe place;
PAN numbers in a backup cannot be read without the same PAN_ENCRYPTION_KEY.

Commands:
  python manage.py backup_firmflow [--dir DIR] [--keep 14]
  python manage.py restore_firmflow FILE --verify      (checks the file, changes nothing)
  python manage.py restore_firmflow FILE --yes         (replaces the data; stop the web server and workers first)
Every step writes a structured log line "backup.*" / "restore.*".
"""
import io
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import connection, connections
from django.db.migrations.recorder import MigrationRecorder

from apps.common.logging import log_event

COUNT_TABLES = ['accounts_firm', 'accounts_user', 'clients_client', 'tasks_task', 'tasks_taskattachment', 'common_auditlog']


class BackupError(Exception):
    pass


def _db():
    return settings.DATABASES['default']


def _vendor():
    return connection.vendor     # 'sqlite' or 'postgresql'


def _pg_env():
    env = dict(os.environ)
    if _db().get('PASSWORD'):
        env['PGPASSWORD'] = str(_db()['PASSWORD'])
    return env


def _pg_args():
    d = _db()
    args = ['-d', d['NAME']]
    if d.get('HOST'):
        args += ['-h', d['HOST']]
    if d.get('PORT'):
        args += ['-p', str(d['PORT'])]
    if d.get('USER'):
        args += ['-U', d['USER']]
    return args


def _need(binary):
    path = shutil.which(binary)
    if not path:
        raise BackupError(f'"{binary}" is not installed on this server. Install the PostgreSQL client tools '
                          f'(same major version as the server) and try again.')
    return path


def _row_counts():
    out = {}
    with connection.cursor() as cur:
        for t in COUNT_TABLES:
            try:
                cur.execute(f'SELECT COUNT(*) FROM {t}')   # fixed table names, not user input
                out[t] = cur.fetchone()[0]
            except Exception:
                out[t] = None
    return out


def _applied_migrations():
    return sorted(f'{a}.{n}' for a, n in MigrationRecorder(connection).applied_migrations())


def _add_dir(tar, src: Path, arcname: str):
    if src.exists():
        tar.add(str(src), arcname=arcname)


def create_backup(target_dir=None, keep=None) -> Path:
    started = time.monotonic()
    target = Path(target_dir or settings.BACKUP_DIR)
    target.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    final = target / f'firmflow-{stamp}.tar.gz'
    vendor = _vendor()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        if vendor == 'sqlite':
            db_file = tmp / 'database.sqlite3'
            if connection.in_atomic_block:
                # SQLite cannot copy a database that has uncommitted changes on the same connection (it waits for ever)
                raise BackupError('Run the backup outside a database transaction.')
            dest = sqlite3.connect(str(db_file))
            connection.ensure_connection()
            connection.connection.backup(dest)       # consistent copy while the app runs
            dest.close()
            db_name = 'database.sqlite3'
        elif vendor == 'postgresql':
            db_file = tmp / 'database.pgdump'
            res = subprocess.run([_need('pg_dump'), '-Fc', '--no-owner', '-f', str(db_file)] + _pg_args(),
                                 env=_pg_env(), capture_output=True, text=True, timeout=3600)
            if res.returncode != 0:
                raise BackupError(f'pg_dump failed: {res.stderr.strip()[:500]}')
            db_name = 'database.pgdump'
        else:
            raise BackupError(f'Database type "{vendor}" is not supported.')
        manifest = {
            'format': 1, 'created_at': datetime.now().astimezone().isoformat(), 'database': vendor,
            'database_file': db_name, 'migrations': _applied_migrations(), 'row_counts': _row_counts(),
            'note': 'PAN_ENCRYPTION_KEY is not in this file. Keep the .env file safe.',
        }
        partial = target / f'.firmflow-{stamp}.tar.gz.partial'
        with tarfile.open(partial, 'w:gz') as tar:
            data = json.dumps(manifest, indent=2).encode()
            info = tarfile.TarInfo('manifest.json'); info.size = len(data); info.mtime = int(time.time())
            tar.addfile(info, io.BytesIO(data))
            tar.add(str(db_file), arcname=db_name)
            _add_dir(tar, Path(settings.PRIVATE_MEDIA_ROOT), 'private_media')
            _add_dir(tar, Path(settings.MEDIA_ROOT), 'media')
        partial.rename(final)       # a half-written file never looks like a good backup
    removed = prune(target, keep if keep is not None else settings.BACKUP_KEEP)
    log_event('backup.create', 'System', final.name, duration_ms=round((time.monotonic() - started) * 1000, 1),
              database=vendor, size_bytes=final.stat().st_size, removed_old=removed, rows=manifest['row_counts'])
    return final


def prune(target: Path, keep: int) -> int:
    files = sorted(target.glob('firmflow-*.tar.gz'))
    old = files[:-keep] if keep and len(files) > keep else []
    for f in old:
        f.unlink()
    return len(old)


def _safe_extract(tar: tarfile.TarFile, dest: Path):
    root = dest.resolve()
    for m in tar.getmembers():
        p = (dest / m.name).resolve()
        if not str(p).startswith(str(root)) or m.issym() or m.islnk():
            raise BackupError(f'Unsafe path in backup file: {m.name}')
    tar.extractall(dest)


def read_backup(path, workdir: Path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise BackupError(f'File not found: {path}')
    with tarfile.open(path, 'r:gz') as tar:
        _safe_extract(tar, workdir)
    mf = workdir / 'manifest.json'
    if not mf.exists():
        raise BackupError('This is not a FirmFlow backup (no manifest.json).')
    manifest = json.loads(mf.read_text())
    if not (workdir / manifest['database_file']).exists():
        raise BackupError('The database file is missing from the backup.')
    return manifest


def _check_migrations(manifest) -> list:
    """Backups made by a NEWER app version cannot be restored into this code."""
    from django.db.migrations.loader import MigrationLoader
    loader = MigrationLoader(None, ignore_no_migrations=True)
    known = {f'{a}.{n}' for a, n in loader.disk_migrations.keys()}
    return sorted(set(manifest.get('migrations', [])) - known)


def verify_backup(path) -> dict:
    """Restore drill without touching live data: open the backup and count rows."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        manifest = read_backup(path, tmp)
        unknown = _check_migrations(manifest)
        result = {'file': str(path), 'database': manifest['database'], 'created_at': manifest['created_at'],
                  'expected_rows': manifest['row_counts'], 'unknown_migrations': unknown,
                  'attachments': sum(1 for p in (tmp / 'private_media').rglob('*') if p.is_file()) if (tmp / 'private_media').exists() else 0}
        if manifest['database'] == 'sqlite':
            con = sqlite3.connect(str(tmp / manifest['database_file']))
            result['integrity'] = con.execute('PRAGMA integrity_check').fetchone()[0]
            found = {}
            for t in COUNT_TABLES:
                try:
                    found[t] = con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                except sqlite3.Error:
                    found[t] = None
            con.close()
            result['found_rows'] = found
            result['ok'] = result['integrity'] == 'ok' and found == manifest['row_counts'] and not unknown
        else:
            res = subprocess.run([_need('pg_restore'), '--list', str(tmp / manifest['database_file'])],
                                 capture_output=True, text=True, timeout=600)
            result['archive_entries'] = len([l for l in res.stdout.splitlines() if l and not l.startswith(';')])
            result['ok'] = res.returncode == 0 and result['archive_entries'] > 0 and not unknown
            if res.returncode != 0:
                result['error'] = res.stderr.strip()[:500]
    log_event('restore.verify', 'System', Path(path).name, result='ok' if result['ok'] else 'error',
              level='INFO' if result['ok'] else 'ERROR', **{k: v for k, v in result.items() if k not in ('file',)})
    return result


def restore_backup(path) -> dict:
    """Replace the live database and files with the backup. A copy of the present data is kept beside it."""
    started = time.monotonic()
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        manifest = read_backup(path, tmp)
        unknown = _check_migrations(manifest)
        if unknown:
            raise BackupError('The backup is from a newer FirmFlow version (unknown migrations: '
                              + ', '.join(unknown[:5]) + '). Update the code first.')
        vendor = _vendor()
        if manifest['database'] != vendor:
            raise BackupError(f'The backup is a {manifest["database"]} database, but this server uses {vendor}.')
        kept = []
        if vendor == 'sqlite':
            live = Path(_db()['NAME'])
            connections.close_all()
            if live.exists():
                safety = live.with_name(f'{live.name}.before-restore-{stamp}')
                shutil.copy2(live, safety)
                kept.append(str(safety))
            shutil.copy2(tmp / manifest['database_file'], live)
        else:
            res = subprocess.run([_need('pg_restore'), '--clean', '--if-exists', '--no-owner', '--single-transaction']
                                 + _pg_args() + [str(tmp / manifest['database_file'])],
                                 env=_pg_env(), capture_output=True, text=True, timeout=3600)
            if res.returncode != 0:
                raise BackupError(f'pg_restore failed (nothing was changed): {res.stderr.strip()[:500]}')
        for name, live_dir in (('private_media', Path(settings.PRIVATE_MEDIA_ROOT)), ('media', Path(settings.MEDIA_ROOT))):
            src = tmp / name
            if not src.exists():
                continue
            if live_dir.exists():
                safety = live_dir.with_name(f'{live_dir.name}.before-restore-{stamp}')
                live_dir.rename(safety)
                kept.append(str(safety))
            shutil.copytree(src, live_dir)
    connections.close_all()
    result = {'restored_from': str(path), 'database': vendor, 'kept_previous': kept,
              'rows': _row_counts(), 'duration_ms': round((time.monotonic() - started) * 1000, 1)}
    log_event('restore.apply', 'System', Path(path).name, **{k: v for k, v in result.items() if k != 'duration_ms'})
    return result
