import importlib
import sys
import types
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "database/migrations/20260821_add_exact_duplicate_review.sql"
ROLLBACK = ROOT / "database/migrations/rollback/20260821_add_exact_duplicate_review.sql"


class ExactDuplicateReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class FakeFastAPI:
            def __init__(self, *args, **kwargs): pass
            def mount(self, *args, **kwargs): pass
            def get(self, *args, **kwargs): return lambda function: function
            def post(self, *args, **kwargs): return lambda function: function

        class FakeHTTPException(RuntimeError):
            def __init__(self, status_code, detail):
                super().__init__(detail); self.status_code = status_code; self.detail = detail

        fastapi = types.ModuleType("fastapi")
        fastapi.FastAPI = FakeFastAPI; fastapi.HTTPException = FakeHTTPException
        fastapi.Query = lambda default, **kwargs: default; fastapi.Body = lambda default, **kwargs: default
        responses = types.ModuleType("fastapi.responses")
        responses.FileResponse = lambda path, **kwargs: path
        responses.RedirectResponse = lambda path, status_code=307: (path, status_code)
        responses.Response = lambda **kwargs: kwargs
        staticfiles = types.ModuleType("fastapi.staticfiles"); staticfiles.StaticFiles = lambda **kwargs: kwargs
        modules = {"psycopg2": mock.MagicMock(), "redis": mock.MagicMock(), "fastapi": fastapi,
                   "fastapi.responses": responses, "fastapi.staticfiles": staticfiles}
        with mock.patch.dict(sys.modules, modules):
            cls.dashboard = importlib.import_module("dashboard.app")

    def test_migration_is_append_only_and_handoff_only(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        rollback = ROLLBACK.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS public.exact_duplicate_review_events", sql)
        self.assertIn("reject_exact_duplicate_review_mutation", sql)
        self.assertIn("v_exact_duplicate_review_groups", sql)
        self.assertIn("v_exact_duplicate_review_handoff", sql)
        self.assertIn("/volume1/data/.core/quarantaine/duplicaten", sql)
        self.assertIn("golden_switch_required", sql)
        self.assertIn("duplicate_changed_after_nomination", sql)
        self.assertNotIn("UPDATE public.files", sql)
        self.assertNotIn("DELETE FROM public.files", sql)
        self.assertIn("DROP TABLE IF EXISTS public.exact_duplicate_review_events", rollback)

    def test_portal_exposes_integrated_group_review(self):
        html = (ROOT / "dashboard/static/workset.html").read_text(encoding="utf-8")
        script = (ROOT / "dashboard/static/duplicate-review.js").read_text(encoding="utf-8")
        source = (ROOT / "dashboard/app.py").read_text(encoding="utf-8")
        self.assertIn('id="duplicateReviewSection"', html)
        self.assertIn("duplicate-review.js", html)
        self.assertIn("Leidende kopie bevestigen", script)
        self.assertIn('id="duplicateBulkSelectAll"', html)
        self.assertIn('id="duplicateBulkDialog"', html)
        self.assertIn("confirmBulkReview", script)
        self.assertIn("submit(card, 'selected_leader', {reload:false})", script)
        self.assertIn("globalThis.crypto?.randomUUID", script)
        self.assertIn("globalThis.crypto?.getRandomValues", script)
        self.assertIn('@app.get("/api/v1/workset/duplicates")', source)
        self.assertIn('@app.post("/api/v1/workset/duplicate-reviews")', source)

    def test_review_requires_current_exact_hash_and_writes_one_event(self):
        connection = mock.MagicMock(); connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        event_id = uuid.uuid4(); group_id = uuid.uuid4(); policy_id = uuid.uuid4()
        cursor.fetchone.return_value = (event_id, None, group_id, 11, "selected_leader")
        group = {"id": group_id, "content_sha256": "a" * 64, "size_bytes": 42, "golden_file_id": 11}
        members = [
            {"id": 11, "path": "/volume1/data/a.pdf", "filename": "a.pdf", "content_sha256": "a" * 64, "size_bytes": 42, "deleted_at": None},
            {"id": 12, "path": "/volume1/data/b.pdf", "filename": "b.pdf", "content_sha256": "a" * 64, "size_bytes": 42, "deleted_at": None},
        ]
        policy = {"id": policy_id, "policy_code": "document_retention", "policy_version": "v1", "configuration": {"deletion_review_days": 30}}
        with mock.patch.dict("os.environ", {"CORE_REVIEW_WRITES_ENABLED": "true"}), mock.patch.object(
            self.dashboard, "db_connect", return_value=connection,
        ), mock.patch.object(
            self.dashboard, "query_all", side_effect=[[group], members, [], [policy], []],
        ):
            result = self.dashboard.create_exact_duplicate_review({
                "content_group_id": str(group_id), "selected_file_id": 11,
                "idempotency_key": str(uuid.uuid4()), "action": "selected_leader",
            })
        self.assertEqual("stored", result["status"])
        self.assertTrue(result["selected_is_current_golden"])
        self.assertFalse(result["file_mutations"])
        self.assertFalse(result["golden_record_updated"])
        self.assertFalse(result["retention_events_created"])
        sql = cursor.execute.call_args_list[0].args[0]
        self.assertIn("INSERT INTO public.exact_duplicate_review_events", sql)

    def test_changed_member_hash_blocks_review(self):
        connection = mock.MagicMock(); connection.__enter__.return_value = connection
        group_id = uuid.uuid4()
        group = {"id": group_id, "content_sha256": "a" * 64, "size_bytes": 42, "golden_file_id": 11}
        members = [
            {"id": 11, "content_sha256": "a" * 64, "size_bytes": 42, "deleted_at": None},
            {"id": 12, "content_sha256": "b" * 64, "size_bytes": 42, "deleted_at": None},
        ]
        with mock.patch.dict("os.environ", {"CORE_REVIEW_WRITES_ENABLED": "true"}), mock.patch.object(
            self.dashboard, "db_connect", return_value=connection,
        ), mock.patch.object(self.dashboard, "query_all", side_effect=[[group], members]):
            with self.assertRaisesRegex(RuntimeError, "duplicate evidence changed"):
                self.dashboard.create_exact_duplicate_review({
                    "content_group_id": str(group_id), "selected_file_id": 11,
                    "idempotency_key": str(uuid.uuid4()), "action": "selected_leader",
                })


if __name__ == "__main__":
    unittest.main()
