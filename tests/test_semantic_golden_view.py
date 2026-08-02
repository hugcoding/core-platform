import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SemanticGoldenViewMigrationTests(unittest.TestCase):
    def test_forward_migration_is_repeatable_and_exposes_freshness(self):
        sql = (ROOT / "database/migrations/20260802_add_semantic_golden_records_view.sql").read_text("utf-8")
        self.assertIn("CREATE OR REPLACE VIEW public.v_semantic_golden_records", sql)
        self.assertIn("DISTINCT ON (sd.file_id)", sql)
        self.assertIn("'stale_content_group'", sql)
        self.assertIn("semantic_metadata_current", sql)
        self.assertIn("CREATE INDEX IF NOT EXISTS", sql)
        self.assertIn("f.deleted_at IS NULL", sql)

    def test_rollback_removes_only_owned_view_and_indexes(self):
        sql = (ROOT / "database/migrations/rollback/20260802_add_semantic_golden_records_view.sql").read_text("utf-8")
        self.assertIn("DROP VIEW IF EXISTS public.v_semantic_golden_records", sql)
        self.assertNotIn("DROP TABLE", sql)
        self.assertNotIn("CASCADE", sql)


if __name__ == "__main__":
    unittest.main()
