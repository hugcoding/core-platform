"""Bounded background discovery; no work is triggered by a dashboard request."""
from uuid import NAMESPACE_URL, uuid5

from core.organization.target_path import propose_target
from core.organization.review_taxonomy import taxonomy_fallback_proposal

REQUESTED_BY = "core-auto-inactive-general-v1"

# Limit the workset before joining review evidence. Keyset paging avoids OFFSET.
PAGE_SQL = """WITH page AS MATERIALIZED (
    SELECT * FROM public.v_effective_document_workset
    WHERE file_id > %s
      AND effective_workset_status='inactive'
      AND review_state='pending'
      AND review_family='general'
    ORDER BY file_id LIMIT %s
)
SELECT w.*, c.category, c.document_family,
       EXISTS (SELECT 1 FROM public.v_latest_pdf_content_similarity_review s
               WHERE s.action='selected_leader' AND w.file_id=ANY(s.redundant_file_ids)) AS redundant_file_id
FROM page w
LEFT JOIN public.v_current_file_classification c ON c.file_id=w.file_id
ORDER BY w.file_id
"""


def eligible(row, now=None):
    from core.finance.privacy import protected_path
    if protected_path(row.get('path')):
        return False
    del now  # Kept for call compatibility; effective status is database-projected.
    status = row.get("effective_workset_status") or row.get("workset_status")
    if status != "inactive" or row.get("redundant_file_id"):
        return False
    if row.get("review_state") != "pending" or row.get("review_family") != "general":
        return False
    proposal = propose_target(row)
    return (proposal["category_code"] == "needs_review"
            and proposal["zone_code"] != "quarantine"
            and not taxonomy_fallback_proposal(row, proposal))


def enqueue_page(cur, after_id, model, prompt, page_size=25, pending_limit=5, hourly_limit=10):
    cur.execute("SELECT count(*) AS count FROM public.workset_ai_jobs WHERE status IN ('pending','running')")
    room = max(0, pending_limit - cur.fetchone()["count"])
    if not room:
        return after_id, 0
    cur.execute("""SELECT count(*) AS count FROM public.workset_ai_jobs
                   WHERE requested_by=%s AND requested_at >= now() - interval '1 hour'""",
                (REQUESTED_BY,))
    room = min(room, max(0, hourly_limit - cur.fetchone()["count"]))
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
            SELECT %s,%s,%s,'inactive',100,%s,%s,%s
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
