"""Private account labels; the imported account identity remains immutable."""
import unicodedata

from core.finance.crypto import decrypt


def normalize_name(value):
    if not isinstance(value, str):
        raise ValueError('invalid_account_name')
    value = unicodedata.normalize('NFC', value)
    if len(value) > 80 or any(unicodedata.category(c).startswith('C') for c in value):
        raise ValueError('invalid_account_name')
    return value.strip() or None


def account_view(row):
    original = decrypt(row['private_data'])
    name = decrypt(row['name_data'])['display_name'] if row['name_data'] else None
    return {
        'id': str(row['id']),
        'label': f"{name} · •{original['iban'][-4:]}" if name else original['label'],
        'default_label': original['label'],
        'display_name': name,
        'name_event_id': str(row['name_event_id']) if row['name_event_id'] else None,
    }
