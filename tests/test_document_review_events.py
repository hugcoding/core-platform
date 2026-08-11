from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "database/migrations/20260811_add_document_review_events.sql"
ROLLBACK = ROOT / "database/migrations/rollback/20260811_add_document_review_events.sql"


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

    def test_rollback_is_scoped(self):
        sql = ROLLBACK.read_text(encoding="utf-8")
        self.assertIn("DROP VIEW IF EXISTS public.v_latest_document_review", sql)
        self.assertIn("DROP TABLE IF EXISTS public.document_review_events", sql)


if __name__ == "__main__":
    unittest.main()
