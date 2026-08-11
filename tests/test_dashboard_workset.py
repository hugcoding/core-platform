import importlib
import sys
import types
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[1]


class DashboardWorksetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class FakeFastAPI:
            def __init__(self, *args, **kwargs):
                pass

            def mount(self, *args, **kwargs):
                pass

            def get(self, *args, **kwargs):
                return lambda function: function

            def post(self, *args, **kwargs):
                return lambda function: function

        fastapi = types.ModuleType("fastapi")
        fastapi.FastAPI = FakeFastAPI
        fastapi.HTTPException = RuntimeError
        fastapi.Query = lambda default, **kwargs: default
        fastapi.Body = lambda default, **kwargs: default
        responses = types.ModuleType("fastapi.responses")
        responses.FileResponse = lambda path: path
        responses.RedirectResponse = lambda path, status_code=307: (path, status_code)
        staticfiles = types.ModuleType("fastapi.staticfiles")
        staticfiles.StaticFiles = lambda **kwargs: kwargs
        modules = {
            "psycopg2": mock.MagicMock(), "redis": mock.MagicMock(),
            "fastapi": fastapi, "fastapi.responses": responses,
            "fastapi.staticfiles": staticfiles,
        }
        with mock.patch.dict(sys.modules, modules):
            cls.dashboard = importlib.import_module("dashboard.app")

    def test_smb_path_maps_only_data_share(self):
        self.assertEqual(
            r"\\192.168.68.105\data\import\document.docx",
            self.dashboard.smb_path("/volume1/data/import/document.docx"),
        )
        self.assertEqual("", self.dashboard.smb_path("/volume1/private/document.docx"))

    def test_workset_response_is_read_only_and_exposes_reason(self):
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        row = {
            "file_id": 1, "content_group_id": "group", "filename": "document.docx",
            "extension": "docx", "path": "/volume1/data/import/document.docx",
            "size_bytes": 42, "workset_status": "active",
            "reason_code": "filesystem_mtime_within_configured_window",
            "last_qualifying_activity_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
            "category": None, "document_family": None,
            "latest_review_decision": "accepted",
            "latest_review_family": "interview_preparation",
        }
        with mock.patch.object(self.dashboard, "db_connect", return_value=connection), mock.patch.object(
            self.dashboard, "query_one", side_effect=[
                {"total": 3, "active": 1, "inactive": 1, "needs_review": 1},
                {"available": False},
            ],
        ), mock.patch.object(self.dashboard, "query_all", return_value=[row]) as query_all:
            result = self.dashboard.workset(
                status="active", extension="docx", search="document", limit=50, offset=0,
            )
        self.assertEqual("read_only", result["mode"])
        self.assertEqual(
            {"database_writes": False, "file_mutations": False, "model_updates": False},
            result["safety"],
        )
        self.assertEqual("not_reviewed", result["documents"][0]["classification_status"])
        self.assertEqual("interview_preparation", result["documents"][0]["effective_document_family"])
        self.assertEqual("accepted_portal_review", result["documents"][0]["effective_family_source"])
        self.assertEqual(
            "interview_preparation",
            result["documents"][0]["target_proposal"]["document_family_code"],
        )
        self.assertIn("filesystem_mtime", result["documents"][0]["reason_code"])
        self.assertEqual(r"\\192.168.68.105\data\import\document.docx", result["documents"][0]["smb_path"])
        params = query_all.call_args.args[2]
        self.assertEqual(("active", "docx", "%document%", "%document%"), params)

    def test_source_limits_mutation_to_append_only_review_events(self):
        source = (ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
        self.assertEqual(1, source.count("@app.post"))
        self.assertIn("INSERT INTO public.document_review_events", source)
        self.assertNotIn("UPDATE public.", source)
        self.assertNotIn("DELETE FROM", source)
        self.assertNotIn("shutil.move", source)
        self.assertIn('"model_updates": False', source)
        self.assertIn("ILIKE %s", source)
        self.assertIn("enriched[offset:offset + limit]", source)

    def test_review_is_append_only_and_does_not_update_model_or_file(self):
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        review_id = uuid.uuid4()
        cursor.fetchone.return_value = (
            review_id, datetime(2026, 8, 11, tzinfo=timezone.utc), 1, "accepted",
        )
        row = {
            "file_id": 1, "content_group_id": uuid.uuid4(), "content_sha256": "a" * 64,
            "filename": "vacature.docx", "extension": "docx",
            "path": "/volume1/data/Documenten/CV & Sollicitaties/UWV/vacature.docx",
            "size_bytes": 42, "workset_status": "active", "category": None,
            "document_family": None, "lifecycle": None,
        }
        with mock.patch.dict("os.environ", {"CORE_REVIEW_WRITES_ENABLED": "true"}), mock.patch.object(
            self.dashboard, "db_connect", return_value=connection,
        ), mock.patch.object(
            self.dashboard, "query_one", return_value={"available": True},
        ), mock.patch.object(
            self.dashboard, "query_all", side_effect=[[row], []],
        ):
            result = self.dashboard.create_workset_review({
                "file_id": 1, "idempotency_key": str(uuid.uuid4()),
                "decision": "accepted", "corrected_document_family_code": "vacancies",
            })
        sql = cursor.execute.call_args_list[0].args[0]
        self.assertIn("INSERT INTO public.document_review_events", sql)
        self.assertNotIn("UPDATE", sql)
        self.assertEqual(str(review_id), result["review_id"])
        self.assertFalse(result["file_mutations"])
        self.assertFalse(result["model_updates"])


if __name__ == "__main__":
    unittest.main()
