"""ASN account-scoped NtryRef identity. No external calls or bank data in logs."""
import base64
import uuid

from core.finance import camt
from core.finance.crypto import decrypt, encrypt, fingerprint

PROFILE = 'asn-ntryref-v1'
# ASN-family Dutch account codes covered by the ASN export profile. Other banks
# keep conservative matching; CAMT syntax alone is not a bank identity guarantee.
ASN_CODES = {'ASNB', 'SNSB', 'RBRB'}


def usable(entry):
    return (entry.account.startswith('NL') and entry.account[4:8] in ASN_CODES
            and bool(entry.entry_reference)
            and entry.entry_reference.upper() not in {'NOTPROVIDED', 'NONREF', 'N/A'})


def persist(cur, record, entry):
    if not usable(entry):
        return False
    identity = fingerprint(PROFILE, [str(record['account_id']), entry.entry_reference])
    cur.execute('''INSERT INTO finance.finance_record_bank_references(record_id,account_id,profile,identity_key,private_data)
        VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
        (record['id'], record['account_id'], PROFILE, identity, encrypt({'entry_reference': entry.entry_reference})))
    return True


def mark_extracted(cur, batch, status='indexed'):
    cur.execute('''INSERT INTO finance.finance_reference_extractions(batch_id,version,status)
        VALUES (%s,%s,%s) ON CONFLICT DO NOTHING''', (batch, PROFILE, status))


def backfill_one(conn):
    """Index all old evidence before attempting any automatic resolution."""
    from core.finance.store import IMPORT_LOCK, entry_fingerprint
    with conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)', (IMPORT_LOCK,))
        cur.execute('''SELECT b.id,s.original_ciphertext FROM finance.v_import_status b
            JOIN finance.finance_source_documents s ON s.id=b.source_id
            WHERE b.status IN ('imported','partial','rolled_back') AND NOT EXISTS
            (SELECT 1 FROM finance.finance_reference_extractions x WHERE x.batch_id=b.id)
            ORDER BY b.created_at,b.id LIMIT 1''')
        batch = cur.fetchone()
        if not batch:
            return False
        try:
            parsed = camt.parse(base64.b64decode(decrypt(batch['original_ciphertext'])['bytes'], validate=True))
        except camt.ImportErrorCode:
            mark_extracted(cur, batch['id'], 'unavailable')
            return True
        cur.execute('''SELECT r.*,a.identity_key AS account_key FROM finance.finance_import_records r
            JOIN finance.finance_accounts a ON a.id=r.account_id WHERE r.batch_id=%s''', (batch['id'],))
        records = {r['locator']: r for r in cur.fetchall()}
        if len(records) != len(parsed.entries) or any(
            e.locator not in records or records[e.locator]['account_key'] != fingerprint('account-v1', e.account)
            or records[e.locator]['fingerprint'] != entry_fingerprint(e, records[e.locator]['account_id'])
            for e in parsed.entries):
            mark_extracted(cur, batch['id'], 'unavailable')
            return True
        for entry in parsed.entries:
            persist(cur, records[entry.locator], entry)
        mark_extracted(cur, batch['id'])
        return True


def resolve_record(cur, record):
    """Caller holds IMPORT_LOCK. Never replace a manual decision or merge ledgers."""
    from core.finance.store import publish_record
    cur.execute('SELECT * FROM finance.finance_record_bank_references WHERE record_id=%s', (record['id'],))
    ref = cur.fetchone()
    if not ref:
        return False
    cur.execute('SELECT 1 FROM finance.finance_duplicate_events WHERE record_id=%s', (record['id'],))
    if cur.fetchone():
        return False
    # Same number with differing immutable content is a conflict, not an update.
    cur.execute('''SELECT 1 FROM finance.finance_record_bank_references k
        JOIN finance.finance_import_records r ON r.id=k.record_id
        WHERE k.account_id=%s AND k.identity_key=%s AND r.fingerprint<>%s LIMIT 1''',
        (ref['account_id'], ref['identity_key'], record['fingerprint']))
    if cur.fetchone():
        return False
    cur.execute('''SELECT DISTINCT t.id FROM finance.finance_record_bank_references k
        JOIN finance.finance_transaction_sources s ON s.record_id=k.record_id
        JOIN finance.finance_transactions t ON t.id=s.transaction_id
        WHERE k.account_id=%s AND k.identity_key=%s LIMIT 2''', (ref['account_id'], ref['identity_key']))
    candidates = cur.fetchall()
    if len(candidates) > 1:
        return False
    if candidates:
        tid = candidates[0]['id']
        cur.execute('INSERT INTO finance.finance_transaction_sources(record_id,transaction_id) VALUES (%s,%s)',
                    (record['id'], tid))
        decision = 'same'
    else:
        # An unindexed/numberless old lookalike can still be the same payment.
        cur.execute('''SELECT 1 FROM finance.finance_import_records r WHERE r.account_id=%s
            AND r.fingerprint=%s AND r.id<>%s AND NOT EXISTS
            (SELECT 1 FROM finance.finance_record_bank_references k WHERE k.record_id=r.id) LIMIT 1''',
            (record['account_id'], record['fingerprint'], record['id']))
        if cur.fetchone():
            return False
        tid = publish_record(cur, record, decrypt(record['private_data']))
        decision = 'distinct'
    key = str(uuid.uuid5(uuid.NAMESPACE_URL, PROFILE+':'+str(record['id'])))
    cur.execute('''INSERT INTO finance.finance_duplicate_events
        (record_id,transaction_id,decision,actor,idempotency_key,payload_digest) VALUES (%s,%s,%s,%s,%s,%s)''',
        (record['id'], tid, decision, PROFILE, key, fingerprint(PROFILE, [str(record['id']), str(tid), decision])))
    return True


def reconcile_chunk(conn, after=None, limit=100):
    """Bounded seek, including conflicts only once per run; admission gate per chunk."""
    from core.finance.store import IMPORT_LOCK, event
    with conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)', (IMPORT_LOCK,))
        cur.execute('''SELECT r.* FROM finance.finance_import_records r
            JOIN finance.finance_record_bank_references k ON k.record_id=r.id
            JOIN finance.v_import_status b ON b.id=r.batch_id
            WHERE r.initial_outcome='unresolved' AND b.status IN ('partial','imported')
            AND (%s::uuid IS NULL OR r.id>%s::uuid)
            AND NOT EXISTS(SELECT 1 FROM finance.finance_duplicate_events d WHERE d.record_id=r.id)
            ORDER BY r.id LIMIT %s''', (after, after, limit))
        records = cur.fetchall()
        changed = set()
        for record in records:
            if resolve_record(cur, record):
                changed.add(record['batch_id'])
        for batch in changed:
            cur.execute('''SELECT count(*) AS n, count(*) FILTER (WHERE r.initial_outcome='unresolved'
                AND NOT EXISTS(SELECT 1 FROM finance.finance_duplicate_events d WHERE d.record_id=r.id)) AS remaining
                FROM finance.finance_import_records r WHERE batch_id=%s''', (batch,))
            counts = cur.fetchone()
            event(cur, batch, 'partial' if counts['remaining'] else 'imported', counts['n'], counts['remaining'],
                  reason='bank_reference_reconciled', actor=PROFILE, key=f"{PROFILE}:{batch}:{counts['remaining']}")
        return str(records[-1]['id']) if records else None
