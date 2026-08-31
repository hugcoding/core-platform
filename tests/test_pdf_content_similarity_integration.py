import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from tools.runtime.pdf_content_similarity import analyze_with_available_runtime, insert_sql


ROOT = Path(__file__).parents[1]


class PdfContentSimilarityIntegrationTests(unittest.TestCase):
    def test_migration_is_append_only_and_has_no_cleanup_handoff(self):
        sql = (ROOT / "database/migrations/20260829_add_pdf_content_similarity_review.sql").read_text("utf-8")
        self.assertIn("pdf_content_similarity_evidence", sql)
        self.assertIn("pdf_content_similarity_review_events", sql)
        self.assertIn("reject_pdf_similarity_mutation", sql)
        self.assertIn("count(DISTINCT content_sha256) > 1", sql)
        self.assertIn("count(DISTINCT page_text_sha256) = 1", sql)
        self.assertIn("g.file_ids <@ r.file_ids", sql)
        self.assertIn("g.evidence_ids <@ r.evidence_ids", sql)
        self.assertNotIn("UPDATE public.files", sql)
        self.assertNotIn("DELETE FROM public.files", sql)
        self.assertNotIn("quarantine", sql.lower())

    def test_portal_exposes_separate_advisory_review(self):
        html = (ROOT / "dashboard/static/workset.html").read_text("utf-8")
        script = (ROOT / "dashboard/static/pdf-similarity-review.js").read_text("utf-8")
        app = (ROOT / "dashboard/app.py").read_text("utf-8")
        self.assertIn('id="pdfSimilaritySection"', html)
        self.assertIn("Bewust apart bewaren", script)
        self.assertIn("Leidende kopie bevestigen", script)
        self.assertIn('type=\"radio\"', script)
        self.assertIn('pdf-similarity-document-link', script)
        self.assertIn('data-show-file', script)
        self.assertIn("ws('worksetSearch').value=show.dataset.showFile", script)
        self.assertIn('class=\"pdf-similarity-document-link\"', script)
        self.assertIn('/content\" target=\"_blank\"', script)
        self.assertIn('@app.get("/api/v1/workset/pdf-similarity")', app)
        self.assertIn('"cleanup_handoff": False', app)

    def test_leader_selection_is_append_only_and_only_creates_handoff(self):
        sql = (ROOT / "database/migrations/20260829_add_pdf_similarity_leader_selection.sql").read_text("utf-8")
        self.assertIn("selected_file_id", sql)
        self.assertIn("redundant_file_ids", sql)
        self.assertIn("v_pdf_content_similarity_quarantine_handoff", sql)
        self.assertIn("DROP VIEW IF EXISTS public.v_pdf_content_similarity_groups", sql)
        self.assertIn("DROP VIEW IF EXISTS public.v_latest_pdf_content_similarity_review", sql)
        self.assertIn("CREATE VIEW public.v_latest_pdf_content_similarity_review", sql)
        self.assertLess(
            sql.index("CREATE VIEW public.v_latest_pdf_content_similarity_review"),
            sql.index("CREATE VIEW public.v_pdf_content_similarity_groups"),
        )
        self.assertIn("eligible_for_cleanup", sql)
        self.assertIn("separately approved cleanup plan", sql)
        self.assertNotIn("UPDATE public.files", sql)
        self.assertNotIn("DELETE FROM public.files", sql)

    def test_review_stays_effective_when_a_reviewed_redundant_copy_leaves(self):
        migration = ROOT / "database/migrations/20260830_stabilize_pdf_similarity_review_projection.sql"
        rollback = ROOT / "database/migrations/rollback/20260830_stabilize_pdf_similarity_review_projection.sql"
        sql = migration.read_text("utf-8")
        self.assertIn("g.file_ids <@ r.file_ids", sql)
        self.assertIn("g.evidence_ids <@ r.evidence_ids", sql)
        self.assertNotIn("UPDATE public.files", sql)
        self.assertNotIn("DELETE FROM public.files", sql)
        self.assertTrue(rollback.exists())

    def test_new_member_or_new_evidence_does_not_inherit_old_review(self):
        sql = (ROOT / "database/migrations/20260830_stabilize_pdf_similarity_review_projection.sql").read_text("utf-8")
        # The subset direction is deliberate: current members/evidence must all
        # belong to the reviewed snapshot. A newly joined member cannot match.
        self.assertNotIn("r.file_ids <@ g.file_ids", sql)
        self.assertNotIn("r.evidence_ids <@ g.evidence_ids", sql)

    def test_redundant_workset_projection_inherits_leader_without_writes(self):
        migration = ROOT / "database/migrations/20260831_add_similarity_redundant_workset_projection.sql"
        rollback = ROOT / "database/migrations/rollback/20260831_add_similarity_redundant_workset_projection.sql"
        sql = migration.read_text("utf-8")
        self.assertIn("v_pdf_similarity_redundant_workset", sql)
        self.assertIn("review.selected_file_id AS leader_file_id", sql)
        self.assertIn("inherited_category", sql)
        self.assertIn("inherited_document_family", sql)
        self.assertIn("quarantine_phase", sql)
        self.assertNotIn("UPDATE public.files", sql)
        self.assertNotIn("DELETE FROM public.files", sql)
        self.assertTrue(rollback.exists())

    def test_evidence_insert_stores_hashes_but_no_raw_text(self):
        evidence = {
            "content_sha256": "a" * 64, "normalized_text_sha256": "b" * 64,
            "page_text_sha256": ["c" * 64], "page_count": 1,
            "normalized_text_characters": 12, "metadata": {}, "document_id": None,
            "has_digital_signature": False, "extraction_warnings": [],
        }
        sql = insert_sql(3361602, evidence)
        self.assertIn("normalized_text_sha256", sql)
        self.assertNotIn("bankier", sql)
        self.assertNotIn("extracted_text", sql)
        self.assertIn("ON CONFLICT", sql)

    def test_backfill_skips_current_evidence_on_next_run(self):
        runtime = (ROOT / "tools/runtime/pdf_content_similarity.py").read_text("utf-8")
        self.assertIn("NOT EXISTS", runtime)
        self.assertIn("e.analyzer_version", runtime)

    def test_missing_host_pypdf_uses_dashboard_container(self):
        expected = {"content_sha256": "a" * 64}
        missing = ModuleNotFoundError("No module named 'pypdf'", name="pypdf")
        completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(expected), stderr="")
        with mock.patch("tools.runtime.pdf_content_similarity.analyze_pdf", side_effect=missing), mock.patch(
            "tools.runtime.pdf_content_similarity.subprocess.run", return_value=completed,
        ) as runner:
            result = analyze_with_available_runtime(Path("/volume1/data/example.pdf"))
        self.assertEqual(expected, result)
        command = runner.call_args.args[0]
        self.assertEqual(["docker", "compose", "exec", "-T", "dashboard"], command[:5])


if __name__ == "__main__":
    unittest.main()
