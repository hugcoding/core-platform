"""Real PostgreSQL + filesystem move/resume/rollback integration proof."""
import hashlib
import os
import uuid
from pathlib import Path

import psycopg2
import psycopg2.extras

import controlled_execution_worker as worker


def connect():
    return psycopg2.connect(host=os.environ["DB_HOST"], user=os.environ["DB_USER"],
                            password=os.environ["DB_PASS"], dbname=os.environ["DB_NAME"],
                            cursor_factory=psycopg2.extras.RealDictCursor)


conn = connect()
with conn, conn.cursor() as cur:
    cur.execute("CREATE TABLE public.files (id bigint PRIMARY KEY)")
    for migration in ("20260829_add_controlled_execution_queue.sql", "20260830_enhance_controlled_execution_progress.sql"):
        cur.execute(Path("database/migrations", migration).read_text("utf-8"))

source = Path("/volume1/data/import/integration.txt")
target = Path("/volume1/data/Persoonlijk/Actief/integration.txt")
source.parent.mkdir(parents=True, exist_ok=True)
source.write_bytes(b"controlled execution integration\n")
digest = hashlib.sha256(source.read_bytes()).hexdigest()
batch_id, item_id = str(uuid.uuid4()), str(uuid.uuid4())
with conn, conn.cursor() as cur:
    cur.execute("INSERT INTO public.files(id) VALUES (1)")
    cur.execute("""INSERT INTO public.controlled_execution_batches
      (id,contract_version,batch_key,item_count,created_by) VALUES (%s,'controlled-execution-queue-v1',%s,1,'integration')""",
      (batch_id, "a" * 64))
    cur.execute("""INSERT INTO public.controlled_execution_batch_items
      (id,batch_id,sequence_no,action_type,priority,file_id,source_path,target_path,content_sha256,size_bytes,evidence_snapshot)
      VALUES (%s,%s,1,'migrate_active',40,1,%s,%s,%s,%s,'{}')""",
      (item_id, batch_id, str(source), str(target), digest, source.stat().st_size))
    cur.execute("""INSERT INTO public.controlled_execution_events(batch_id,item_id,event_type,idempotency_key,actor)
      VALUES (%s,%s,'queued',%s,'integration'),(%s,NULL,'approved',%s,'integration')""",
      (batch_id, item_id, item_id + ":queued", batch_id, batch_id + ":approved"))

assert worker.run_once() is True
assert target.is_file() and not source.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == digest
with conn, conn.cursor() as cur:
    cur.execute("SELECT current_status FROM public.v_controlled_execution_item_status WHERE id=%s", (item_id,))
    assert cur.fetchone()["current_status"] == "verified"
    cur.execute("""INSERT INTO public.controlled_execution_events(batch_id,item_id,event_type,idempotency_key,actor)
      VALUES (%s,NULL,'rollback_pending',%s,'integration')""", (batch_id, batch_id + ":rollback"))

assert worker.run_once() is True
assert source.is_file() and not target.exists() and hashlib.sha256(source.read_bytes()).hexdigest() == digest
with conn, conn.cursor() as cur:
    cur.execute("SELECT current_status FROM public.v_controlled_execution_item_status WHERE id=%s", (item_id,))
    assert cur.fetchone()["current_status"] == "rolled_back"
print("controlled execution integration: PASS")
