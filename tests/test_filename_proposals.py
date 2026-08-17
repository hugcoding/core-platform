import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from core.organization.filename_normalization import normalize_proposed_filename, target_with_filename


ROOT = Path(__file__).resolve().parents[1]


class FilenameNormalizationTests(unittest.TestCase):
    def test_preserves_original_extension_and_normalizes_invalid_characters(self):
        result = normalize_proposed_filename(
            "Hugo: CV?.docx", current_filename="oud.pdf",
        )
        self.assertEqual("Hugo_ CV.pdf", result["normalized"])
        self.assertIn("original_extension_preserved", result["reason_codes"])
        self.assertIn("invalid_filename_characters_normalized", result["reason_codes"])

    def test_appends_original_extension_when_omitted(self):
        result = normalize_proposed_filename("Aangifte 2025", current_filename="scan.PDF")
        self.assertEqual("Aangifte 2025.PDF", result["normalized"])
        self.assertIn("original_extension_appended", result["reason_codes"])

    def test_replaces_only_filename_in_target(self):
        self.assertEqual(
            "/volume1/data/Persoonlijk/Actief/Werk/Nieuw.pdf",
            target_with_filename("/volume1/data/Persoonlijk/Actief/Werk/Oud.pdf", "Nieuw.pdf"),
        )

    def test_migration_is_append_only_and_rollback_removes_only_new_fields(self):
        migration = (ROOT / "database/migrations/20260815_add_review_filename_proposals.sql").read_text()
        rollback = (ROOT / "database/migrations/rollback/20260815_add_review_filename_proposals.sql").read_text()
        for field in ("source_filename", "proposed_filename_raw", "proposed_filename",
                      "filename_normalization_reasons", "target_path_conflict_details"):
            self.assertIn(field, migration)
            self.assertIn(field, rollback)
        self.assertNotIn("UPDATE public.document_review_events", migration)
        self.assertNotIn("DELETE FROM public.document_review_events", migration)
        self.assertNotIn("DROP TABLE", rollback)


class FilenamePortalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_dashboard_workset import DashboardWorksetTests
        DashboardWorksetTests.setUpClass()
        cls.dashboard = DashboardWorksetTests.dashboard

    def test_live_preview_reports_existing_target_conflict(self):
        connection = mock.MagicMock(); connection.__enter__.return_value = connection
        row = {"file_id": 1, "filename": "oud.pdf", "extension": "pdf",
               "path": "/volume1/data/import/oud.pdf", "workset_status": "active", "lifecycle": None}
        with mock.patch.object(self.dashboard, "db_connect", return_value=connection), mock.patch.object(
            self.dashboard, "query_all", side_effect=[[row], [], [{"id": 2}], []],
        ):
            result = self.dashboard.workset_target_path_preview(
                1, "finance", "tax_documents", "Aangifte 2025.docx",
            )
        self.assertTrue(result["target_path_conflict"])
        self.assertEqual("Aangifte 2025.pdf", result["filename_proposal"]["normalized"])
        self.assertTrue(result["suggested_target_path"].endswith("/Aangifte 2025.pdf"))
        self.assertFalse(result["file_mutations"])

    def test_live_preview_combines_manual_directory_and_safe_filename(self):
        connection = mock.MagicMock(); connection.__enter__.return_value = connection
        row = {"file_id": 1, "filename": "oud.pdf", "extension": "pdf",
               "path": "/volume1/data/import/oud.pdf", "workset_status": "active", "lifecycle": None}
        with mock.patch.object(self.dashboard, "db_connect", return_value=connection), mock.patch.object(
            self.dashboard, "query_all", side_effect=[[row], [], [], []],
        ):
            result = self.dashboard.workset_target_path_preview(
                1, "finance", "tax_documents", "Nieuw", 
                "/volume1/data/Persoonlijk/Actief/Geldzaken/Belastingen",
            )
        self.assertEqual(
            "/volume1/data/Persoonlijk/Actief/Geldzaken/Belastingen/Nieuw.pdf",
            result["suggested_target_path"],
        )

    def test_review_stores_raw_and_normalized_name_without_file_mutation(self):
        connection = mock.MagicMock(); connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        review_id = uuid.uuid4()
        cursor.fetchone.return_value = (review_id, datetime(2026, 8, 15, tzinfo=timezone.utc), 1, "accepted")
        row = {"file_id": 1, "content_group_id": uuid.uuid4(), "content_sha256": "a" * 64,
               "filename": "oud.pdf", "extension": "pdf", "path": "/volume1/data/import/oud.pdf",
               "size_bytes": 42, "workset_status": "active", "category": None,
               "document_family": None, "lifecycle": None}
        with mock.patch.dict("os.environ", {"CORE_REVIEW_WRITES_ENABLED": "true"}), mock.patch.object(
            self.dashboard, "db_connect", return_value=connection,
        ), mock.patch.object(self.dashboard, "query_one", return_value={"available": True}), mock.patch.object(
            self.dashboard, "query_all", side_effect=[[row], [], [], [], []],
        ):
            result = self.dashboard.create_workset_review({
                "file_id": 1, "idempotency_key": str(uuid.uuid4()), "decision": "accepted",
                "corrected_category_code": "finance", "corrected_document_family_code": "tax_documents",
                "proposed_filename": "Aangifte: 2025.docx",
            })
        sql = cursor.execute.call_args_list[0].args[0]
        self.assertIn("proposed_filename_raw", sql)
        self.assertEqual("Aangifte: 2025.docx", result["proposed_filename_raw"])
        self.assertEqual("Aangifte_ 2025.pdf", result["proposed_filename"])
        self.assertFalse(result["file_mutations"])
        self.assertFalse(result["model_updates"])

    def test_portal_exposes_filename_input_and_live_conflict_warning(self):
        script = (ROOT / "dashboard/static/workset.js").read_text(encoding="utf-8")
        self.assertIn("proposed-filename", script)
        self.assertIn("payload.proposed_filename", script)
        self.assertIn("target_path_conflict", script)
        self.assertIn("De huidige extensie blijft behouden", script)


if __name__ == "__main__":
    unittest.main()
