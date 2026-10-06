"""Versioned, conservative bank evidence. No descriptions, AI or logging."""
import base64
from decimal import Decimal
from core.finance import camt
from core.finance.crypto import decrypt, encrypt, fingerprint

VERSION = 'bank-type-v1'
UNKNOWN = ('UNKNOWN', 'insufficient_bank_evidence')
ASN_BANKS = {'ASNB', 'SNSB', 'RBRB'}
CARD_DEBITS = {str(n+offset) for start in (7903,7913,7923) for n in range(start,start+6) for offset in (0,2000)}
CARD_CREDITS = {str(n+offset) for start in (6903,6913,6923) for n in range(start,start+6) for offset in (0,2000)}
RETURNS = {'7909','9909','7920','9920','6909','8909','6920','8920','9715','9716','9717','8715','8716','8717','7225','6606','6230'}
FEES = {'7617','7628','7614','7626','7642','7643','7261','7262','7615','7627','7241','7260','7734','7737','7738','7741','7236','7240','7263','7227','7259','7228','7237','7921','9921','7264','7922','9922'}


def code_type(code, amount, asn):
    number = code.get('proprietary','')
    if asn:
        if number in RETURNS: return ('CORRECTION','bank_return')
        if number in CARD_DEBITS and amount < 0: return ('EXPENSE','card_payment')
        if number in CARD_CREDITS and amount > 0: return ('CORRECTION','card_refund')
        if number in {'9714','9827','9885'} and amount < 0: return ('EXPENSE','direct_debit')
        if number in {'7606','7618','7600','7602','7604'} and amount < 0: return ('EXPENSE','interest_paid')
        if number in {'6607','6619','6600','6602','6604'} and amount > 0: return ('INCOME','interest_received')
        if number in FEES and amount < 0: return ('EXPENSE','bank_fee')
        if number in {'6617','6628'} and amount > 0: return ('CORRECTION','fee_refund')
    iso = tuple(code.get(k,'') for k in ('domain','family','subfamily'))
    if iso == ('PMNT','CCRD','POSD'):
        return ('EXPENSE','card_payment') if amount < 0 else ('CORRECTION','card_refund')
    if iso == ('PMNT','CCRD','RIMB'): return ('CORRECTION','bank_return')
    if iso[0] == 'PMNT' and iso[1] in {'IDDT','RDDT'} and iso[2] in {'UPDD','PRDD'}:
        return ('CORRECTION','bank_return')
    if iso[0:2] == ('PMNT','RDDT') and iso[2] in {'ESDD','BBDD','PMDD'} and amount < 0:
        return ('EXPENSE','direct_debit')
    if iso == ('ACMT','MDOP','CHRG') and amount < 0: return ('EXPENSE','bank_fee')
    if iso == ('ACMT','MCOP','CHRG') and amount > 0: return ('CORRECTION','fee_refund')
    # Generic INTR includes ASN interest corrections: require its precise bank code.
    return UNKNOWN


def recognize(entry):
    amount = Decimal(entry.amount)
    if not amount: return UNKNOWN
    if entry.reversal.upper() in {'YES','TRUE','1'}: return ('CORRECTION','bank_reversal')
    if entry.reversal.upper() not in {'','NO','FALSE','0'}: return UNKNOWN
    if len(entry.details) > 1: return ('UNKNOWN','aggregate_entry')
    choices = {code_type(c, amount, entry.account[4:8] in ASN_BANKS) for c in entry.bank_codes}
    known = {c[0] for c in choices if c[0] != 'UNKNOWN'}
    if len(known) > 1: return ('UNKNOWN','conflicting_bank_evidence')
    return sorted(c for c in choices if c[0] != 'UNKNOWN')[0] if known else UNKNOWN


def persist(cur, record, entry=None):
    kind, reason = recognize(entry) if entry else ('UNKNOWN','source_unavailable')
    metadata = {'codes': entry.bank_codes, 'reversal': entry.reversal} if entry else {}
    cur.execute('''INSERT INTO finance.finance_record_bank_types
        (record_id,version,transaction_type,reason_code,private_data) VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING''', (record['id'],VERSION,kind,reason,encrypt(metadata)))


def backfill_one(conn):
    """One original source per admitted transaction; no new imports or ledger edits."""
    from core.finance.store import IMPORT_LOCK, entry_fingerprint
    with conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)', (IMPORT_LOCK,))
        cur.execute('''SELECT b.id,s.original_ciphertext FROM finance.v_import_status b
            JOIN finance.finance_source_documents s ON s.id=b.source_id
            WHERE b.status IN ('imported','partial','rolled_back') AND EXISTS
            (SELECT 1 FROM finance.finance_import_records r WHERE r.batch_id=b.id AND NOT EXISTS
             (SELECT 1 FROM finance.finance_record_bank_types k WHERE k.record_id=r.id AND k.version=%s))
            ORDER BY b.created_at,b.id LIMIT 1''', (VERSION,))
        batch = cur.fetchone()
        if not batch: return False
        cur.execute('''SELECT r.*,a.identity_key AS account_key FROM finance.finance_import_records r
            JOIN finance.finance_accounts a ON a.id=r.account_id WHERE r.batch_id=%s''', (batch['id'],))
        records = {r['locator']: r for r in cur.fetchall()}
        try:
            parsed = camt.parse(base64.b64decode(decrypt(batch['original_ciphertext'])['bytes'],validate=True))
        except camt.ImportErrorCode:
            for record in records.values(): persist(cur, record)
            return True
        valid = len(records) == len(parsed.entries) and all(
            e.locator in records and records[e.locator]['account_key'] == fingerprint('account-v1', e.account)
            and records[e.locator]['fingerprint'] == entry_fingerprint(e,records[e.locator]['account_id'])
            for e in parsed.entries)
        if valid:
            for entry in parsed.entries: persist(cur, records[entry.locator], entry)
        else:
            for record in records.values(): persist(cur, record)
        return True
