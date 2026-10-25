"""Finance adapter: encrypted rule versions, shared matching and existing reviews."""
from decimal import Decimal
from fastapi import HTTPException
from core.recognition.rules import validate,matches
from core.finance.crypto import decrypt,encrypt,fingerprint
from core.finance.classification import merchant_name,validate_category,signature,merchant_id,insert_manual_batch
from core.finance.event_recognition import hydrate_many,match as bank_match,CATALOGUE

MODEL='finance-local-v1:owner-rule-v1'
MAX_SCAN=25000


def validate_finance(cur,rule):
    try:validate(rule)
    except (ValueError,TypeError):raise HTTPException(422,'invalid_recognition_rule') from None
    if rule['module']!='finance':raise HTTPException(422,'invalid_recognition_module')
    actions=rule['set']
    if 'counterparty' in actions and not merchant_name(actions['counterparty']):raise HTTPException(422,'invalid_merchant')
    if 'subcategory' in actions and 'category' not in actions:raise HTTPException(422,'invalid_category')
    if 'category' in actions:
        validate_category(cur,actions['category'],actions.get('subcategory'))
        cur.execute('SELECT transaction_type FROM finance.finance_categories WHERE code=%s',(actions['category'],))
        if cur.fetchone()['transaction_type'] in ('TRANSFER','SAVING','INVESTMENT','DEBT'):
            raise HTTPException(422,'invalid_classification')
    if 'transaction_type' in actions and actions['transaction_type'] not in ('INCOME','EXPENSE','CORRECTION','UNKNOWN'):
        raise HTTPException(422,'invalid_classification')
    return rule


def current(cur,active=False):
    cur.execute('''SELECT * FROM (SELECT DISTINCT ON(rule_id) * FROM finance.finance_recognition_rule_events
        ORDER BY rule_id,sequence_no DESC) r '''+('WHERE active ' if active else '')+'ORDER BY sequence_no DESC')
    return [{**r,'rule':decrypt(r['private_data'])} for r in cur.fetchall()]


def facts(row,payload):
    codes=payload.get('bank_codes') or []
    return dict(_id=str(row['id']),description=payload.get('description'),counterparty=payload.get('counterparty'),
                counteraccount=payload.get('counteraccount'),account_id=str(row['account_id']),
                issuer=[c.get('issuer') for c in codes],bank_code=[c.get('proprietary') for c in codes],
                direction='CRDT' if Decimal(str(row['amount']))>0 else 'DBIT',currency=row['currency'])


def plan(row,payload,rule,categories,owner_confirmation=False):
    if len(payload.get('details') or [])>1 or str(payload.get('reversal') or '').upper() not in ('','NO','FALSE','0'):
        return None
    if not Decimal(str(row['amount'])):return None
    context=facts(row,payload)
    bank_fields={'issuer','bank_code'}
    terms=next(iter(rule['when'].values()))
    if any(t['field'] in bank_fields for t in terms):
        codes=[c for c in payload.get('bank_codes') or [] if any(c.values())]
        # Issuer and proprietary code must refer to the same evidence record.
        if not codes or not all(matches(rule,'finance',{**context,'issuer':c.get('issuer'),'bank_code':c.get('proprietary')}) for c in codes):return None
        if any(t['field']=='bank_code' and t['value']==r['code'] for t in terms for r in CATALOGUE['rules']) and not bank_match(row,payload):return None
    elif not matches(rule,'finance',context):return None
    actions=rule['set'];desired={k:row.get(k) for k in ('category_code','subcategory_code','transaction_type','merchant_id')}
    desired['transaction_type']=desired['transaction_type'] or 'UNKNOWN'
    if 'category' in actions:
        desired.update(category_code=actions['category'],subcategory_code=actions.get('subcategory'))
        parent=next((c for c in categories if c['code']==actions['category'] and not c['parent_id'] and c.get('active',True)),None)
        child=next((c for c in categories if parent and c['code']==actions.get('subcategory') and c['parent_id']==parent['id'] and c.get('active',True)),None)
        if not parent or (actions.get('subcategory') and not child):return {'status':'invalid_category','changes':{},'desired':desired}
        desired['transaction_type']=actions.get('transaction_type', (child or parent)['transaction_type'])
    elif 'transaction_type' in actions:desired['transaction_type']=actions['transaction_type']
    before_name=decrypt(row['merchant_data']).get('name') if row.get('merchant_data') else ''
    changes={k:v for k,v in desired.items() if k!='merchant_id' and v!=row.get(k)}
    if 'counterparty' in actions and merchant_name(actions['counterparty']).casefold()!=before_name.casefold():
        changes['counterparty']=merchant_name(actions['counterparty'])
    status='eligible' if changes else 'aligned'
    # Filling a missing name is allowed without replacing an existing owner category.
    if row.get('confirmed') and (set(changes)-{'counterparty'} or ('counterparty' in changes and row.get('merchant_id'))):status='protected'
    if desired['transaction_type'] in ('TRANSFER','SAVING','INVESTMENT','DEBT'):status='protected'
    if owner_confirmation and changes and not row.get('confirmed') and not desired['category_code']:
        status='needs_category'  # Existing owner reviews confirm the whole classification.
    amount=Decimal(str(row['amount']))
    if (desired['transaction_type']=='INCOME' and amount<0) or (desired['transaction_type'] in ('EXPENSE','TAX') and amount>0):status='protected'
    return dict(status=status,changes=changes,desired=desired)


