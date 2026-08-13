from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "database/migrations/20260811_add_document_review_events.sql"
ROLLBACK = ROOT / "database/migrations/rollback/20260811_add_document_review_events.sql"
REFINEMENT = ROOT / "database/migrations/20260811_add_review_refinement_proposals.sql"
CATEGORY = ROOT / "database/migrations/20260812_add_review_category_choice.sql"
RAW_PATH = ROOT / "database/migrations/20260813_add_review_raw_target_path.sql"


class DocumentReviewEventsMigrationTests(unittest.TestCase):
    def test_append_only_auditable_review_contract(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS public.document_review_events", sql)
        self.assertIn("idempotency_key text NOT NULL UNIQUE", sql)
        self.assertIn("content_sha256 text NOT NULL", sql)
        self.assertIn("supersedes_event_id uuid", sql)
        self.assertIn("CREATE OR REPLACE VIEW public.v_latest_document_review", sql)
        self.assertNotIn("ON DELETE CASCADE", sql)
        self.assertNotIn("UPDATE public.document_review_events", sql)

    def test_structured_refinement_proposals_are_separate_from_contract(self):
        sql = REFINEMENT.read_text(encoding="utf-8")
        for field in ("proposed_category_label", "proposed_family_label", "proposed_target_path"):
            self.assertIn(field, sql)
        self.assertIn("v_document_taxonomy_refinement_queue", sql)
        self.assertNotIn("UPDATE public.document_review_events", sql)

    def test_rollback_is_scoped(self):
        sql = ROLLBACK.read_text(encoding="utf-8")
        self.assertIn("DROP VIEW IF EXISTS public.v_latest_document_review", sql)
        self.assertIn("DROP TABLE IF EXISTS public.document_review_events", sql)

    def test_category_choice_is_append_only_and_viewed(self):
        sql = CATEGORY.read_text(encoding="utf-8")
        self.assertIn("corrected_category_code", sql)
        self.assertIn("CREATE OR REPLACE VIEW public.v_latest_document_review", sql)
        self.assertNotIn("UPDATE public.document_review_events", sql)

    def test_raw_target_path_is_retained_for_audit(self):
        sql = RAW_PATH.read_text(encoding="utf-8")
        self.assertIn("proposed_target_path_raw", sql)
        self.assertNotIn("UPDATE public.document_review_events", sql)


if __name__ == "__main__":
    unittest.main()
