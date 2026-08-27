import importlib
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[1]


class WorksetAiQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        redis_module = types.ModuleType("redis")
        redis_module.Redis = mock.MagicMock
        redis_module.ResponseError = RuntimeError
        psycopg2_module = types.ModuleType("psycopg2")
        psycopg2_module.connect = mock.MagicMock
        extras_module = types.ModuleType("psycopg2.extras")
        extras_module.RealDictCursor = object
        psycopg2_module.extras = extras_module
        with mock.patch.dict(sys.modules, {
            "redis": redis_module, "psycopg2": psycopg2_module,
            "psycopg2.extras": extras_module,
        }):
            cls.worker = importlib.import_module("workset_ai_worker")

    def test_resource_gate_protects_cpu_memory_and_core_pipeline(self):
        self.assertEqual("waiting_for_cpu", self.worker.resource_gate(
            {"cpu_load_percent": 71, "available_memory_mib": 8000}, 0,
        ))
        self.assertEqual("waiting_for_memory", self.worker.resource_gate(
            {"cpu_load_percent": 20, "available_memory_mib": 2000}, 0,
        ))
        self.assertEqual("core_pipeline_priority", self.worker.resource_gate(
            {"cpu_load_percent": 20, "available_memory_mib": 8000}, 1001,
        ))
        self.assertIsNone(self.worker.resource_gate(
            {"cpu_load_percent": 20, "available_memory_mib": 8000}, 0,
        ))

    def test_claim_query_prioritizes_active_before_review_and_inactive(self):
        source = (ROOT / "workset_ai_worker.py").read_text(encoding="utf-8")
        self.assertIn("ORDER BY priority DESC, requested_at, id", source)
        self.assertIn("FOR UPDATE SKIP LOCKED", source)
        self.assertIn("MAX_STREAM_LAG", source)
        self.assertIn("workset_ai_worker:heartbeat", source)
        self.assertIn('row["workset_status"] = job["workset_status_snapshot"]', source)

    def test_enqueue_uses_effective_human_lifecycle_status(self):
        source = (ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
        enqueue = source[source.index("def create_workset_ai_job"):source.index(
            '@app.post("/api/v1/workset/ai-jobs/{job_id}/accept")'
        )]
        self.assertIn('effective_lifecycle_for_file(conn, row)["workset_status"]', enqueue)

    def test_migration_has_persistent_queue_and_rollback(self):
        migration = (ROOT / "database" / "migrations" / "20260816_add_async_workset_ai_jobs.sql").read_text()
        rollback = (ROOT / "database" / "migrations" / "rollback" / "20260816_add_async_workset_ai_jobs.sql").read_text()
        self.assertIn("CREATE TABLE IF NOT EXISTS public.workset_ai_jobs", migration)
        self.assertIn("WHERE status IN ('pending', 'running')", migration)
        self.assertIn("DROP TABLE IF EXISTS public.workset_ai_jobs", rollback)

    def test_portal_uses_individual_jobs_bell_and_explicit_complete_acceptance(self):
        script = (ROOT / "dashboard" / "static" / "workset-ai.js").read_text(encoding="utf-8")
        app = (ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
        self.assertIn("Vraag AI-voorstel aan", script)
        self.assertIn("ai-bell", script)
        self.assertIn("Gebruik als beoordeling", script)
        self.assertNotIn("file_ids:ids", script)
        self.assertIn('@app.post("/api/v1/workset/ai-jobs")', app)
        self.assertIn('@app.post("/api/v1/workset/ai-jobs/{job_id}/accept")', app)
        self.assertIn("for review_type in (\"target_path\", \"privacy_classification\", \"lifecycle\")", app)
        self.assertIn('"file_mutations": False', app)
        self.assertIn("latestAiJobsByFile", script)
        self.assertIn("job.awaiting_human_review", script)
        self.assertIn("notification_label:'OCR gereed'", script)
        self.assertIn("job.workset_available===false", script)
        self.assertIn("w.content_sha256=ANY(%s)", app)
        self.assertIn('item["requested_file_id"]', app)
        self.assertIn('item["workset_available"]', app)
        self.assertIn("WHERE w.content_sha256=%s", app)

    def test_portal_explains_ocr_recommendation_without_automatic_ocr(self):
        worker = (ROOT / "workset_ai_worker.py").read_text(encoding="utf-8")
        script = (ROOT / "dashboard" / "static" / "workset-ai.js").read_text(encoding="utf-8")
        self.assertIn('context["status"] != "ready"', worker)
        self.assertIn("ocr_recommended_no_extractable_text", script)
        self.assertIn("OCR aanbevolen", script)
        self.assertNotIn("startOcr", script)

    def test_existing_needs_ocr_is_looked_up_by_content_hash(self):
        cursor = mock.MagicMock()
        cursor.fetchone.return_value = {
            "run_id": "00000000-0000-0000-0000-000000000001",
            "evidence_file_id": 42,
            "status": "needs_ocr",
            "pages": 3,
            "updated_at": datetime(2026, 8, 21, tzinfo=timezone.utc),
        }
        evidence = self.worker.existing_ocr_evidence(cursor, 42, "abc")
        query = cursor.execute.call_args.args[0]
        self.assertIn("sd.content_sha256=%s", query)
        self.assertIn("sd.status='needs_ocr'", query)
        self.assertEqual(("abc", 42), cursor.execute.call_args.args[1])
        self.assertEqual(3, evidence["pages"])

    def test_api_exposes_extraction_lineage_for_ocr_advice(self):
        app = (ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
        script = (ROOT / "dashboard" / "static" / "workset-ai.js").read_text(encoding="utf-8")
        self.assertIn("p.related_file_ids, p.extraction_metadata", app)
        self.assertIn("ocr_required_from_existing_evidence", script)
        self.assertIn("OCR vereist — reeds vastgesteld", script)

    def test_document_selection_remains_available_for_every_workset_status(self):
        workset = (ROOT / "dashboard" / "static" / "workset.js").read_text(encoding="utf-8")
        ai = (ROOT / "dashboard" / "static" / "workset-ai.js").read_text(encoding="utf-8")
        self.assertIn('aria-label="Document selecteren"', workset)
        self.assertNotIn("card.querySelector('.bulk-select')?.remove()", ai)
        self.assertNotIn("file_ids:ids", ai)

    def test_compose_worker_is_read_only_and_single_process(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("workset_ai_worker:", compose)
        self.assertIn("CORE_AI_MAX_CPU_PERCENT", compose)
        self.assertIn('"/volume1:/volume1:ro"', compose)
        self.assertIn("read_only: true", compose)


if __name__ == "__main__":
    unittest.main()
