import re
from rest_framework import serializers

PAN_REGEX = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]$')
GSTIN_REGEX = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$')

PAN_ENTITY_MAP = {
    'individual': 'P',
    'company': 'C',
    'partnership': 'F',
    'llp': 'F',
    'huf': 'H',
    'trust': 'T',
    'aop': 'A',
}

def validate_pan_format(pan: str) -> str:
    """Validate standard Indian PAN format: 5 letters, 4 digits, 1 letter."""
    if not pan:
        return ''
    pan = pan.strip().upper()
    if not PAN_REGEX.match(pan):
        raise serializers.ValidationError('Invalid PAN format. Must be 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F).')
    return pan

GSTIN_CHARS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'


def gstin_check_char(gstin14: str) -> str:
    """GSTN checksum (mod 36, factors 1,2,1,2... from the left) over the first 14 chars."""
    total = 0
    for i, ch in enumerate(gstin14[:14]):
        product = GSTIN_CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return GSTIN_CHARS[(36 - total % 36) % 36]


def validate_gstin_format(gstin: str, pan: str = '') -> str:
    """
    Validate Indian GSTIN format:
    15 characters: 2-digit state code (01-38), 10-char PAN, 1 entity code, 'Z', 1 checksum.
    If PAN is provided, chars 3-12 must match the client's PAN.
    """
    if not gstin:
        return ''
    gstin = gstin.strip().upper()
    if not GSTIN_REGEX.match(gstin):
        raise serializers.ValidationError('Invalid GSTIN format. Must be 15 characters according to standard GSTIN rules.')

    state_code = int(gstin[:2])
    if state_code < 1 or state_code > 38:
        raise serializers.ValidationError('Invalid GSTIN state code. Must be between 01 and 38.')

    expected = gstin_check_char(gstin)
    if gstin[14] != expected:
        raise serializers.ValidationError(
            f'Invalid GSTIN checksum: the last character should be {expected}. Please check the number.')

    if pan:
        pan_clean = pan.strip().upper()
        gstin_pan = gstin[2:12]
        if gstin_pan != pan_clean:
            raise serializers.ValidationError(f'GSTIN contains PAN {gstin_pan}, which does not match client PAN {pan_clean}.')

    return gstin

def check_pan_entity_type_warning(pan: str, client_type: str) -> str | None:
    """Returns warning if 4th char of PAN conflicts with selected client type."""
    if not pan or len(pan) < 4:
        return None
    fourth_char = pan[3].upper()
    expected_char = PAN_ENTITY_MAP.get(client_type)
    if expected_char and fourth_char != expected_char:
        return f"Warning: PAN 4th character '{fourth_char}' does not match client type '{client_type}' (expected '{expected_char}')."
    return None
