"""Small atomic imports. No bank fields in logs or exception text."""
import base64
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import os
from pathlib import Path
import stat
import uuid
import unicodedata

import psycopg2
from psycopg2.extras import RealDictCursor
from core.finance import camt
from core.finance.crypto import encrypt, fingerprint
from core.finance.privacy import source_root

ADMISSION_LOCK = 118202609
IMPORT_LOCK = 118202610


@contextmanager
def connection(worker=False):
    conn = psycopg2.connect(host=os.environ['DB_HOST'],port=os.getenv('DB_PORT','5432'),
        user=os.environ['DB_USER'], password=os.environ['DB_PASS'],dbname=os.environ['DB_NAME'],
        cursor_factory=RealDictCursor,connect_timeout=5,
        options='-c statement_timeout=15000 -c lock_timeout=1000 -c jit=off')
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute('SET LOCAL ROLE '+('core_finance_ingest' if worker else 'core_finance_api'))
            yield conn
    finally:
        conn.close()


def read_source(path):
    root = source_root().resolve(strict=True)
    path = Path(path)
    if path.suffix.lower() != '.xml' or path.is_symlink() or not path.resolve().is_relative_to(root):
        raise camt.ImportErrorCode('unsafe_source_path')
    # Never follow symlink components, including a directory replaced during discovery.
    current = path
    while current != source_root() and current != current.parent:
        if current.is_symlink():
            raise camt.ImportErrorCode('unsafe_source_path')
        current = current.parent
    if os.name == 'posix':
        # Open every component relative to an already opened directory. A path
        # swap cannot redirect the source read outside the configured root.
        parts=path.relative_to(source_root()).parts
        directory_fd=os.open(source_root(),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            for part in parts[:-1]:
                next_fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory_fd)
                os.close(directory_fd);directory_fd=next_fd
            fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory_fd)
        finally:
            os.close(directory_fd)
    else:
        fd = os.open(path, os.O_RDONLY | getattr(os,'O_NOFOLLOW',0))
    with os.fdopen(fd, 'rb') as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= camt.MAX_BYTES:
            raise camt.ImportErrorCode('source_size_limit')
        data = handle.read(camt.MAX_BYTES+1)
        after = os.fstat(handle.fileno())
    latest = path.stat()
    if ((before.st_ino,before.st_size,before.st_mtime_ns) != (after.st_ino,after.st_size,after.st_mtime_ns)
        or (before.st_ino,before.st_size,before.st_mtime_ns) != (latest.st_ino,latest.st_size,latest.st_mtime_ns)):
        raise camt.ImportErrorCode('source_changed')
    return data


def event(cur, batch_id, status, records=0, unresolved=0, reason='', actor='finance-worker', key=None):
    cur.execute('''INSERT INTO finance.finance_import_events
      (batch_id,status,reason_code,records,unresolved,actor,idempotency_key) VALUES (%s,%s,%s,%s,%s,%s,%s)
      ON CONFLICT(idempotency_key) DO NOTHING''',
      (batch_id,status,reason,records,unresolved,actor,key or f'{batch_id}:{status}'))


def register_source(cur, path, data):
    digest = hashlib.sha256(data).hexdigest()
    cur.execute('SELECT id FROM public.files WHERE path=%s', (str(path),))
    row = cur.fetchone()
    if row:
        file_id = row['id']
    else:
        cur.execute('INSERT INTO public.folders(path) VALUES (%s) ON CONFLICT(path) DO NOTHING', (str(path.parent),))
        cur.execute('SELECT id FROM public.folders WHERE path=%s', (str(path.parent),))
        folder_id = cur.fetchone()['id']
        cur.execute('''INSERT INTO public.files(folder_id,filename,path,extension,size_bytes,mime_type,source,content_sha256)
            VALUES (%s,%s,%s,'xml',%s,'application/xml','finance',%s) ON CONFLICT(path) DO NOTHING''',
            (folder_id,path.name,str(path),len(data),digest))
        cur.execute('SELECT id FROM public.files WHERE path=%s', (str(path),))
        file_id = cur.fetchone()['id']
    cur.execute('''SELECT 1 FROM finance.finance_source_occurrences o JOIN finance.finance_source_documents s ON s.id=o.source_id
        WHERE o.file_id=%s AND s.content_sha256<>%s''', (file_id,digest))
    if cur.fetchone():
        raise camt.ImportErrorCode('registered_source_changed')
    cur.execute('''SELECT id FROM finance.finance_source_documents WHERE content_sha256=%s AND size_bytes=%s''',(digest,len(data)))
    row = cur.fetchone()
    if row:
        source_id = row['id']
    else:
        cur.execute('''INSERT INTO finance.finance_source_documents(file_id,content_sha256,size_bytes,original_ciphertext)
            VALUES (%s,%s,%s,%s) RETURNING id''',
            (file_id,digest,len(data),encrypt({'bytes':base64.b64encode(data).decode()})))
        source_id = cur.fetchone()['id']
    cur.execute('''INSERT INTO finance.finance_source_occurrences(source_id,file_id) VALUES (%s,%s)
        ON CONFLICT DO NOTHING''',(source_id,file_id))
    return source_id


