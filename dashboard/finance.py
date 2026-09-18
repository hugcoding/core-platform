"""Owner-only Finance API. Existing CORE serves layout and source identity."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time
import uuid

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from core.finance.crypto import canonical, decrypt, encrypt, fingerprint, secret
from core.finance.account_names import account_view, normalize_name
from core.finance.periods import period_bounds
from core.finance.suggestions import identity as merchant_identity, METHOD as SUGGESTION_METHOD, MAX_SCAN
from core.finance.store import connection, enqueue, event, publish_record, IMPORT_LOCK

router = APIRouter()
ASSETS = Path(__file__).parent/'static'
COOKIE = 'core_finance_session'
SESSION_TTL = 3600
_attempts = {}


def uid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError,TypeError):
        raise HTTPException(422,'invalid_id') from None


def owner(request):
    if os.getenv('CORE_FINANCE_ENABLED','false').lower() != 'true':
        raise HTTPException(503,'finance_disabled')
    try:
        value=Fernet(secret()['session_key'].encode()).decrypt(request.cookies.get(COOKIE,'').encode(),ttl=SESSION_TTL)
        if value != b'owner':
            raise ValueError()
    except (InvalidToken,ValueError,KeyError,OSError):
        raise HTTPException(401,'finance_locked') from None
    return 'owner'


async def finance_boundary(request, call_next):
    if not request.url.path.startswith('/api/v1/finance'):
        return await call_next(request)
    try:
        if request.method not in ('GET','HEAD'):
            # Require a browser same-origin JSON request (also protects login CSRF).
            if request.headers.get('origin') != str(request.base_url).rstrip('/'):
                raise HTTPException(403,'same_origin_required')
            if int(request.headers.get('content-length','0')) > 8192:
                raise HTTPException(413,'request_too_large')
        if request.url.path != '/api/v1/finance/session':
            owner(request)
        response=await call_next(request)
    except HTTPException as exc:
        response=JSONResponse({'detail':exc.detail},status_code=exc.status_code)
    except Exception:
        # Deliberately do not emit exception repr, SQL, path, request or bank data.
        response=JSONResponse({'detail':'finance_unavailable'},status_code=503)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    return response


@router.get('/corefinance')
def page():
    return FileResponse(ASSETS/'finance.html',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})


@router.post('/api/v1/finance/session')
def login(request: Request,payload:dict=Body(...)):
    if os.getenv('CORE_FINANCE_ENABLED','false').lower() != 'true':
        raise HTTPException(503,'finance_disabled')
    host=request.client.host if request.client else 'unknown'
    now=time.monotonic()
    recent=[t for t in _attempts.get(host,[]) if now-t<300]
    if len(recent)>=10:
        raise HTTPException(429,'try_later')
    _attempts[host]=recent+[now]
    supplied=str(payload.get('code',''))
    if not hmac.compare_digest(hashlib.sha256(supplied.encode()).hexdigest(),secret()['access_hash']):
        raise HTTPException(401,'invalid_code')
    _attempts.pop(host,None)
    response=JSONResponse({'status':'unlocked'})
    response.set_cookie(COOKIE,Fernet(secret()['session_key'].encode()).encrypt(b'owner').decode(),
        httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=SESSION_TTL,path='/api/v1/finance')
    return response


@router.delete('/api/v1/finance/session')
def logout():
    response=JSONResponse({'status':'locked'})
    response.delete_cookie(COOKIE,path='/api/v1/finance')
    return response


def serial(row):
    return {key:(str(value) if value is not None else None) for key,value in row.items()}


def transaction(row):
    result=serial(row)
    payload=decrypt(row['private_data'])
    result.pop('private_data',None)
    result.pop('fingerprint',None)
    result.update({key:payload[key] for key in ('description','counterparty','counteraccount','details')})
    return result


@router.get('/api/v1/finance/data')
def data(account:str='',month:str='',category:str='',page:int=0,sort:str='booking_date',direction:str='desc',year:str='',date_from:str='',date_to:str=''):
    columns={'booking_date':'t.booking_date','amount':'t.amount',
             'category':"lower(COALESCE(c.label,'Nog te categoriseren'))"}
    if sort not in (*columns,'counterparty','description') or direction not in ('asc','desc'):
        raise HTTPException(422,'invalid_sort')
    clauses,params=['true'],[]
    if account:
        clauses.append('t.account_id=%s'); params.append(uid(account))
    try:
        bounds=period_bounds(month,year,date_from,date_to)
    except ValueError:
        raise HTTPException(422,'invalid_period') from None
    if bounds:
        clauses.append('t.booking_date >= %s AND t.booking_date <= %s')
        params.extend(bounds)
    if category:
        if category=='uncategorized': clauses.append('t.category_code IS NULL')
        else: clauses.append('t.category_code=%s');params.append(category)
    if not 0<=page<=100000:
        raise HTTPException(422,'invalid_page')
    where=' AND '.join(clauses)
    with connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT a.id,a.private_data,n.id AS name_event_id,n.private_data AS name_data
            FROM finance.finance_accounts a LEFT JOIN LATERAL (
                SELECT id,private_data FROM finance.finance_account_name_events
                WHERE account_id=a.id ORDER BY sequence_no DESC LIMIT 1
            ) n ON true ORDER BY a.created_at,a.id""")
        accounts=[account_view(r) for r in cur.fetchall()]
        cur.execute('SELECT * FROM finance.finance_categories ORDER BY label')
        categories=cur.fetchall()
        cur.execute('SELECT DISTINCT to_char(booking_date,\'YYYY-MM\') AS month FROM finance.v_transactions ORDER BY month DESC')
        months=[r['month'] for r in cur.fetchall()]
        cur.execute(f'''SELECT count(*) AS total,coalesce(sum(amount) FILTER(WHERE amount>0),0) AS credits,
            coalesce(sum(amount) FILTER(WHERE amount<0),0) AS debits,coalesce(sum(amount),0) AS net,
            count(*) FILTER(WHERE category_code IS NULL) AS uncategorized FROM finance.v_transactions t WHERE {where}''',params)
        totals=serial(cur.fetchone())
        if sort in ('counterparty','description'):
            # Text remains encrypted at rest. Sort the complete filtered selection
            # locally, then paginate; never create a plaintext search/sort index.
            cur.execute(f'SELECT t.id,t.private_data FROM finance.v_transactions t WHERE {where} ORDER BY t.id',params)
            ranked=[(r['id'],str(decrypt(r['private_data']).get(sort) or '').casefold()) for r in cur.fetchall()]
            ranked.sort(key=lambda item:item[1],reverse=direction=='desc')
            ids=[str(item[0]) for item in ranked[page*100:(page+1)*100]]
            if ids:
                cur.execute('SELECT t.* FROM finance.v_transactions t WHERE t.id=ANY(%s::uuid[])',(ids,))
                by_id={str(r['id']):transaction(r) for r in cur.fetchall()}
                rows=[by_id[i] for i in ids]
            else: rows=[]
        else:
            # Date ties retain the original source order in either date direction.
            # The initial record remains stable even when duplicate evidence is added.
            joins=''
            tie_break='t.id'
            if sort=='booking_date':
                joins='''JOIN finance.finance_import_records r ON r.id=t.record_id
                    JOIN finance.finance_import_batches b ON b.id=r.batch_id
                    JOIN finance.finance_source_documents s ON s.id=b.source_id'''
                tie_break="""s.file_id ASC,
                    substring(r.locator from '^stmt:([0-9]+)/entry:')::integer ASC NULLS LAST,
                    substring(r.locator from '/entry:([0-9]+)$')::integer ASC NULLS LAST,t.id"""
            # SQL fragments are selected internally; user input is allowlisted above.
            cur.execute(f'''SELECT t.* FROM finance.v_transactions t {joins}
                LEFT JOIN finance.finance_categories c ON c.code=t.category_code WHERE {where}
                ORDER BY {columns[sort]} {direction} NULLS LAST,{tie_break} LIMIT 100 OFFSET %s''',params+[page*100])
            rows=[transaction(r) for r in cur.fetchall()]
        cur.execute('SELECT * FROM finance.v_import_status ORDER BY created_at DESC LIMIT 100')
        imports=[serial(r) for r in cur.fetchall()]
        cur.execute('SELECT * FROM finance.finance_ingest_jobs ORDER BY requested_at DESC LIMIT 5')
        jobs=[serial(r) for r in cur.fetchall()]
        cur.execute('''SELECT count(*) AS n FROM finance.finance_import_records r JOIN finance.v_import_status b ON b.id=r.batch_id
            WHERE r.initial_outcome='unresolved' AND b.status IN ('partial','imported')
            AND NOT EXISTS(SELECT 1 FROM finance.finance_duplicate_events e WHERE e.record_id=r.id)''')
        unresolved=cur.fetchone()['n']
    return {'accounts':accounts,'categories':categories,'months':months,'years':sorted({m[:4] for m in months},reverse=True),'totals':totals,'transactions':rows,
        'imports':imports,'jobs':jobs,'unresolved':unresolved,'page':page,'currency':'EUR','sort':sort,'direction':direction}


