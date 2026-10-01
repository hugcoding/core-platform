"""Deterministic recurrence evidence; never classification or financial truth."""
from calendar import monthrange
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from statistics import median

from core.finance.crypto import decrypt, encrypt, fingerprint
from core.finance.suggestions import identity, merchant_identity, METHOD, MAX_SCAN
from core.finance.account_groups import transfer_scope, internal_transfer_group
from core.finance.local_classification import revision
from core.finance.camt import ImportErrorCode

VERSION = 'recurring-v2'
CADENCES = {'monthly': 1, 'quarterly': 3, 'yearly': 12}


def month_date(index, day):
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day, monthrange(year, month + 1)[1]))


def detect(rows):
    """One stable identity/account/direction/currency series, O(n log n).

    Conservative: no multiple payments per day, at most one missing period,
    and only a long series (>=5) can tolerate one off-schedule observation.
    """
    if len(rows) < 3:
        return None
    rows = sorted(rows, key=lambda r: (r['booking_date'], str(r['id'])))
    dates = [r['booking_date'] for r in rows]
    if len(set(dates)) != len(dates):
        return None
    amounts = [Decimal(str(r['amount'])) for r in rows]
    typical = median(amounts)
    if not typical or any(a * typical <= 0 for a in amounts):
        return None
    variation = median([abs(a - typical) for a in amounts]) / abs(typical)
    intervals = [(b-a).days for a, b in zip(dates, dates[1:])]
    day = int(median([d.day for d in dates]))
    month_end = all(d.day >= monthrange(d.year, d.month)[1] - 2 for d in dates)
    if month_end:
        day = 31
    candidates = []
    for cadence, months in CADENCES.items():
        indices = [d.year*12+d.month-1 for d in dates]
        phase = Counter(i % months for i in indices).most_common(1)[0][0]
        timing = [i % months == phase and abs((d-month_date(i, day)).days) <= 3
                  for d, i in zip(dates, indices)]
        gaps = [(b-a)/months for a, b in zip(indices, indices[1:])]
        # No aggressively selected subsets: every interval must fit the cadence.
        if any(g not in (1, 2) for g in gaps) or gaps.count(2) > 1:
            continue
        if len(timing)-sum(timing) > (1 if len(rows) >= 5 else 0):
            continue
        fit = sum(timing)/len(timing)
        confidence = min(.98, .55+.04*min(len(rows), 8)+.20*fit-.04*gaps.count(2)-.15*min(float(variation), 1))
        if confidence < .7:
            continue
        next_date = month_date(indices[-1]+months, day)
        candidates.append(dict(cadence=cadence, confidence=round(confidence, 3),
            observation_count=len(rows), typical_interval=str(median(intervals)),
            typical_amount=str(typical.quantize(Decimal('.01'))), amount_min=str(min(amounts)),
            amount_max=str(max(amounts)), amount_variation=str(variation.quantize(Decimal('.0001'))),
            typical_transaction_day=day,
            day_basis='day_of_month',
            month_end=month_end, missed_periods=gaps.count(2),
            timing_outliers=len(timing)-sum(timing), last_observed=dates[-1].isoformat(),
            next_expected=next_date.isoformat()))
    if not candidates:
        return None
    result = max(candidates, key=lambda c: c['confidence'])
    result.update(price_change(amounts))
    result['first_observed'] = dates[0].isoformat()
    return result


def price_change(amounts):
    """Latest observed amount step, not a claim that a contract price changed."""
    latest = abs(Decimal(str(amounts[-1])))
    previous = next((abs(Decimal(str(a))) for a in reversed(amounts[:-1]) if abs(Decimal(str(a))) != latest), latest)
    return {'latest_amount': str(latest), 'previous_amount': str(previous),
            'price_change_percent': str(((latest-previous)/previous*100).quantize(Decimal('.01'))) if previous else None}


def current_revision(cur):
    return fingerprint(VERSION, [METHOD, revision(cur)])


