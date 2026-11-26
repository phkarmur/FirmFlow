"""
Task attachments (spec §3.2 TaskAttachment, §5.8).

- Type is decided from the FILE CONTENT (magic bytes), and must agree with the extension.
  A renamed .exe is refused.
- Size limit = firm.max_upload_mb (default 25 MB).
- Same file (sha256) already on the task -> 409 with a warning unless confirm_duplicate=true.
- Stored in private storage under a random name; the original name is kept only as data.
"""
import hashlib
import io
import json
import os
import re
import uuid
import zipfile
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError, APIException
from apps.common.logging import log_event
from apps.common.models import AuditLog
from apps.tasks.models import TaskAttachment
from apps.tasks import permissions as perm

# extension -> (kind detected from content, mime)
ALLOWED = {
    'pdf': ('pdf', 'application/pdf'),
    'jpg': ('jpeg', 'image/jpeg'), 'jpeg': ('jpeg', 'image/jpeg'),
    'png': ('png', 'image/png'),
    'xlsx': ('xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
    'docx': ('docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
    'zip': ('zip', 'application/zip'),
    'xls': ('ole', 'application/vnd.ms-excel'),
    'doc': ('ole', 'application/msword'),
    'csv': ('text', 'text/csv'),
    'txt': ('text', 'text/plain'),
    'json': ('json', 'application/json'),
}


class DuplicateAttachment(APIException):
    status_code = 409
    default_code = 'duplicate'


def detect_kind(data: bytes):
    """Return the content kind from magic bytes / structure, or None."""
    head = data[:8]
    if head.startswith(b'%PDF-'):
        return 'pdf'
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if head.startswith(b'\xff\xd8\xff'):
        return 'jpeg'
    if head.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
        return 'ole'                          # old Office: .xls / .doc
    if head.startswith(b'PK\x03\x04') or head.startswith(b'PK\x05\x06'):
        try:
            names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
        except zipfile.BadZipFile:
            return None
        if '[Content_Types].xml' in names and any(n.startswith('xl/') for n in names):
            return 'xlsx'
        if '[Content_Types].xml' in names and any(n.startswith('word/') for n in names):
            return 'docx'
        return 'zip'
    if b'\x00' in data[:8192]:
        return None                           # binary that we do not know
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return None
    try:
        json.loads(text)
        return 'json'
    except ValueError:
        return 'text'


def safe_name(name):
    base = os.path.basename(name or 'file').strip().replace('\x00', '')
    base = re.sub(r'[\r\n"\\\\/]+', '_', base)
    return base[:200] or 'file'


@transaction.atomic
def add_attachment(task, user, upload, confirm_duplicate=False, request=None):
    from apps.tasks.services.task_service import TaskService
    task = TaskService._lock(task)
    perm.require(perm.can_work(task, user), user, 'file.upload', task,
                 'Only people with a role on this task can attach files.')
    if task.status == 'deleted':
        raise ValidationError({'file': 'Cannot attach files to a deleted task.'})
    if upload is None:
        raise ValidationError({'file': 'Choose a file.'})

    original = safe_name(upload.name)
    ext = original.rsplit('.', 1)[-1].lower() if '.' in original else ''
    limit = (task.firm.max_upload_mb or 25) * 1024 * 1024

    def reject(reason, message, **extra):
        log_event('file.reject', 'Task', task.id, result='error', level='WARNING', reason=reason,
                  ext=ext, size=getattr(upload, 'size', None), **extra)
        raise ValidationError({'file': message})

    if ext not in ALLOWED:
        reject('extension', f'File type .{ext or "?"} is not allowed. Allowed: {", ".join(sorted(ALLOWED))}.')
    if upload.size > limit:
        reject('too_large', f'File is larger than {task.firm.max_upload_mb} MB.')
    if upload.size == 0:
        reject('empty', 'The file is empty.')

    data = upload.read()
    kind = detect_kind(data)
    expected_kind, mime = ALLOWED[ext]
    if kind != expected_kind:
        reject('content_mismatch', f'The file content is not a real .{ext} file.', detected=kind)

    sha = hashlib.sha256(data).hexdigest()
    dup = TaskAttachment.objects.filter(task=task, sha256=sha, deleted_at__isnull=True).first()
    if dup and not confirm_duplicate:
        log_event('file.duplicate_warning', 'Task', task.id, sha256=sha, existing=dup.id)
        raise DuplicateAttachment({'duplicate': True, 'existing_file_name': dup.file_name,
                                   'error': f'The same file is already attached as "{dup.file_name}". Upload again to keep both.'})

    key = uuid.uuid4().hex
    att = TaskAttachment(task=task, uploaded_by=user, file_name=original, mime=mime, size_bytes=len(data),
                         storage_key=key, sha256=sha)
    att.file.save(f'{key}.{ext}', ContentFile(data), save=False)
    att.save()
    AuditLog.log(firm_id=task.firm_id, action='file.upload', entity_type='Task', entity_id=str(task.id),
                 actor_user_id=getattr(user, 'id', None),
                 new_value={'attachment_id': str(att.id), 'file_name': original, 'size': len(data)}, request=request)
    log_event('file.upload', 'Task', task.id, attachment_id=att.id, mime=mime, size=len(data), sha256=sha,
              duplicate_confirmed=bool(dup))
    return att


@transaction.atomic
def delete_attachment(task, att, user, request=None):
    """Soft delete: the uploader or an Admin+. The file stays in storage until the retention job (spec F4)."""
    allowed = perm.is_admin(user) or (att.uploaded_by_id == getattr(user, 'id', None) and perm.can_work(task, user))
    perm.require(allowed, user, 'file.delete', task, 'Only the person who uploaded the file, or an admin, can remove it.')
    if att.deleted_at:
        raise ValidationError({'attachment': 'Already removed.'})
    att.deleted_at = timezone.now()
    att.save(update_fields=['deleted_at', 'updated_at'])
    AuditLog.log(firm_id=task.firm_id, action='file.delete', entity_type='Task', entity_id=str(task.id),
                 actor_user_id=user.id, old_value={'attachment_id': str(att.id), 'file_name': att.file_name},
                 request=request)
    log_event('file.delete', 'Task', task.id, attachment_id=att.id)