@router.post('/api/v1/finance/import')
def request_import():
    with connection() as conn, conn.cursor() as cur:
        job=enqueue(cur)
    return {'job_id':job,'status':'pending'}


@router.get('/api/v1/finance/transactions/{transaction_id}/sources')
def sources(transaction_id:str):
    with connection() as conn, conn.cursor() as cur:
        cur.execute('''SELECT s.id AS source_id,s.file_id,b.id AS batch_id,b.status,r.locator
            FROM finance.finance_transaction_sources link JOIN finance.finance_import_records r ON r.id=link.record_id
            JOIN finance.v_import_status b ON b.id=r.batch_id JOIN finance.finance_source_documents s ON s.id=b.source_id
            WHERE link.transaction_id=%s ORDER BY b.created_at''',(uid(transaction_id),))
        return {'sources':[serial(r) for r in cur.fetchall()]}


@router.get('/api/v1/finance/sources/{source_id}')
def original(source_id:str):
    with connection() as conn, conn.cursor() as cur:
        cur.execute('SELECT original_ciphertext FROM finance.finance_source_documents WHERE id=%s',(uid(source_id),))
        row=cur.fetchone()
        if not row: raise HTTPException(404,'source_not_found')
    # Exact original bytes, authenticated encrypted snapshot; never remote fetch.
    return Response(base64.b64decode(decrypt(row['original_ciphertext'])['bytes']),media_type='application/xml',
        headers={'Content-Disposition':'attachment; filename="core-finance-source.xml"'})


