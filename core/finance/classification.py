"""Classification enriches bank data; taxonomy comes exclusively from PostgreSQL."""
import unicodedata

from fastapi import HTTPException
from core.finance.crypto import encrypt, fingerprint


def merchant_name(value):
    if value is None:
        return None
    if not isinstance(value, str) or any(unicodedata.category(c).startswith('C') for c in value):
        raise HTTPException(422, 'invalid_merchant')
    value = ' '.join(unicodedata.normalize('NFKC', value).split())
    if len(value) > 120:
        raise HTTPException(422, 'invalid_merchant')
    return value or None


def validate_category(cur, category, subcategory):
    if category is None:
        if subcategory is not None:
            raise HTTPException(422, 'invalid_category')
        return
    cur.execute('SELECT id,parent_id,active FROM finance.finance_categories WHERE code=%s', (category,))
    parent = cur.fetchone()
    if not parent or parent['parent_id'] is not None or not parent['active']:
        raise HTTPException(422, 'invalid_category')
    if subcategory:
        cur.execute('SELECT parent_id,active FROM finance.finance_categories WHERE code=%s', (subcategory,))
        child = cur.fetchone()
        if not child or child['parent_id'] != parent['id'] or not child['active']:
            raise HTTPException(422, 'invalid_category')


def merchant_id(cur, name):
    if not name:
        return None
    identity = fingerprint('normalized-merchant-v1', name.casefold())
    cur.execute('''INSERT INTO finance.finance_counterparties(identity_key,private_data)
        VALUES (%s,%s) ON CONFLICT(identity_key) DO NOTHING''', (identity, encrypt({'name': name})))
    cur.execute('SELECT id FROM finance.finance_counterparties WHERE identity_key=%s', (identity,))
    return cur.fetchone()['id']


def signature(row):
    return tuple(row.get(k) for k in ('transaction_type', 'category_code', 'subcategory_code', 'merchant_id'))


def conflicts(example, seed):
    # Pre-migration reviews asserted only a category. Missing old enrichment is
    # not a contradictory assertion, but a new explicit UNKNOWN remains one.
    if example.get('legacy_classification'):
        return example['category_code'] != seed['category_code']
    return signature(example) != signature(seed)


def predecessor(cur, transaction_id):
    # Unconfirmed future classifier events remain in the physical audit chain,
    # while optimistic concurrency checks use the last effective owner review.
    cur.execute('SELECT id FROM finance.finance_review_events WHERE transaction_id=%s ORDER BY sequence_no DESC LIMIT 1',
                (transaction_id,))
    row = cur.fetchone()
    return row['id'] if row else None


def insert_suggestion(cur, target, seed, expected, key, digest, method):
    """An owner-confirmed proposal copies the entire classification, never raw data."""
    validate_category(cur, seed['category_code'], seed.get('subcategory_code'))
    cur.execute('''INSERT INTO finance.finance_review_events
        (transaction_id,category_code,subcategory_code,transaction_type,merchant_id,
         classification_source,confidence,confirmed,supersedes_event_id,actor,
         idempotency_key,payload_digest,source_review_id,suggestion_method)
        VALUES (%s,%s,%s,%s,%s,'MERCHANT',NULL,true,%s,'owner',%s,%s,%s,%s)''',
        (target, seed['category_code'], seed.get('subcategory_code'), seed['transaction_type'],
         seed.get('merchant_id'), predecessor(cur, target), key, digest, seed['review_id'], method))