def preview(cur,rule):
    validate_finance(cur,rule)
    cur.execute('SELECT count(*) AS n FROM finance.v_transactions')
    if cur.fetchone()['n']>MAX_SCAN:raise HTTPException(422,'recognizer_scan_limit')
    cur.execute('SELECT * FROM finance.v_transactions ORDER BY booking_date,id')
    rows=cur.fetchall();payloads=hydrate_many(cur,rows)
    cur.execute('SELECT id,code,parent_id,transaction_type,active FROM finance.finance_categories')
    categories=cur.fetchall();results=[]
    for row in rows:
        payload=payloads[str(row['id'])];decision=plan(row,payload,rule,categories,owner_confirmation=True)
        if decision:results.append((row,payload,decision))
    snapshot=fingerprint('recognition-preview-v1',[rule,[(str(r['id']),str(r.get('review_id')),d['status'],d['changes']) for r,_,d in results]])
    return results,snapshot


def save_and_apply(cur,rule,rid,previous,key,snapshot,scope,selection):
    validate_finance(cur,rule)
    digest=fingerprint('recognition-approve-v1',[rule,rid,previous,snapshot,scope,selection])
    cur.execute('SELECT id,payload_digest,applied_count FROM finance.finance_recognition_rule_events WHERE idempotency_key=%s',(key,))
    done=cur.fetchone()
    if done:
        if done['payload_digest']!=digest:raise HTTPException(409,'idempotency_conflict')
        return dict(status='saved',rule_id=rid,event_id=str(done['id']),applied=done['applied_count'])
    cur.execute('SELECT id FROM finance.finance_recognition_rule_events WHERE rule_id=%s ORDER BY sequence_no DESC LIMIT 1',(rid,))
    latest=cur.fetchone()
    if (str(latest['id']) if latest else None)!=previous:raise HTTPException(409,'recognition_rule_changed')
    results,actual=preview(cur,rule) if scope!='none' else ([],None)
    if scope!='none' and actual!=snapshot:raise HTTPException(409,'recognition_preview_changed')
    candidates={str(r['id']):(r,d) for r,_,d in results}
    if any(tid not in candidates or candidates[tid][1]['status']!='eligible' for tid in selection):raise HTTPException(409,'recognition_preview_changed')
    chosen=[(r,d) for r,_,d in results if d['status']=='eligible' and (scope=='all' or (scope=='selected' and str(r['id']) in selection))]
    merchant=merchant_id(cur,merchant_name(rule['set'].get('counterparty')))
    cur.execute('''INSERT INTO finance.finance_recognition_rule_events
        (rule_id,private_data,active,merchant_id,supersedes_event_id,idempotency_key,payload_digest,applied_count)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',(rid,encrypt(rule),rule['active'],merchant,previous,key,digest,len(chosen)))
    eid=cur.fetchone()['id']
    import uuid
    items=[]
    for row,decision in chosen:
        d=decision['desired']
        items.append((row['id'],d['category_code'],d['subcategory_code'],d['transaction_type'],
                      merchant if 'counterparty' in rule['set'] else row.get('merchant_id'),
                      str(uuid.uuid5(uuid.UUID(key),str(row['id']))),digest))
    insert_manual_batch(cur,items,recognition_rule_event_id=eid)
    return dict(status='saved',rule_id=rid,event_id=str(eid),applied=len(chosen))


def automatic(cur,row,rules=None,categories=None):
    """Same plan as preview, but never changes owner-confirmed transactions."""
    if row.get('confirmed'):return None
    if rules is None:rules=current(cur,active=True)
    if not rules:return None
    payload=hydrate_many(cur,[row])[str(row['id'])]
    if categories is None:
        cur.execute('SELECT id,code,parent_id,transaction_type,active FROM finance.finance_categories')
        categories=cur.fetchall()
    choices=[]
    for event in rules:
        decision=plan(row,payload,event['rule'],categories)
        if not decision:continue
        if decision['status'] not in ('eligible','aligned'):return {'blocked':True}
        desired={**decision['desired'],'merchant_id':event['merchant_id'] if 'counterparty' in event['rule']['set'] else row.get('merchant_id')}
        choices.append((event,decision,desired))
    if not choices:return None
    if len({signature(d) for _,_,d in choices})>1:return {'blocked':True}
    event,decision,desired=choices[0]
    if decision['status']=='aligned':return None
    return {**desired,'source':'RULE','confidence':None,'seed':None,'model_version':MODEL,
            'recognition_rule_event_id':event['id']}