def replay(cur,table,key,digest):
    # Table name is only supplied as a fixed literal by internal callers.
    cur.execute(f'SELECT payload_digest FROM finance.{table} WHERE idempotency_key=%s',(uid(key),))
    row=cur.fetchone()
    if row and row['payload_digest']!=digest: raise HTTPException(409,'idempotency_conflict')
    return row is not None


@router.post('/api/v1/finance/accounts/{account_id}/name')
def rename_account(account_id:str,payload:dict=Body(...)):
    aid=uid(account_id); key=uid(payload.get('key'))
    expected=uid(payload['previous']) if payload.get('previous') else None
    try:
        name=normalize_name(payload.get('name'))
    except ValueError:
        raise HTTPException(422,'invalid_account_name') from None
    digest=fingerprint('account-name-review-v1',[aid,name,expected])
    with connection() as conn,conn.cursor() as cur:
        # Serialize retries, including accidental key reuse for another account.
        cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('finance-account-name-key:'+key,))
        if replay(cur,'finance_account_name_events',key,digest): return {'status':'saved'}
        cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('finance-account-name:'+aid,))
        cur.execute('SELECT 1 FROM finance.finance_accounts WHERE id=%s',(aid,))
        if not cur.fetchone(): raise HTTPException(404,'account_not_found')
        cur.execute("""SELECT id FROM finance.finance_account_name_events
            WHERE account_id=%s ORDER BY sequence_no DESC LIMIT 1""",(aid,))
        previous=cur.fetchone()
        if (str(previous['id']) if previous else None)!=expected:
            raise HTTPException(409,'account_name_changed')
        cur.execute("""INSERT INTO finance.finance_account_name_events
            (account_id,private_data,supersedes_event_id,actor,idempotency_key,payload_digest)
            VALUES (%s,%s,%s,'owner',%s,%s)""",
            (aid,encrypt({'display_name':name}),expected,key,digest))
    return {'status':'saved'}


