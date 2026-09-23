"""Bank-reported snapshots, never inferred from an incomplete transaction list."""
import base64
from decimal import Decimal

from core.finance import camt
from core.finance.crypto import decrypt, encrypt, fingerprint


def persist(cur, batch, parsed):
    cur.execute('''INSERT INTO finance.finance_balance_extractions(batch_id,extractor_version,status)
        VALUES (%s,'camt-balances-v1',%s) ON CONFLICT DO NOTHING RETURNING batch_id''',
        (batch, 'extracted' if parsed is not None else 'unavailable'))
    if not cur.fetchone():
        return
    for balance in parsed.bank_balances if parsed else ():
        cur.execute('SELECT id FROM finance.finance_accounts WHERE identity_key=%s',
                    (fingerprint('account-v1', balance['account']),))
        account = cur.fetchone()
        if not account:
            raise ValueError('balance_account_missing')
        payload = {k: v for k, v in balance.items() if k not in ('account', 'locator')}
        cur.execute('''INSERT INTO finance.finance_bank_balances(batch_id,account_id,locator,private_data)
            VALUES (%s,%s,%s,%s)''', (batch, account['id'], balance['locator'], encrypt(payload)))


def backfill_one(conn):
    """Called only under worker admission/resource gate. One immutable source per commit."""
    from core.finance.store import IMPORT_LOCK
    with conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)', (IMPORT_LOCK,))
        cur.execute('''SELECT b.id,s.original_ciphertext FROM finance.v_import_status b
            JOIN finance.finance_source_documents s ON s.id=b.source_id
            WHERE b.status IN ('imported','partial') AND NOT EXISTS
            (SELECT 1 FROM finance.finance_balance_extractions e WHERE e.batch_id=b.id)
            ORDER BY b.created_at,b.id LIMIT 1''')
        row = cur.fetchone()
        if not row:
            return False
        try:
            parsed = camt.parse(base64.b64decode(decrypt(row['original_ciphertext'])['bytes'], validate=True))
        except camt.ImportErrorCode:
            parsed = None
        persist(cur, row['id'], parsed)
        return True


def summarize(accounts, snapshots, end=None, pending=0):
    rows = []
    for account in accounts:
        candidates = [s for s in snapshots if s['account_id'] == account['id']
                      and s.get('closing_date') and (not end or s['closing_date'] <= end)
                      and (not s.get('opening_date') or s['opening_date'] <= s['closing_date'])]
        item = {'account_id': account['id'], 'label': account['label'], 'status': 'unavailable'}
        if candidates:
            latest = max(s['closing_date'] for s in candidates)
            at_date = [s for s in candidates if s['closing_date'] == latest]
            if len({Decimal(s['closing']) for s in at_date}) != 1:
                item.update(status='conflict', closing_date=latest)
            else:
                chosen = max(at_date, key=lambda s: (s.get('opening_date') or '', s['source_id'], s['locator']))
                item.update(chosen, status='reported')
        rows.append(item)
    complete = bool(rows) and not pending and all(r['status'] == 'reported' for r in rows)
    same_date = complete and len({r['closing_date'] for r in rows}) == 1
    return {'accounts': rows, 'pending': pending, 'as_of': rows[0]['closing_date'] if same_date else None,
            'total': format(sum(Decimal(r['closing']) for r in rows), '.2f') if same_date else None,
            'requested_end': end}


def overview(cur, accounts, end=None):
    cur.execute('''SELECT s.account_id,s.locator,s.private_data,b.source_id
        FROM finance.finance_bank_balances s JOIN finance.v_import_status b ON b.id=s.batch_id
        WHERE b.status IN ('imported','partial') AND s.account_id=ANY(%s::uuid[])''',
        ([a['id'] for a in accounts],))
    snapshots = [{**decrypt(r['private_data']), 'account_id': str(r['account_id']),
                  'source_id': str(r['source_id']), 'locator': r['locator']} for r in cur.fetchall()]
    cur.execute('''SELECT count(*) AS n FROM finance.v_import_status b WHERE b.status IN ('imported','partial')
        AND NOT EXISTS(SELECT 1 FROM finance.finance_balance_extractions e WHERE e.batch_id=b.id)''')
    return summarize(accounts, snapshots, end, cur.fetchone()['n'])
