"""Container integration for bounded inactive/general AI fallback."""
import os
import uuid

import psycopg2
import psycopg2.extras
import redis

import workset_ai_worker as worker
from core.semantic.automatic_workset_ai import REQUESTED_BY, enqueue_page


def connect():
    return psycopg2.connect(
        host=os.environ["DB_HOST"], user=os.environ["DB_USER"], password=os.environ["DB_PASS"],
        dbname=os.environ["DB_NAME"], cursor_factory=psycopg2.extras.RealDictCursor,
    )


SCHEMA = """
CREATE TABLE files(id bigint PRIMARY KEY, filename text, path text, extension text,
 content_sha256 text, deleted_at timestamptz);
CREATE TABLE effective_items(file_id bigint PRIMARY KEY, filename text, path text, extension text,
 content_sha256 text, workset_status text, effective_workset_status text, review_state text,
 review_family text, category text, document_family text);
CREATE VIEW v_effective_document_workset AS SELECT * FROM effective_items;
CREATE VIEW v_active_document_workset AS SELECT file_id,filename,path,extension,content_sha256,workset_status FROM effective_items;
CREATE VIEW v_workset_current_physical_location AS
 SELECT NULL::bigint AS file_id,NULL::text AS current_path WHERE false;
CREATE VIEW v_current_file_classification AS SELECT file_id,category,document_family FROM effective_items WHERE false;
CREATE TABLE similarity_reviews(action text, redundant_file_ids bigint[]);
CREATE VIEW v_latest_pdf_content_similarity_review AS SELECT * FROM similarity_reviews;
CREATE TABLE workset_ai_jobs(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), idempotency_key uuid UNIQUE NOT NULL,
 file_id bigint NOT NULL, content_sha256 text NOT NULL, workset_status_snapshot text NOT NULL,
 priority int NOT NULL, status text NOT NULL DEFAULT 'pending', waiting_reason text,
 model_id text NOT NULL, prompt_version text NOT NULL, requested_by text NOT NULL,
 requested_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz, finished_at timestamptz,
 updated_at timestamptz NOT NULL DEFAULT now(), attempt_count int NOT NULL DEFAULT 0,
 error_code text, run_id uuid, proposal_id uuid);
CREATE TABLE workset_ocr_jobs(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), idempotency_key uuid UNIQUE NOT NULL,
 file_id bigint NOT NULL, content_sha256 text NOT NULL, priority int NOT NULL,
 status text NOT NULL DEFAULT 'pending', requested_by text NOT NULL,
 requested_at timestamptz NOT NULL DEFAULT now(), error_code text, artifact_path text,
 pages int, characters int, text_sha256 text, finished_at timestamptz);
CREATE TABLE controlled_state(batch_status text);
CREATE VIEW v_controlled_execution_batch_progress AS SELECT batch_status FROM controlled_state;
"""

with connect() as conn, conn.cursor() as cur:
    cur.execute(SCHEMA)
    cur.execute("""INSERT INTO files VALUES
        (42,'onbekend.pdf','/volume1/data/Persoonlijk/Inactief/Te beoordelen/onbekend.pdf','pdf',%s,NULL)""", ("a" * 64,))
    cur.execute("""INSERT INTO effective_items VALUES
        (42,'onbekend.pdf','/volume1/data/Persoonlijk/Inactief/Te beoordelen/onbekend.pdf','pdf',%s,
         'inactive','inactive','pending','general',NULL,NULL)""", ("a" * 64,))

with connect() as conn, conn.cursor() as cur:
    after, added = enqueue_page(cur, 0, "test-model", "test-prompt", page_size=5, pending_limit=5, hourly_limit=10)
    assert (after, added) == (0, 1), (after, added)
with connect() as conn, conn.cursor() as cur:
    assert enqueue_page(cur, 0, "test-model", "test-prompt", 5, 5, 10)[1] == 0
    cur.execute("SELECT * FROM workset_ai_jobs WHERE file_id=42")
    stale_job = dict(cur.fetchone())
    cur.execute("UPDATE effective_items SET content_sha256=%s WHERE file_id=42", ("b" * 64,))
    cur.execute("UPDATE files SET content_sha256=%s WHERE id=42", ("b" * 64,))

worker.process_job(stale_job)
with connect() as conn, conn.cursor() as cur:
    cur.execute("SELECT status,error_code FROM workset_ai_jobs WHERE id=%s", (stale_job["id"],))
    assert dict(cur.fetchone()) == {"status": "cancelled", "error_code": "stale_file"}

client = redis.Redis(host=os.environ["REDIS_HOST"], decode_responses=True)
assert worker.service_gate(client) is None
with connect() as conn, conn.cursor() as cur:
    cur.execute("INSERT INTO controlled_state VALUES ('started')")
assert worker.service_gate(client) == "controlled_execution_priority"
with connect() as conn, conn.cursor() as cur:
    cur.execute("DELETE FROM controlled_state")
    retry_id = uuid.uuid4()
    cur.execute("""INSERT INTO workset_ai_jobs
      (id,idempotency_key,file_id,content_sha256,workset_status_snapshot,priority,model_id,prompt_version,requested_by)
      VALUES (%s,%s,42,%s,'inactive',100,'test-model','test-prompt','integration')""",
      (str(retry_id), str(uuid.uuid4()), "b" * 64))
worker.fail_or_retry({"id": str(retry_id), "attempt_count": 0}, TimeoutError())
with connect() as conn, conn.cursor() as cur:
    cur.execute("SELECT status,waiting_reason FROM workset_ai_jobs WHERE id=%s", (str(retry_id),))
    assert dict(cur.fetchone()) == {"status": "pending", "waiting_reason": "provider_unavailable"}
worker.fail_or_retry({"id": str(retry_id), "attempt_count": 3}, TimeoutError())
with connect() as conn, conn.cursor() as cur:
    cur.execute("SELECT status FROM workset_ai_jobs WHERE id=%s", (str(retry_id),))
    assert cur.fetchone()["status"] == "failed"

print("workset AI fallback integration: PASS")