@router.post('/api/v1/finance/transactions/{transaction_id}/category')
def categorize(transaction_id:str,payload:dict=Body(...)):
    tid=uid(transaction_id); key=uid(payload.get('key')); category=payload.get('category') or None
    expected=uid(payload['previous']) if payload.get('previous') else None
    digest=hashlib.sha256(canonical([tid,category,expected]).encode()).hexdigest()
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('finance-category-learning'))")
        cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(tid,))
        if replay(cur,'finance_review_events',key,digest): return {'status':'saved'}
        cur.execute('SELECT review_id FROM finance.v_transactions WHERE id=%s',(tid,))
        row=cur.fetchone()
        if not row: raise HTTPException(404,'transaction_not_found')
        if (str(row['review_id']) if row['review_id'] else None)!=expected: raise HTTPException(409,'review_changed')
        if category:
            cur.execute('SELECT 1 FROM finance.finance_categories WHERE code=%s',(category,))
            if not cur.fetchone(): raise HTTPException(422,'invalid_category')
        cur.execute('''INSERT INTO finance.finance_review_events(transaction_id,category_code,supersedes_event_id,actor,idempotency_key,payload_digest)
            VALUES (%s,%s,%s,'owner',%s,%s)''',(tid,category,expected,key,digest))
    return {'status':'saved'}


def category_suggestion_context(cur,seed_id):
    cur.execute("""SELECT t.*,r.source_review_id FROM finance.v_transactions t
        LEFT JOIN finance.finance_review_events r ON r.id=t.review_id WHERE t.id=%s""",(seed_id,))
    seed=cur.fetchone()
    if not seed or not seed['category_code'] or seed['source_review_id']:
        raise HTTPException(409,'suggestion_needs_manual_example')
    identity=merchant_identity(decrypt(seed['private_data']),seed['amount'],seed['currency'])
    if identity is None: return seed,[],'unsupported_pattern'
    cur.execute("""SELECT count(*) AS n FROM finance.v_transactions
        WHERE currency=%s AND (amount<0)=%s""",(seed['currency'],seed['amount']<0))
    if cur.fetchone()['n']>MAX_SCAN: raise HTTPException(422,'suggestion_scan_limit')
    cur.execute("""SELECT t.*,r.source_review_id FROM finance.v_transactions t
        LEFT JOIN finance.finance_review_events r ON r.id=t.review_id
        WHERE t.currency=%s AND (t.amount<0)=%s ORDER BY t.booking_date DESC,t.id""",
        (seed['currency'],seed['amount']<0))
    candidates=[]
    for row in cur.fetchall():
        if merchant_identity(decrypt(row['private_data']),row['amount'],row['currency'])!=identity: continue
        if row['category_code'] and row['source_review_id'] is None and row['category_code']!=seed['category_code']:
            return seed,[],'conflicting_examples'
        if row['category_code'] is None and row['id']!=seed['id']: candidates.append(row)
    return seed,candidates,identity[0]


@router.get('/api/v1/finance/transactions/{transaction_id}/suggestions')
def category_suggestions(transaction_id:str):
    with connection() as conn,conn.cursor() as cur:
        requested_id=uid(transaction_id)
        cur.execute("""SELECT t.id,r.source_review_id FROM finance.v_transactions t
            LEFT JOIN finance.finance_review_events r ON r.id=t.review_id WHERE t.id=%s""",(requested_id,))
        selected=cur.fetchone();source_review=selected['source_review_id'] if selected else None
        seed_id=requested_id
        if source_review:
            cur.execute("""SELECT t.id FROM finance.finance_review_events r
                JOIN finance.v_transactions t ON t.id=r.transaction_id AND t.review_id=r.id
                WHERE r.id=%s AND r.source_review_id IS NULL""",(source_review,))
            original=cur.fetchone()
            if not original: raise HTTPException(409,'suggestion_example_changed')
            seed_id=str(original['id'])
        seed,rows,reason=category_suggestion_context(cur,seed_id)
        if source_review and str(seed['review_id'])!=str(source_review):
            raise HTTPException(409,'suggestion_example_changed')
        return {'seed_transaction_id':str(seed['id']),'seed_review_id':str(seed['review_id']),
            'category_code':seed['category_code'],'method':SUGGESTION_METHOD,'reason':reason,
            'from_original_example':bool(source_review),'total':len(rows),'transactions':[transaction(r) for r in rows[:50]]}


