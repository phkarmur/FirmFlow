import uuid
from django.db import models
from django.utils import timezone

class BaseModel(models.Model):
    """Abstract base model with UUID primary key and timestamps."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditLogAppendOnly(Exception):
    """Raised when code tries to change or remove an audit log entry."""


class AuditLogQuerySet(models.QuerySet):
    # Bulk update / delete are refused (Django admin and shell use these)
    def update(self, **kwargs):
        raise AuditLogAppendOnly('The audit log is append-only: entries cannot be changed.')

    def delete(self):
        raise AuditLogAppendOnly('The audit log is append-only: entries cannot be removed.')


def _safe_ip(value):
    """Return a valid IP address or None (the column type rejects other text on PostgreSQL)."""
    import ipaddress
    try:
        return str(ipaddress.ip_address((value or '').strip())) if value else None
    except ValueError:
        return None


class AuditLog(models.Model):
    """
    Append-only audit log.
    MUST never contain PAN, passwords, OTPs, or file contents.
    Append-only is enforced two times: here (save/delete/queryset) and, on PostgreSQL, by database
    triggers (migration common.0002) that refuse UPDATE and DELETE from any client.
    """
    class ActorType(models.TextChoices):
        USER = 'user', 'User'
        SYSTEM = 'system', 'System'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    firm_id = models.UUIDField(db_index=True)
    actor_user_id = models.UUIDField(null=True, blank=True, db_index=True)
    actor_type = models.CharField(max_length=10, choices=ActorType.choices, default=ActorType.USER)
    action = models.CharField(max_length=100, db_index=True)
    entity_type = models.CharField(max_length=100, db_index=True)
    entity_id = models.CharField(max_length=100, db_index=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['firm_id', 'created_at']),
            models.Index(fields=['entity_type', 'entity_id']),
        ]

    def __str__(self):
        return f"{self.action} on {self.entity_type}:{self.entity_id} by {self.actor_user_id or self.actor_type}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditLogAppendOnly('The audit log is append-only: entries cannot be changed.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditLogAppendOnly('The audit log is append-only: entries cannot be removed.')

    @classmethod
    def log(cls, firm_id, action, entity_type, entity_id, actor_user_id=None, actor_type='user', old_value=None, new_value=None, request=None):
        """Helper to create an audit log entry."""
        ip = None
        user_agent = ''
        if request:
            # X-Forwarded-For only when the server is behind a trusted proxy (setting TRUST_X_FORWARDED_FOR);
            # a client can send this header itself
            from django.conf import settings
            raw = request.META.get('REMOTE_ADDR', '')
            if getattr(settings, 'TRUST_X_FORWARDED_FOR', False) and request.META.get('HTTP_X_FORWARDED_FOR'):
                raw = request.META['HTTP_X_FORWARDED_FOR'].split(',')[0]
            ip = _safe_ip(raw)
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
            if not actor_user_id and request.user and request.user.is_authenticated:
                actor_user_id = request.user.id

        return cls.objects.create(
            firm_id=firm_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            old_value=old_value,
            new_value=new_value,
            ip=ip,
            user_agent=user_agent
        )
