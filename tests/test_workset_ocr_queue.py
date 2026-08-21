import gzip
import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[1]


class WorksetOcrQueueTests(unittest.TestCase):
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
            cls.worker = importlib.import_module("workset_ocr_worker")

    def test_migration_is_persistent_content_bound_and_reversible(self):
        migration = (ROOT / "database/migrations/20260821_add_workset_ocr_jobs.sql").read_text()
        rollback = (ROOT / "database/migrations/rollback/20260821_add_workset_ocr_jobs.sql").read_text()
        self.assertIn("CREATE TABLE IF NOT EXISTS public.workset_ocr_jobs", migration)
        self.assertIn("content_sha256 text NOT NULL", migration)
        self.assertIn("WHERE status IN ('pending', 'running')", migration)
        self.assertIn("DROP TABLE IF EXISTS public.workset_ocr_jobs", rollback)

    def test_artifact_is_compressed_and_named_by_valid_content_hash(self):
        digest = "a" * 64
        with self.subTest("valid"):
            with mock.patch.object(self.worker, "OUTPUT_ROOT", Path(self._testMethodName)):
                try:
                    path, text_hash = self.worker.persist_artifact(digest, "herkende tekst")
                    with gzip.open(path, "rt", encoding="utf-8") as handle:
                        self.assertEqual("herkende tekst", handle.read())
                    self.assertEqual(64, len(text_hash))
                finally:
                    import shutil
                    shutil.rmtree(self._testMethodName, ignore_errors=True)
        with self.assertRaisesRegex(ValueError, "invalid_content_sha256"):
            self.worker.persist_artifact("../onveilig", "tekst")

    def test_worker_uses_local_tesseract_and_never_rewrites_source(self):
        source = (ROOT / "workset_ocr_worker.py").read_text(encoding="utf-8")
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        dockerfile = (ROOT / "Dockerfile.workset-ocr-worker").read_text(encoding="utf-8")
        self.assertIn('["tesseract", str(image), "stdout"', source)
        self.assertIn("workset_ocr_worker:", compose)
        self.assertIn('"/volume1:/volume1:ro"', compose)
        self.assertIn("tesseract-ocr-data-nld", dockerfile)
        self.assertIn("CORE_OCR_MAX_CPU_PERCENT", compose)

    def test_portal_has_individual_ocr_endpoint_and_button(self):
        app = (ROOT / "dashboard/app.py").read_text(encoding="utf-8")
        script = (ROOT / "dashboard/static/workset-ai.js").read_text(encoding="utf-8")
        self.assertIn('@app.post("/api/v1/workset/ocr-jobs")', app)
        self.assertIn("OCR starten", script)
        self.assertIn("requestOcr", script)
        self.assertIn('"file_mutations": False', app)

    def test_ai_worker_reuses_ready_ocr_artifact(self):
        source = (ROOT / "workset_ai_worker.py").read_text(encoding="utf-8")
        self.assertIn("existing_ocr_artifact", source)
        self.assertIn('"reason": "local_ocr_artifact"', source)


if __name__ == "__main__":
    unittest.main()