@router.post('/api/v1/finance/transactions/{transaction_id}/suggestion')
def accept_category_suggestion(transaction_id:str,payload:dict=Body(...)):
    tid=uid(transaction_id);seed_id=uid(payload.get('seed_transaction_id'))
    seed_review=uid(payload.get('seed_review_id'));key=uid(payload.get('key'))
    expected=uid(payload['previous']) if payload.get('previous') else None
    digest=fingerprint('category-suggestion-v1',[tid,seed_id,seed_review,expected,SUGGESTION_METHOD])
    with connection() as conn,conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('finance-category-learning'))")
        if replay(cur,'finance_review_events',key,digest): return {'status':'saved'}
        seed,rows,reason=category_suggestion_context(cur,seed_id)
        target=next((r for r in rows if str(r['id'])==tid),None)
        if str(seed['review_id'])!=seed_review or target is None:
            raise HTTPException(409,'suggestion_changed')
        if (str(target['review_id']) if target['review_id'] else None)!=expected:
            raise HTTPException(409,'suggestion_changed')
        cur.execute("""INSERT INTO finance.finance_review_events
            (transaction_id,category_code,supersedes_event_id,actor,idempotency_key,payload_digest,source_review_id,suggestion_method)
            VALUES (%s,%s,%s,'owner',%s,%s,%s,%s)""",
            (tid,seed['category_code'],expected,key,digest,seed_review,SUGGESTION_METHOD))
    return {'status':'saved'}


@router.post('/api/v1/finance/suggestions/approve')
def approve_category_selection(payload:dict=Body(...)):
    seed_id=uid(payload.get('seed_transaction_id'));seed_review=uid(payload.get('seed_review_id'))
    batch_key=uuid.UUID(uid(payload.get('key')))
    items=payload.get('items')
    if not isinstance(items,list) or not 1<=len(items)<=50 or any(not isinstance(i,dict) for i in items):
        raise HTTPException(422,'invalid_selection')
    selected=sorted([(uid(i.get('id')),uid(i['previous']) if i.get('previous') else None) for i in items],key=lambda item:item[0])
    if len({tid for tid,_ in selected})!=len(selected): raise HTTPException(422,'invalid_selection')
    digest=fingerprint('category-selection-v1',[seed_id,seed_review,selected,SUGGESTION_METHOD])
    keys=[str(uuid.uuid5(batch_key,str(i))) for i in range(len(selected))]
    with connection() as conn,conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('finance-category-learning'))")
        done=[replay(cur,'finance_review_events',key,digest) for key in keys]
        if all(done): return {'status':'saved','count':len(selected)}
        if any(done): raise HTTPException(409,'idempotency_conflict')
        seed,rows,_=category_suggestion_context(cur,seed_id)
        candidates={str(r['id']):r for r in rows}
        if str(seed['review_id'])!=seed_review: raise HTTPException(409,'suggestion_changed')
        for tid,expected in selected:
            target=candidates.get(tid)
            if target is None or (str(target['review_id']) if target['review_id'] else None)!=expected:
                raise HTTPException(409,'suggestion_changed')
        for (tid,expected),key in zip(selected,keys):
            cur.execute("""INSERT INTO finance.finance_review_events
                (transaction_id,category_code,supersedes_event_id,actor,idempotency_key,payload_digest,source_review_id,suggestion_method)
                VALUES (%s,%s,%s,'owner',%s,%s,%s,%s)""",
                (tid,seed['category_code'],expected,key,digest,seed_review,SUGGESTION_METHOD))
    return {'status':'saved','count':len(selected)}


