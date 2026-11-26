# FirmFlow operations guide

## Backups

One backup = one file `firmflow-YYYYMMDD-HHMMSS.tar.gz`. It contains the database, task attachments
(`private_media`) and the firm logo (`media`), plus `manifest.json` (time, migrations, row counts).

**The backup does NOT contain `PAN_ENCRYPTION_KEY` or `SECRET_KEY`.** Keep a copy of the `.env` file in a
safe place (for example a password manager). Without the same `PAN_ENCRYPTION_KEY`, PAN numbers in a
backup cannot be read.

Make a backup (default folder `backend/backups`, keeps the newest 14):

```
cd backend && source venv/bin/activate && python manage.py backup_firmflow
cd backend && source venv/bin/activate && python manage.py backup_firmflow --dir /path/to/backups --keep 30
```

Automatic daily backup at 01:30: set `BACKUP_DAILY=true` (and `BACKUP_DIR`, `BACKUP_KEEP`) and run Celery
worker + beat. Copy the backup folder to another machine or cloud storage; a backup on the same disk does not
protect against a disk failure.

PostgreSQL needs `pg_dump` / `pg_restore` on the server (same major version as the database).

## Restore drill (do this once a month)

Check a backup without changing anything:

```
cd backend && source venv/bin/activate && python manage.py restore_firmflow backups/firmflow-YYYYMMDD-HHMMSS.tar.gz --verify
```

It must end with `Backup check OK.` For SQLite it opens the copy, runs an integrity check and compares the
row counts with the manifest. For PostgreSQL it reads the dump with `pg_restore --list`.

## Restore

1. Stop the web server, Celery worker and Celery beat.
2. Run:
   ```
   cd backend && source venv/bin/activate && python manage.py restore_firmflow backups/firmflow-YYYYMMDD-HHMMSS.tar.gz --yes
   ```
3. Run `python manage.py migrate`, then start the servers.

The present data is kept beside the new data (`db.sqlite3.before-restore-…`, `private_media.before-restore-…`,
`media.before-restore-…`). Delete them when you are sure the restore is good. A backup from a newer FirmFlow
version is refused.

## Health check

`GET /healthz` checks the database, file storage, attachment storage, Redis and SMTP. It answers 503 when a
required part fails. Redis is required only when `HEALTH_REQUIRE_REDIS=true` (default: same as
`NOTIFY_EMAIL_ASYNC`). Error details show only when `DEBUG` is on; the server log (`healthz`) always has them.

## Security settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `SECRET_KEY`, `PAN_ENCRYPTION_KEY` | — | Required when `DEBUG=False` (the server does not start with example values) |
| `SESSION_HOURS` | 12 | How long a sign-in lasts |
| `LOGIN_MAX_FAILURES` / `LOGIN_LOCKOUT_MINUTES` | 10 / 15 | Lock an e-mail after this many failures in this time |
| `LOGIN_MAX_FAILURES_PER_IP` | 50 | Same, per IP address |
| `TRUST_X_FORWARDED_FOR` | False | Turn on only behind nginx that sets this header |
| `PASSWORD_RESET_TIMEOUT_MINUTES` | 60 | Reset link lifetime |
| `SECURE_COOKIES` | on when DEBUG is off | Cookies only over HTTPS |
| `HSTS_SECONDS` | 0 | Turn on after HTTPS works for every host name |
| `USE_X_FORWARDED_PROTO` | False | Behind a proxy that ends HTTPS |

## Audit log

The audit log is append-only. The application refuses changes and deletes. On PostgreSQL, database
triggers also refuse `UPDATE` and `DELETE` from every client (migration `common.0002`).

## CI

`.github/workflows/ci.yml` runs on every push: backend tests on SQLite and PostgreSQL 16, a migration
check, the production-key check, and the frontend type-check and build.
