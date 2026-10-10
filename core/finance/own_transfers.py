"""Known managed account evidence; never pair transactions by amount or name."""
from decimal import Decimal
from core.finance.crypto import fingerprint


def counter_account(account_id, payload, scope):
    if len(payload.get('details') or []) > 1:
        return None
    iban = ''.join(str(payload.get('counteraccount') or '').split()).upper()
    other = scope[1].get(fingerprint('account-v1', iban)) if iban else None
    return other if other and other != account_id else None


def relationship(account_id, other, memberships):
    first, second = memberships.get(account_id), memberships.get(other)
    if not first or not second:
        return 'unassigned'
    return 'internal' if first == second else 'between_groups'


def decide(target, payload, categories, scope):
    other = counter_account(target.get('account_id'), payload, scope)
    if not other or not Decimal(str(target['amount'])):
        return None
    # Reversals, cards, fees and aggregate bank evidence are not regular transfers.
    if payload.get('reversal', '').upper() not in ('', 'NO', 'FALSE', '0'):
        return None
    if target.get('classification_source') == 'RULE' and target.get('transaction_type') not in ('UNKNOWN', 'TRANSFER'):
        return None
    parent = next((c for c in categories if c['code'] == 'overboekingen'
                   and not c['parent_id'] and c.get('active', True)
                   and c['transaction_type'] == 'TRANSFER'), None)
    if not parent:
        return None
    return dict(category_code=parent['code'], subcategory_code=None,
                transaction_type='TRANSFER', merchant_id=None, source='RULE',
                confidence=None, seed=None, rule='known_account_transfer')


def display(row, payload, scope, accounts, groups):
    other = counter_account(row['account_id'], payload, scope)
    if not other:
        return {}
    by_id = {a['id']: a for a in accounts}
    account = by_id.get(str(other))
    if not account:
        return {}
    kind = relationship(row['account_id'], other, scope[0])
    names = {g['id']: g['name'] for g in groups}
    result = dict(counter_account_id=str(other), counter_account_label=account['label'])
    # A label match does not override an explicit owner judgement or reversal.
    if row.get('transaction_type') != 'TRANSFER':
        return result
    credit = Decimal(str(row['amount'])) > 0
    result.update(
                own_transfer_scope=kind,
                own_transfer_label={'internal': 'Eigen overboeking',
                    'between_groups': 'Overboeking tussen groepen',
                    'unassigned': 'Overboeking tussen beheerde rekeningen'}[kind],
                source_group=names.get(str(scope[0].get(other if credit else row['account_id']))),
                destination_group=names.get(str(scope[0].get(row['account_id'] if credit else other))))
    return result