@router.get('/api/v1/finance/unresolved')
def unresolved():
    with connection() as conn, conn.cursor() as cur:
        cur.execute('''SELECT r.* FROM finance.finance_import_records r JOIN finance.v_import_status b ON b.id=r.batch_id
            WHERE r.initial_outcome='unresolved' AND b.status='partial'
            AND NOT EXISTS(SELECT 1 FROM finance.finance_duplicate_events e WHERE e.record_id=r.id)
            ORDER BY r.created_at,r.id LIMIT 50''')
        records=cur.fetchall(); result=[]
        for r in records:
            cur.execute('''SELECT id,booking_date,amount FROM finance.v_transactions
                WHERE account_id=%s AND fingerprint=%s ORDER BY created_at LIMIT 50''',(r['account_id'],r['fingerprint']))
            result.append({'id':str(r['id']),'locator':r['locator'],**decrypt(r['private_data']),
                'candidates':[serial(c) for c in cur.fetchall()]})
    return {'records':result}


@router.post('/api/v1/finance/unresolved/{record_id}')
def resolve(record_id:str,payload:dict=Body(...)):
    rid=uid(record_id); key=uid(payload.get('key')); choice=payload.get('decision')
    tid=uid(payload['transaction_id']) if payload.get('transaction_id') else None
    if choice not in ('same','distinct') or (choice=='same' and not tid): raise HTTPException(422,'invalid_decision')
    digest=hashlib.sha256(canonical([rid,choice,tid]).encode()).hexdigest()
    with connection() as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)',(IMPORT_LOCK,))
        if replay(cur,'finance_duplicate_events',key,digest): return {'status':'saved'}
        cur.execute('''SELECT r.* FROM finance.finance_import_records r JOIN finance.v_import_status b ON b.id=r.batch_id
            WHERE r.id=%s AND r.initial_outcome='unresolved' AND b.status='partial'
            AND NOT EXISTS(SELECT 1 FROM finance.finance_duplicate_events e WHERE e.record_id=r.id)''',(rid,))
        record=cur.fetchone()
        if not record: raise HTTPException(409,'record_not_pending')
        if choice=='same':
            cur.execute('SELECT id FROM finance.v_transactions WHERE id=%s AND account_id=%s AND fingerprint=%s',
                (tid,record['account_id'],record['fingerprint']))
            if not cur.fetchone(): raise HTTPException(409,'candidate_changed')
            cur.execute('INSERT INTO finance.finance_transaction_sources(record_id,transaction_id) VALUES (%s,%s)',(rid,tid))
        else: tid=publish_record(cur,record,decrypt(record['private_data']))
        cur.execute('''INSERT INTO finance.finance_duplicate_events(record_id,transaction_id,decision,actor,idempotency_key,payload_digest)
            VALUES (%s,%s,%s,'owner',%s,%s)''',(rid,tid,choice,key,digest))
        cur.execute('''SELECT count(*) AS n FROM finance.finance_import_records r WHERE batch_id=%s AND initial_outcome='unresolved'
            AND NOT EXISTS(SELECT 1 FROM finance.finance_duplicate_events e WHERE e.record_id=r.id)''',(record['batch_id'],))
        remaining=cur.fetchone()['n']
        cur.execute('SELECT count(*) AS n FROM finance.finance_import_records WHERE batch_id=%s',(record['batch_id'],))
        count=cur.fetchone()['n']
        event(cur,record['batch_id'],'partial' if remaining else 'imported',count,remaining,actor='owner',key='review:'+key)
    return {'status':'saved'}


@router.post('/api/v1/finance/imports/{batch_id}/rollback')
def rollback(batch_id:str,payload:dict=Body(...)):
    bid=uid(batch_id)
    if payload.get('confirm') is not True: raise HTTPException(422,'confirmation_required')
    with connection() as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)',(IMPORT_LOCK,))
        cur.execute('SELECT * FROM finance.v_import_status WHERE id=%s',(bid,))
        row=cur.fetchone()
        if not row: raise HTTPException(404,'batch_not_found')
        if row['status']=='rolled_back': return {'status':'rolled_back'}
        if row['status'] not in ('partial','imported'): raise HTTPException(409,'batch_not_imported')
        event(cur,bid,'rolled_back',row['records'],row['unresolved'],actor='owner')
    return {'status':'rolled_back'}
