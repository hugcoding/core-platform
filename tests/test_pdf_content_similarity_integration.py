import unittest
from pathlib import Path

from tools.runtime.pdf_content_similarity import insert_sql


ROOT = Path(__file__).parents[1]


class PdfContentSimilarityIntegrationTests(unittest.TestCase):
    def test_migration_is_append_only_and_has_no_cleanup_handoff(self):
        sql = (ROOT / "database/migrations/20260829_add_pdf_content_similarity_review.sql").read_text("utf-8")
        self.assertIn("pdf_content_similarity_evidence", sql)
        self.assertIn("pdf_content_similarity_review_events", sql)
        self.assertIn("reject_pdf_similarity_mutation", sql)
        self.assertIn("count(DISTINCT content_sha256) > 1", sql)
        self.assertIn("count(DISTINCT page_text_sha256) = 1", sql)
        self.assertIn("r.evidence_ids = g.evidence_ids", sql)
        self.assertNotIn("UPDATE public.files", sql)
        self.assertNotIn("DELETE FROM public.files", sql)
        self.assertNotIn("quarantine", sql.lower())

    def test_portal_exposes_separate_advisory_review(self):
        html = (ROOT / "dashboard/static/workset.html").read_text("utf-8")
        script = (ROOT / "dashboard/static/pdf-similarity-review.js").read_text("utf-8")
        app = (ROOT / "dashboard/app.py").read_text("utf-8")
        self.assertIn('id="pdfSimilaritySection"', html)
        self.assertIn("Zelfde documentversie", script)
        self.assertIn("Bewust apart bewaren", script)
        self.assertIn('@app.get("/api/v1/workset/pdf-similarity")', app)
        self.assertIn('"cleanup_handoff": False', app)

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


if __name__ == "__main__":
    unittest.main()
