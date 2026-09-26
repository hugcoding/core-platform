"""Conservative local matching. Categories always come from owner reviews."""
from decimal import Decimal
import re
import unicodedata

METHOD = 'local-merchant-v2'
MAX_SCAN = 25000
PROCESSORS = {'mollie', 'adyen', 'paypal', 'stripe', 'sumup', 'worldline', 'pay nl'}


def normalize(value):
    return ' '.join(re.findall(r'[^\W_]+', unicodedata.normalize('NFKC', value or '').casefold()))

def card_description_merchant(value):
    """
    Extract a stable merchant candidate from ASN card/Apple Pay descriptions.

    Examples:
      DEKAMARKT LOC 726 >HAARLEM 21.09.2026 ... -> dekamarkt
      DEKAMARKT LOC 422 >HAARLEM 20.09.2026 ... -> dekamarkt
      Plus Haarlem >HAARLEM 18.09.2026 ...      -> plus haarlem
      Wibra Marsmanplein >HAARLEM ...           -> wibra marsmanplein
      BCK*Bruna marsmanplein >HAARLEM ...       -> bruna marsmanplein

    This only derives an identity candidate. It does not infer a category.
    """
    value = unicodedata.normalize('NFKC', value or '').strip()
    if not value:
        return None

    # Existing ASN terminal/reference prefix.
    value = re.sub(
        r'^NL[A-Z0-9]{6,34}\s*>\s*',
        '',
        value,
        count=1,
        flags=re.I,
    )

    # Card descriptions in the current ASN import put the merchant before
    # ">LOCATION ...". Everything after that delimiter is transaction metadata.
    merchant_part = value.split('>', 1)[0].strip()

    # Only derive a merchant from the structured ASN card format.
    # Arbitrary free-text descriptions must never become merchant identities.
    if '>' not in value:
        return None

    # Merchant is the part before >LOCATION.
    merchant_part = value.split('>', 1)[0].strip()

    if not merchant_part:
        return None

    # Payment-service / terminal prefixes seen in merchant descriptions.
    merchant_part = re.sub(
        r'^(?:BCK|CVC)\*',
        '',
        merchant_part,
        count=1,
        flags=re.I,
    )

    # Store/location numbers are volatile and must not become part of identity.
    merchant_part = re.sub(
        r'\s+LOC(?:ATIE)?\s+\d+\s*$',
        '',
        merchant_part,
        flags=re.I,
    )

    candidate = normalize(merchant_part)

    if len(candidate) < 3:
        return None

    # Transaction metadata is not a merchant.
    # Prevent descriptions such as:
    # "MCC:4111 Apple Pay NEDERLAND"
    # from becoming merchant identities.
    if re.match(r'^mcc\s+\d+\b', candidate):
        return None

    # These are payment mechanisms, not merchant identities.
    if candidate in {
        'apple pay',
        'google pay',
        'betaling',
        'onbekende tegenpartij',
        'unknown',
    }:
        return None

    return candidate

def merchant_identity(payload):
    """
    Return the strongest deterministic merchant identity available.

    Explicit recognized merchants remain preferred. For card transactions
    without a usable counterparty, derive a stable identity from the
    structured bank description.
    """
    merchant = recognized_merchant(payload)
    if merchant:
        return ('recognized', normalize(merchant))

    party = normalize(payload.get('counterparty'))

    unknown_party = (
        not party
        or party in {
            'onbekende tegenpartij',
            'unknown',
            'betaling',
            'apple pay',
            'google pay',
        }
    )

    if unknown_party:
        candidate = card_description_merchant(
            payload.get('description')
        )
        if candidate:
            return ('card_description', candidate)

    return None

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
    description = unicodedata.normalize(
        'NFKC',
        payload.get('description') or '',
    ).casefold()

    if re.search(
        r'(?<![a-z0-9])(?:www\.)?ovpay(?=$|[^a-z])',
        description,
    ):
        return ('ovpay', direction, currency)

    # Prefer a deterministic merchant identity before falling back to
    # counterparty + account.
    merchant = merchant_identity(payload)

    if merchant:
        source, name = merchant
        return (
            'merchant_marker',
            name,
            direction,
            currency,
        )

    party = normalize(payload.get('counterparty'))
    account = ''.join(
        (payload.get('counteraccount') or '').split()
    ).upper()

    if (
        not party
        or party in {
            'onbekende tegenpartij',
            'unknown',
            'betaling',
            'apple pay',
            'google pay',
        }
    ):
        return None

    if any(
        party == p or party.startswith(p + ' ')
        for p in PROCESSORS
    ):
        return None

    # Require both signals for generic counterparties; no guessing from free text.
    if len(party) >= 3 and account:
        return (
            'counterparty_account',
            party,
            account,
            direction,
            currency,
        )

    return None
