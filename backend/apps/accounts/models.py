import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from apps.common.models import BaseModel

class Firm(BaseModel):
    name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255, blank=True, default='')
    logo = models.ImageField(upload_to='firm_logos/', null=True, blank=True)
    fy_start_month = models.PositiveSmallIntegerField(default=4) # 1-12, default April
    timezone = models.CharField(max_length=50, default='Asia/Kolkata')
    date_format = models.CharField(max_length=20, default='DD-MM-YYYY')
    long_due_days = models.PositiveIntegerField(default=30)
    staff_can_create_task = models.BooleanField(default=False)
    staff_can_complete = models.BooleanField(default=True)
    allow_pickup = models.BooleanField(default=True) # §5.4 A3 self-pickup enabled
    max_upload_mb = models.PositiveSmallIntegerField(default=25)  # spec §3.2 attachments, default 25 MB

    def __str__(self):
        return self.name


class Branch(BaseModel):
    firm = models.ForeignKey(Firm, on_delete=models.CASCADE, related_name='branches')
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = 'branches'
        unique_together = ('firm', 'code')

    def __str__(self):
        return f"{self.name} ({self.code})"


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email address is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('system_role', User.Role.SUPERADMIN)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        SUPERADMIN = 'superadmin', 'Superadmin'
        ADMIN = 'admin', 'Admin'
        STAFF = 'staff', 'Staff'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    firm = models.ForeignKey(Firm, on_delete=models.CASCADE, related_name='users', null=True, blank=True)
    email = models.EmailField(unique=True, db_index=True)
    phone = models.CharField(max_length=20, blank=True, default='')
    full_name = models.CharField(max_length=150)
    designation = models.CharField(max_length=100, blank=True, default='')
    system_role = models.CharField(max_length=20, choices=Role.choices, default=Role.STAFF, db_index=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False) # For Django admin access
    # Per-user exception to firm.staff_can_create_task (staff only; admins can always create):
    # None = follow the firm setting, True = always allow, False = never allow
    can_create_tasks = models.BooleanField(null=True, blank=True, default=None)
    hourly_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) # Phase 3
    # Set when an admin gives a temporary password: the user must choose a new password before any other work
    must_change_password = models.BooleanField(default=False)
    joined_on = models.DateField(null=True, blank=True)
    left_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    def __str__(self):
        return f"{self.full_name} ({self.email}) - {self.system_role}"

    @property
    def is_superadmin(self):
        return self.system_role == self.Role.SUPERADMIN

    @property
    def is_admin(self):
        return self.system_role in (self.Role.SUPERADMIN, self.Role.ADMIN)

    @property
    def effective_can_create_tasks(self):
        """Admin+ always; staff: per-user value if set, else the firm setting."""
        if self.is_admin or self.is_superuser:
            return True
        if self.can_create_tasks is not None:
            return bool(self.can_create_tasks)
        return bool(self.firm and self.firm.staff_can_create_task)


class AuthThrottle(models.Model):
    """One row per failed login or password-reset request. Used for the lockout rules
    (apps/accounts/security.py). Rows older than 1 day are removed on the next write."""
    KIND_LOGIN_FAIL = 'login_fail'
    KIND_RESET_REQUEST = 'reset_request'
    kind = models.CharField(max_length=20, db_index=True)
    key = models.CharField(max_length=254, db_index=True)   # e-mail address, lower case
    ip = models.CharField(max_length=64, blank=True, default='', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=['kind', 'key', 'created_at']), models.Index(fields=['kind', 'ip', 'created_at'])]


class UserBranch(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_branches')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='branch_users')
    is_default = models.BooleanField(default=False)

    class Meta:
        unique_together = ('user', 'branch')

    def __str__(self):
        return f"{self.user.full_name} -> {self.branch.name}"
