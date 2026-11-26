import os
import hmac
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

def _get_aes_key() -> bytes:
    """Derive 32-byte key from settings.PAN_ENCRYPTION_KEY."""
    raw_key = getattr(settings, 'PAN_ENCRYPTION_KEY', 'firmflow_32_byte_secret_key_pan_aes_gcm!')
    # Normalize to 32 bytes via SHA256 if needed
    return hashlib.sha256(raw_key.encode('utf-8')).digest()

def encrypt_pan(pan: str) -> str:
    """Encrypt PAN string using AES-256-GCM, returning urlsafe base64 string (nonce + ciphertext)."""
    if not pan:
        return ''
    key = _get_aes_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12) # 96-bit nonce for GCM
    ciphertext = aesgcm.encrypt(nonce, pan.strip().upper().encode('utf-8'), None)
    payload = nonce + ciphertext
    return base64.urlsafe_b64encode(payload).decode('utf-8')

def decrypt_pan(encrypted_pan: str) -> str:
    """Decrypt base64 ciphertext using AES-256-GCM."""
    if not encrypted_pan:
        return ''
    try:
        payload = base64.urlsafe_b64decode(encrypted_pan.encode('utf-8'))
        nonce = payload[:12]
        ciphertext = payload[12:]
        key = _get_aes_key()
        aesgcm = AESGCM(key)
        decrypted = aesgcm.decrypt(nonce, ciphertext, None)
        return decrypted.decode('utf-8')
    except Exception:
        return ''

def mask_pan(pan: str) -> str:
    """Return masked PAN: 'ABCDE1234F' -> 'XXXXX1234X'."""
    if not pan or len(pan) != 10:
        return pan or ''
    # Mask first 5 characters and last char: XXXXX + digits + X
    return 'XXXXX' + pan[5:9] + 'X'


def pan_blind_index(pan: str) -> str:
    """
    Keyed hash of the PAN (HMAC-SHA256) so an exact PAN can be searched and
    checked for duplicates without decrypting every row. The PAN itself
    cannot be recovered from this value without the key.
    """
    if not pan:
        return ''
    index_key = hashlib.sha256(_get_aes_key() + b'|firmflow-pan-blind-index').digest()
    return hmac.new(index_key, pan.strip().upper().encode('utf-8'), hashlib.sha256).hexdigest()
