"""Conservative local matching. Categories always come from owner reviews."""
from decimal import Decimal
import re
import unicodedata

METHOD = 'local-merchant-v2'
MAX_SCAN = 25000
PROCESSORS = {'mollie', 'adyen', 'paypal', 'stripe', 'sumup', 'worldline', 'pay nl'}


def normalize(value):
    return ' '.join(re.findall(r'[^\W_]+', unicodedata.normalize('NFKC', value or '').casefold()))


def recognized_merchant(payload):
    """Explicit merchant markers only; no category or meaning is inferred."""
    if len(payload.get('details') or []) > 1:
        return None
    for value in (payload.get('counterparty'), payload.get('description')):
        # ASN card descriptions can prefix the merchant with a terminal reference.
        # Strip only that anchored, delimited field, never arbitrary invoice text.
        value = unicodedata.normalize('NFKC', value or '').strip()
        value = re.sub(r'^NL[A-Z0-9]{6,34}\s*>\s*', '', value, count=1, flags=re.I)
        text = normalize(value)
        if re.match(r'^shell (?:station\b|[0-9]{3,}\b)', text):
            return 'Shell'
        if re.match(r'^(?:albert heijn\b|ah (?:[0-9]{4}\b|bouwens\b))', text):
            return 'Albert Heijn'
    return None


def identity(payload, amount, currency):
    if len(payload.get('details') or []) > 1:
        return None
    amount = Decimal(str(amount))
    if not amount:
        return None
    direction = 'debit' if amount < 0 else 'credit'
    # OVpay exports can attach a changing date directly to the merchant marker.
    # Neither a generic MCC nor words such as Apple Pay establish merchant identity.
    description = unicodedata.normalize('NFKC', payload.get('description') or '').casefold()
    if re.search(r'(?<![a-z0-9])(?:www\.)?ovpay(?=$|[^a-z])', description):
        return ('ovpay', direction, currency)
    merchant = recognized_merchant(payload)
    if merchant:
        return ('merchant_marker', merchant, direction, currency)
    party = normalize(payload.get('counterparty'))
    account = ''.join((payload.get('counteraccount') or '').split()).upper()
    if not party or party in {'onbekende tegenpartij', 'unknown', 'betaling', 'apple pay', 'google pay'}:
        return None
    if any(party == p or party.startswith(p+' ') for p in PROCESSORS):
        return None
    # Require both signals for generic counterparties; no guessing from free text.
    if len(party) >= 3 and account:
        return ('counterparty_account', party, account, direction, currency)
    return None
