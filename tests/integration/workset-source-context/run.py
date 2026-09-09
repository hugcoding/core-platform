"""Real PostgreSQL proof for deterministic, evidence-only source context."""
import os
import uuid
from pathlib import Path

import psycopg2
import psycopg2.extras


conn = psycopg2.connect(
    host=os.environ["DB_HOST"], port=os.environ["DB_PORT"],
    user=os.environ["DB_USER"], password=os.environ["DB_PASS"],
    dbname=os.environ["DB_NAME"], cursor_factory=psycopg2.extras.RealDictCursor,
)
file_id = 42
created_id, documents_id, moved_id = (str(uuid.uuid4()) for _ in range(3))
with conn, conn.cursor() as cur:
    cur.execute("""
        CREATE TABLE public.file_events (
            id uuid PRIMARY KEY, file_id bigint, old_path text, new_path text,
            event_status text NOT NULL DEFAULT 'active', created_at timestamptz NOT NULL
        );
        CREATE VIEW public.v_file_events_effective AS
        SELECT * FROM public.file_events WHERE event_status <> 'invalidated';
    """)
    cur.execute("""
        INSERT INTO public.file_events(id,file_id,old_path,new_path,created_at) VALUES
        (%s,%s,NULL,'/volume1/data/import/cloud/onedrive/current/Payroll/pension.pdf','2026-07-01T00:00:00Z'),
        (%s,%s,'/volume1/data/import/cloud/onedrive/current/Payroll/pension.pdf',
          '/volume1/data/import/cloud/onedrive/current/Documenten/Uitzoeken/Payroll/pension.pdf','2026-07-02T00:00:00Z'),
        (%s,%s,'/volume1/data/import/cloud/onedrive/current/Documenten/Uitzoeken/Payroll/pension.pdf',
          '/volume1/data/Persoonlijk/Inactief/Te beoordelen/pension.pdf','2026-07-03T00:00:00Z')
    """, (created_id, file_id, documents_id, file_id, moved_id, file_id))
    cur.execute(Path("database/migrations/20260908_add_workset_source_context.sql").read_text("utf-8"))
    cur.execute("SELECT * FROM public.v_workset_source_context WHERE file_id=%s", (file_id,))
    row = cur.fetchone()

assert row["source_context_path"] == "/volume1/data/import/cloud/onedrive/current/Documenten/Uitzoeken/Payroll/pension.pdf"
assert row["source_context_relative_path"] == "Uitzoeken/Payroll/pension.pdf"
assert str(row["source_event_id"]) == documents_id
assert row["source_event_path_kind"] == "new_path"
assert row["selection_reason"] == "earliest_onedrive_documents_path"

with conn, conn.cursor() as cur:
    cur.execute("SELECT count(*) AS count FROM public.file_events")
    assert cur.fetchone()["count"] == 3, "projection must not mutate event history"

print("workset source context integration passed")