def step(conn, job):
    """One account per existing admitted worker step; checkpoints survive retries."""
    with conn.cursor() as cur:
        cur.execute('''SELECT a.id FROM finance.finance_accounts a WHERE NOT EXISTS
            (SELECT 1 FROM finance.finance_recurring_scans s WHERE s.job_id=%s AND s.account_id=a.id)
            ORDER BY a.id LIMIT 1''', (job,))
        account = cur.fetchone()
        if not account:
            return False
        aid = account['id']
        stamp = current_revision(cur)
        cur.execute('SELECT 1 FROM finance.finance_recurring_scans WHERE account_id=%s AND revision_key=%s LIMIT 1', (aid, stamp))
        unchanged = cur.fetchone() is not None
        if not unchanged:
            cur.execute('''SELECT id,account_id,booking_date,amount,currency,private_data FROM finance.v_transactions
                WHERE account_id=%s ORDER BY booking_date,id LIMIT %s''', (aid, MAX_SCAN+1))
            rows = cur.fetchall()
            if len(rows) > MAX_SCAN:
                raise ImportErrorCode('recurring_account_scan_limit')
            scope = transfer_scope(cur)
            grouped = defaultdict(list)
            for row in rows:
                payload = decrypt(row['private_data'])
                match = identity(payload, row['amount'], row['currency'])
                if match is None:
                    continue
                key = fingerprint('recurring-identity-v1', [str(aid), match])
                row['internal_transfer'] = bool(internal_transfer_group(aid, payload, scope))
                merchant = merchant_identity(payload)
                row['merchant'] = merchant[1] if merchant else payload.get('counterparty') or 'Onbekende tegenpartij'
                grouped[key].append(row)
            cur.execute('SELECT * FROM finance.finance_recurring_patterns WHERE account_id=%s', (aid,))
            existing = {r['identity_key']: r for r in cur.fetchall()}
            for key in sorted(set(grouped) | set(existing)):
                members = grouped.get(key, [])
                evidence = detect(members)
                if evidence is None and key not in existing:
                    continue
                active = evidence is not None
                evidence = evidence or {'observation_count': len(members), 'confidence': 0}
                evidence['recurring_type'] = 'periodic_transfer' if members and all(r['internal_transfer'] for r in members) else 'other_recurring'
                evidence['merchant'] = members[0]['merchant'] if members else None
                evidence['detection_version'] = VERSION
                evidence['identity_version'] = METHOD
                evidence['active'] = active
                member_ids = sorted(str(r['id']) for r in members)
                digest = fingerprint(VERSION, [evidence, member_ids])
                if key not in existing:
                    row = members[0]
                    cur.execute('''INSERT INTO finance.finance_recurring_patterns(account_id,identity_key,direction,currency)
                        VALUES (%s,%s,%s,%s) RETURNING *''',
                        (aid, key, 'debit' if row['amount'] < 0 else 'credit', row['currency']))
                    existing[key] = cur.fetchone()
                pattern = existing[key]['id']
                cur.execute('''SELECT evidence_key FROM finance.finance_recurring_detections
                    WHERE pattern_id=%s ORDER BY sequence_no DESC LIMIT 1''', (pattern,))
                last = cur.fetchone()
                if last and last['evidence_key'] == digest:
                    continue
                cur.execute('''INSERT INTO finance.finance_recurring_detections
                    (pattern_id,job_id,evidence_key,active,cadence,confidence,observation_count,private_data,detection_version)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                    (pattern, job, digest, active, evidence.get('cadence'), evidence['confidence'],
                     len(members), encrypt(evidence), VERSION))
                detection = cur.fetchone()['id']
                cur.executemany('''INSERT INTO finance.finance_recurring_members(detection_id,transaction_id)
                    VALUES (%s,%s)''', [(detection, tid) for tid in member_ids])
            if current_revision(cur) != stamp:
                # Caller rolls back the whole account; never publish a mixed snapshot.
                raise ImportErrorCode('recurring_inputs_changed')
        cur.execute('INSERT INTO finance.finance_recurring_scans(job_id,account_id,revision_key) VALUES (%s,%s,%s)',
                    (job, aid, stamp))
        return True


def patterns(cur, account=None, page=0):
    """Persisted evidence only, no detection on page load. Retired sources hidden."""
    cur.execute('''WITH roots AS (
        SELECT p.id FROM finance.finance_recurring_patterns p
        JOIN finance.v_recurring_membership g ON g.pattern_id=p.id AND g.root_id=p.id
        JOIN LATERAL (SELECT id,cadence,active FROM finance.finance_recurring_detections WHERE pattern_id=p.id ORDER BY sequence_no DESC LIMIT 1) d ON true
        WHERE (%s::uuid IS NULL OR p.account_id=%s::uuid) AND d.cadence IS DISTINCT FROM 'weekly'
        AND EXISTS(SELECT 1 FROM finance.finance_recurring_detections old WHERE old.pattern_id=p.id AND old.cadence IN ('monthly','quarterly','yearly'))
        AND (NOT d.active OR NOT EXISTS (SELECT 1 FROM finance.finance_recurring_members m WHERE m.detection_id=d.id AND NOT EXISTS(SELECT 1 FROM finance.v_transactions t WHERE t.id=m.transaction_id)))
        ORDER BY p.account_id,p.id LIMIT 51 OFFSET %s)
        SELECT p.*,g.root_id,g.link_id,d.id AS detection_id,d.active,d.private_data,d.created_at,
        s.revision_key,r.id AS review_id,r.status AS review_status,r.recurring_type AS reviewed_type,
        r.detection_id AS reviewed_detection FROM finance.finance_recurring_patterns p
        JOIN finance.v_recurring_membership g ON g.pattern_id=p.id JOIN roots ON roots.id=g.root_id
        JOIN LATERAL (SELECT * FROM finance.finance_recurring_detections
            WHERE pattern_id=p.id ORDER BY sequence_no DESC LIMIT 1) d ON true
        JOIN LATERAL (SELECT revision_key FROM finance.finance_recurring_scans
            WHERE account_id=p.account_id ORDER BY created_at DESC,job_id DESC LIMIT 1) s ON true
        LEFT JOIN LATERAL (SELECT * FROM finance.finance_recurring_reviews
            WHERE pattern_id=p.id ORDER BY sequence_no DESC LIMIT 1) r ON true
        WHERE d.cadence IS DISTINCT FROM 'weekly'
        AND (NOT d.active OR NOT EXISTS (SELECT 1 FROM finance.finance_recurring_members m
            WHERE m.detection_id=d.id AND NOT EXISTS(SELECT 1 FROM finance.v_transactions t WHERE t.id=m.transaction_id)))
        ORDER BY p.account_id,g.root_id,p.id''', (account, account, page*50))
    rows = cur.fetchall()
    # Current effective classifications, not copied into detection evidence.
    summaries = defaultdict(list)
    if rows:
        cur.execute("""SELECT m.detection_id,t.category_code,t.subcategory_code,t.transaction_type,
            count(*) AS count,count(*) FILTER(WHERE t.confirmed) AS confirmed_count
            FROM finance.finance_recurring_members m JOIN finance.v_transactions t ON t.id=m.transaction_id
            WHERE m.detection_id=ANY(%s::uuid[])
            GROUP BY m.detection_id,t.category_code,t.subcategory_code,t.transaction_type""",
            ([str(r['detection_id']) for r in rows],))
        for summary in cur.fetchall():
            did = summary.pop('detection_id')
            summaries[did].append(dict(summary))
    stamp = current_revision(cur)
    items = []
    for row in rows:
        items.append({**decrypt(row['private_data']), 'id': str(row['id']),
            'root_id': str(row['root_id']), 'link_id': str(row['link_id']) if row['link_id'] else None,
            'account_id': str(row['account_id']), 'direction': row['direction'], 'currency': row['currency'],
            'detection_id': str(row['detection_id']), 'detected_at': row['created_at'].isoformat(),
            'status': (row['review_status'] or 'proposed') if row['active'] else 'inactive',
            'classifications': summaries[row['detection_id']],
            'review_status': row['review_status'], 'review_id': str(row['review_id']) if row['review_id'] else None,
            'reviewed_type': row['reviewed_type'],
            'new_evidence': bool(row['reviewed_detection'] and row['reviewed_detection'] != row['detection_id']),
            'stale': row['revision_key'] != stamp})
    groups = defaultdict(list)
    for item in items:
        groups[item['root_id']].append(item)
    merged = []
    for root, parts in groups.items():
        parent = next((p for p in parts if p['id'] == root), None)
        if parent is None:
            continue  # Root evidence retired: never publish an incomplete group.
        item = dict(parent)
        item['components'] = parts
        item['observation_count'] = sum(p['observation_count'] for p in parts)
        item['classifications'] = [c for p in parts for c in p['classifications']]
        item['stale'] = any(p['stale'] for p in parts)
        item['new_evidence'] = any(p['new_evidence'] for p in parts)
        if len(parts) > 1:
            ordered = sorted(parts, key=lambda p: (p.get('last_observed') or '', p['id']))
            item['last_observed'] = ordered[-1].get('last_observed')
            item['next_expected'] = None  # A manual link is not evidence for continuous forecasting.
            item['cadence'] = parent.get('cadence') if len({p.get('cadence') for p in parts}) == 1 else None
            amounts = [p['typical_amount'] for p in ordered if p.get('typical_amount') is not None]
            if amounts:
                item.update(price_change(amounts))
            item['typical_amount'] = ordered[-1].get('typical_amount')
            item['amount_min'] = str(min(Decimal(p['amount_min']) for p in parts if p.get('amount_min') is not None)) if amounts else None
            item['amount_max'] = str(max(Decimal(p['amount_max']) for p in parts if p.get('amount_max') is not None)) if amounts else None
        merged.append(item)
    return {'patterns': merged[:50], 'page': page, 'has_more': len(merged) > 50, 'detection_version': VERSION}


def member_ids_sql():
    return """SELECT DISTINCT m.transaction_id FROM finance.v_recurring_membership g
        JOIN LATERAL (SELECT id,cadence FROM finance.finance_recurring_detections WHERE pattern_id=g.pattern_id ORDER BY sequence_no DESC LIMIT 1) d ON true
        JOIN finance.finance_recurring_members m ON m.detection_id=d.id
        WHERE g.root_id=%s AND d.cadence IS DISTINCT FROM 'weekly'"""
