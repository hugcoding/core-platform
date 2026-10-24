"""Local, versioned bank-code catalogue shared by classification and owner UI."""
import json
from pathlib import Path
from decimal import Decimal
from core.finance.crypto import decrypt

CATALOGUE = json.loads(Path(__file__).with_name('bank_code_rules.json').read_text(encoding='utf-8'))
VERSION = CATALOGUE['version']


def match(row, payload):
    """Issuer is a code namespace, never standalone counterparty evidence."""
    if row.get('currency') != 'EUR' or Decimal(str(row['amount'])) <= 0:
        return None
    if str(payload.get('reversal') or '').upper() not in ('', 'NO', 'FALSE', '0'):
        return None
    if len(payload.get('details') or []) > 1:
        return None
    codes = [c for c in payload.get('bank_codes') or [] if any(c.values())]
    if not codes:
        return None
    for rule in CATALOGUE['rules']:
        # Entry/detail and linked import sources must agree. Missing ISO parts
        # are allowed; explicit conflicting evidence is not.
        identified=any(c.get('issuer','').upper()==rule['issuer'] and c.get('proprietary')==rule['code'] for c in codes)
        if identified and all((not c.get('proprietary') or (c.get('issuer','').upper()==rule['issuer'] and c['proprietary']==rule['code']))
               and (not c.get('issuer') or c['issuer'].upper()==rule['issuer'])
               and all(not c.get(k) or c[k] == expected for k, expected in zip(('domain', 'family', 'subfamily'), rule['iso']))
               for c in codes):
            return rule
    return None


def choice(row, payload, categories):
    rule = match(row, payload)
    if not rule or row.get('confirmed') or row.get('transaction_type') not in (None, 'UNKNOWN', 'INCOME'):
        return None
    parent = next((c for c in categories if c['code'] == rule['category'] and not c['parent_id']
                   and c.get('active', True) and c['transaction_type'] == rule['transaction_type']), None)
    child = next((c for c in categories if parent and c['code'] == rule['subcategory']
                  and c['parent_id'] == parent['id'] and c.get('active', True)
                  and c['transaction_type'] == rule['transaction_type']), None)
    if not child:
        return None
    return dict(category_code=parent['code'], subcategory_code=child['code'], transaction_type=rule['transaction_type'],
                merchant_id=None, source='RULE', confidence=None, seed=None,
                rule=rule['id'])


def hydrate_many(cur, rows):
    """Reuse already backfilled encrypted bank evidence, without opening exports."""
    payloads={str(r['id']):decrypt(r['private_data']) for r in rows}
    if not rows:return payloads
    cur.execute('''SELECT DISTINCT s.transaction_id,k.private_data FROM finance.finance_transaction_sources s
        JOIN finance.finance_import_records r ON r.id=s.record_id
        JOIN finance.v_import_status b ON b.id=r.batch_id
        JOIN finance.finance_record_bank_types k ON k.record_id=r.id AND k.version='bank-type-v1'
        WHERE s.transaction_id=ANY(%s::uuid[]) AND b.status IN ('imported','partial')''', (list(payloads),))
    evidence={}
    for r in cur.fetchall():evidence.setdefault(str(r['transaction_id']),[]).append(decrypt(r['private_data']))
    for tid,values in evidence.items():
        original=payloads[tid]
        reversals=[str(e.get('reversal') or '').upper() for e in values]+[str(original.get('reversal') or '').upper()]
        codes=[c for e in values for c in e.get('codes',[])]+list(original.get('bank_codes') or [])
        codes=list({json.dumps(c,sort_keys=True):c for c in codes if any(c.values())}.values())
        payloads[tid]={**original,'bank_codes':codes if all(e.get('codes') for e in values) else [],
                       'reversal':'' if all(v in ('','NO','FALSE','0') for v in reversals) else 'UNKNOWN'}
    return payloads


def hydrate(cur, row, payload):
    return hydrate_many(cur,[row])[str(row['id'])]


def preview_status(row, rule):
    if row.get('confirmed'):
        return 'manual_conflict' if (row.get('category_code'), row.get('subcategory_code'), row.get('transaction_type')) != (
            rule['category'], rule['subcategory'], rule['transaction_type']) else 'manual'
    if row.get('category_code') == rule['category'] and row.get('subcategory_code') == rule['subcategory']:
        return 'aligned'
    from core.finance.income_patterns import refines
    proposed = dict(source='RULE', category_code=rule['category'], subcategory_code=rule['subcategory'], transaction_type=rule['transaction_type'])
    return 'eligible' if refines(row, proposed) else 'protected'
