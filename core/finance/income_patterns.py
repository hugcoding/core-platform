"""Deterministic income patterns; no amount/month matching, model or external I/O."""
import re
from decimal import Decimal
from core.finance.suggestions import normalize, PROCESSORS

METHOD='income-pattern-v1'


def key(row,payload):
    if Decimal(str(row['amount']))<=0 or len(payload.get('details') or [])>1:return None
    if str(payload.get('reversal') or '').upper() not in ('','NO','FALSE','0'):return None
    if row.get('transaction_type') not in (None,'UNKNOWN','INCOME'):return None
    if not row.get('account_id') or not row.get('currency'):return None
    text=normalize(payload.get('description'))
    scope=(str(row['account_id']),row['currency'])
    if row.get('rule_version')=='bank-type-v1:interest_received' or re.match(r'^rente over positief saldo\b',text):
        return ('interest',*scope)
    if not re.match(r'^(?:salaris|loon)(?:\s|$)',text):return None
    # Explicit reversals/corrections and ambiguous memos are not salary evidence.
    if re.search(r'\b(?:terug\w*|correctie\w*|storno\w*|voorschotlening)\b',text):return None
    party=normalize(payload.get('counterparty'))
    if len(party)<3 or party in {'onbekende tegenpartij','unknown','betaling'} or any(party==p or party.startswith(p+' ') for p in PROCESSORS):return None
    counter=''.join(str(payload.get('counteraccount') or '').split()).upper()
    return ('salary',*scope,counter,party)


def default(row,payload,categories):
    pattern=key(row,payload)
    if not pattern:return None
    parent=next((c for c in categories if c['code']=='inkomen' and not c['parent_id'] and c.get('active',True) and c['transaction_type']=='INCOME'),None)
    child=next((c for c in categories if parent and c['code']==('inkomen_salaris' if pattern[0]=='salary' else 'inkomen_rente') and c['parent_id']==parent['id'] and c.get('active',True) and c['transaction_type']=='INCOME'),None)
    if not child:return None
    return dict(category_code=parent['code'],subcategory_code=child['code'],transaction_type='INCOME',merchant_id=None,
                source='RULE',confidence=None,seed=None,rule='salary' if pattern[0]=='salary' else 'bank_interest')


def eligible(row):
    return not row.get('confirmed') and (row.get('category_code') is None or (
        row.get('classification_source') in ('RULE','MERCHANT','AI') and row.get('subcategory_code') is None))


def refines(row,choice):
    return bool(choice) and eligible(row) and (row.get('category_code') is None or (
        choice['source'] in ('MERCHANT','RULE') and choice['category_code']==row['category_code']
        and choice['transaction_type']==row['transaction_type'] and choice.get('subcategory_code') is not None))
