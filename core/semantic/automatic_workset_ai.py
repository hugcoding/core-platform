"""Bounded background discovery; no work is triggered by a dashboard request."""
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from core.organization.target_path import propose_target
from core.organization.review_taxonomy import taxonomy_fallback_proposal

REQUESTED_BY = "core-auto-active-v1"

# Limit the workset before joining review evidence. Keyset paging avoids OFFSET.
PAGE_SQL = """WITH page AS MATERIALIZED (
    SELECT * FROM public.v_active_document_workset
    WHERE file_id > %s ORDER BY file_id LIMIT %s
)
SELECT w.*, c.category, c.document_family,
       r.decision AS review_decision, r.corrected_category_code AS reviewed_category,
       l.corrected_lifecycle, l.lifecycle_active_until,
       EXISTS (SELECT 1 FROM public.v_latest_pdf_content_similarity_review s
               WHERE s.action='selected_leader' AND w.file_id=ANY(s.redundant_file_ids)) AS redundant_file_id
FROM page w
LEFT JOIN public.v_current_file_classification c ON c.file_id=w.file_id
LEFT JOIN public.v_latest_document_review r ON r.file_id=w.file_id AND r.review_type='target_path'
LEFT JOIN public.v_latest_document_review l ON l.file_id=w.file_id AND l.review_type='lifecycle'
ORDER BY w.file_id
"""


def eligible(row, now=None):
    now = now or datetime.now(timezone.utc)
    lifecycle = row.get("corrected_lifecycle")
    until = row.get("lifecycle_active_until")
    if lifecycle == "active" and until and until <= now:
        lifecycle = None
    status = lifecycle or {"inactive": "archive"}.get(row.get("workset_status"), row.get("workset_status"))
    if status != "active" or row.get("redundant_file_id"):
        return False
    if row.get("review_decision") or row.get("category") or row.get("reviewed_category"):
        return False
    proposal = propose_target(row)
    return (proposal["category_code"] == "needs_review"
            and proposal["zone_code"] != "quarantine"
            and not taxonomy_fallback_proposal(row, proposal))


def enqueue_page(cur, after_id, model, prompt, page_size=25, pending_limit=20):
    cur.execute("SELECT count(*) AS count FROM public.workset_ai_jobs WHERE status IN ('pending','running')")
    room = max(0, pending_limit - cur.fetchone()["count"])
    if not room:
        return after_id, 0
    cur.execute(PAGE_SQL, (after_id, page_size))
    rows = cur.fetchall()
    last, added = after_id, 0
    for row in rows:
        last = int(row["file_id"])
        if not eligible(row):
            continue
        identity = str(uuid5(NAMESPACE_URL, f"{REQUESTED_BY}:{row['file_id']}:{row['content_sha256']}:{model}:{prompt}"))
        cur.execute("""
            INSERT INTO public.workset_ai_jobs
              (idempotency_key,file_id,content_sha256,workset_status_snapshot,priority,
               model_id,prompt_version,requested_by)
            SELECT %s,%s,%s,'active',100,%s,%s,%s
            WHERE NOT EXISTS (
                SELECT 1 FROM public.workset_ai_jobs
                WHERE file_id=%s AND content_sha256=%s AND model_id=%s AND prompt_version=%s
            )
            ON CONFLICT DO NOTHING RETURNING id
        """, (identity, row["file_id"], row["content_sha256"], model, prompt, REQUESTED_BY,
              row["file_id"], row["content_sha256"], model, prompt))
        added += int(cur.fetchone() is not None)
        if added >= room:
            return last, added
    return (last if len(rows) == page_size else 0), added
