import uuid
from django.db import models
from apps.common.models import BaseModel
from apps.accounts.models import Firm
from apps.common.crypto import encrypt_pan, decrypt_pan, mask_pan, pan_blind_index

class ClientGroup(BaseModel):
    firm = models.ForeignKey(Firm, on_delete=models.CASCADE, related_name='client_groups')
    name = models.CharField(max_length=150)

    class Meta:
        unique_together = ('firm', 'name')
        ordering = ['name']

    def __str__(self):
        return self.name


class Client(BaseModel):
    class ClientType(models.TextChoices):
        INDIVIDUAL = 'individual', 'Individual'
        HUF = 'huf', 'HUF'
        PARTNERSHIP = 'partnership', 'Partnership Firm'
        LLP = 'llp', 'LLP'
        COMPANY = 'company', 'Company (Pvt/Public)'
        TRUST = 'trust', 'Trust'
        AOP = 'aop', 'AOP / BOI'
        OTHER = 'other', 'Other'

    firm = models.ForeignKey(Firm, on_delete=models.CASCADE, related_name='clients')
    name = models.CharField(max_length=255, db_index=True)
    client_group = models.ForeignKey(ClientGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    client_type = models.CharField(max_length=20, choices=ClientType.choices, default=ClientType.INDIVIDUAL)

    # PAN: Stored encrypted at rest, plus masked string for fast search/display
    pan_encrypted = models.TextField(blank=True, default='')
    pan_masked = models.CharField(max_length=12, blank=True, default='', db_index=True)
    # Keyed hash of the PAN for exact search and duplicate checks (see crypto.pan_blind_index)
    pan_hash = models.CharField(max_length=64, blank=True, default='', db_index=True)

    gstin = models.CharField(max_length=15, blank=True, default='', db_index=True)
    tan = models.CharField(max_length=10, blank=True, default='')
    cin = models.CharField(max_length=21, blank=True, default='')

    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=25, blank=True, default='')
    address = models.TextField(blank=True, default='')
    state_code = models.CharField(max_length=2, blank=True, default='') # 01-38

    is_active = models.BooleanField(default=True)
    is_blocked_for_new_tasks = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['firm', 'name']),
            models.Index(fields=['firm', 'pan_masked']),
            models.Index(fields=['firm', 'gstin']),
        ]

    def __str__(self):
        return f"{self.name} ({self.pan_masked or 'No PAN'})"

    def set_pan(self, raw_pan: str):
        if raw_pan:
            clean = raw_pan.strip().upper()
            self.pan_encrypted = encrypt_pan(clean)
            self.pan_masked = mask_pan(clean)
            self.pan_hash = pan_blind_index(clean)
        else:
            self.pan_encrypted = ''
            self.pan_masked = ''
            self.pan_hash = ''

    def get_pan_decrypted(self) -> str:
        return decrypt_pan(self.pan_encrypted)


class ClientContact(BaseModel):
    class Role(models.TextChoices):
        OWNER = 'owner', 'Owner / Proprietor'
        DIRECTOR = 'director', 'Director / Partner'
        ACCOUNTANT = 'accountant', 'Accountant / Manager'
        OTHER = 'other', 'Other'

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='contacts')
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.OWNER)
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=25, blank=True, default='')
    is_primary = models.BooleanField(default=False)
    receives_task_emails = models.BooleanField(default=True)

    class Meta:
        ordering = ['-is_primary', 'name']

    def __str__(self):
        return f"{self.name} ({self.role}) - {self.client.name}"