def entry_fingerprint(entry, account):
    # Stable across files. NOT unique: identical legitimate payments are possible.
    values = {key:getattr(entry,key) for key in ('booking_date','value_date','amount','currency','description','counteraccount')}
    values['account'] = str(account)
    values['description'] = unicodedata.normalize('NFC', values['description'])
    return fingerprint('transaction-candidate-v1', values)


def publish_record(cur, record, payload):
    cur.execute('''INSERT INTO finance.finance_transactions(record_id,account_id,booking_date,value_date,amount,currency,fingerprint,private_data)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
        (record['id'],record['account_id'],payload['booking_date'],payload['value_date'],payload['amount'],payload['currency'],
         record['fingerprint'],record['private_data']))
    transaction_id = cur.fetchone()['id']
    cur.execute('INSERT INTO finance.finance_transaction_sources(record_id,transaction_id) VALUES (%s,%s)',(record['id'],transaction_id))
    return transaction_id


def import_bytes(conn, path, data):
    """Caller owns transaction and admission lock; each complete file commits once."""
    try:
        parsed = camt.parse(data)
        error = None
    except camt.ImportErrorCode as exc:
        parsed, error = None, str(exc)
    with conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)', (IMPORT_LOCK,))
        source = register_source(cur, path, data)
        cur.execute('SELECT * FROM finance.v_import_status WHERE source_id=%s AND parser_version=%s',(source,camt.VERSION))
        existing = cur.fetchone()
        if existing:
            return {'status':existing['status'],'replay':True}
        cur.execute('INSERT INTO finance.finance_import_batches(source_id,parser_version) VALUES (%s,%s) RETURNING id',(source,camt.VERSION))
        batch = cur.fetchone()['id']
        event(cur,batch,'received')
        if error:
            event(cur,batch,'rejected',reason=error)
            return {'status':'rejected','reason_code':error}
        event(cur,batch,'validated',reason='balances_checked' if parsed.balances_checked==parsed.statements else 'balances_unavailable')
        accounts = {}
        for account in parsed.accounts:
            identity = fingerprint('account-v1',account)
            cur.execute('INSERT INTO finance.finance_accounts(identity_key,private_data) VALUES (%s,%s) ON CONFLICT DO NOTHING',
                (identity,encrypt({'iban':account,'label':'Rekening •'+account[-4:]})))
            cur.execute('SELECT id FROM finance.finance_accounts WHERE identity_key=%s',(identity,))
            accounts[account] = cur.fetchone()['id']
        unresolved = 0
        for entry in parsed.entries:
            account = accounts[entry.account]
            match = entry_fingerprint(entry,account)
            # Look outside this file: repeated equal entries IN a file preserve multiplicity.
            cur.execute('''SELECT 1 FROM finance.finance_import_records r JOIN finance.v_import_status b ON b.id=r.batch_id
                WHERE r.account_id=%s AND r.fingerprint=%s AND r.batch_id<>%s
                AND b.status IN ('imported','partial','rolled_back') LIMIT 1''',(account,match,batch))
            ambiguous = cur.fetchone() is not None
            payload = asdict(entry)
            # Account identifier is already in the encrypted account table.
            payload.pop('account')
            cur.execute('''INSERT INTO finance.finance_import_records(batch_id,locator,account_id,fingerprint,private_data,initial_outcome)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING *''',
                (batch,entry.locator,account,match,encrypt(payload),'unresolved' if ambiguous else 'new'))
            record = cur.fetchone()
            if ambiguous:
                unresolved += 1
            else:
                publish_record(cur,record,payload)
        status = 'partial' if unresolved else 'imported'
        event(cur,batch,status,len(parsed.entries),unresolved)
        return {'status':status,'records':len(parsed.entries),'unresolved':unresolved,'replay':False}


def enqueue(cur):
    cur.execute('''INSERT INTO finance.finance_ingest_jobs DEFAULT VALUES
        ON CONFLICT DO NOTHING RETURNING id''')
    row = cur.fetchone()
    if not row:
        cur.execute("SELECT id FROM finance.finance_ingest_jobs WHERE status IN ('pending','running')")
        row=cur.fetchone()
    return str(row['id'])
