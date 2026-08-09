import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Scrum78MetadataIndexMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.migration = (
            ROOT
            / "database/migrations/20260809_remove_redundant_metadata_file_id_index.sql"
        ).read_text(encoding="utf-8")
        cls.rollback = (
            ROOT
            / "database/migrations/rollback/20260809_remove_redundant_metadata_file_id_index.sql"
        ).read_text(encoding="utf-8")
        cls.schema = (ROOT / "database/schema/schema.sql").read_text(encoding="utf-8")
        cls.verify = (
            ROOT / "database/assessment/scrum78_verify_metadata_file_id_index.sql"
        ).read_text(encoding="utf-8")

    def test_forward_migration_drops_only_redundant_index_concurrently(self):
        self.assertIn(
            "DROP INDEX CONCURRENTLY IF EXISTS public.idx_metadata_file_id",
            self.migration,
        )
        self.assertNotIn("DROP INDEX CONCURRENTLY IF EXISTS public.metadata_file_id_unique", self.migration)
        self.assertNotIn("BEGIN", self.migration.upper())

    def test_rollback_recreates_index_concurrently_and_idempotently(self):
        self.assertIn(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_metadata_file_id",
            self.rollback,
        )
        self.assertIn("ON public.metadata USING btree (file_id)", self.rollback)
        self.assertNotIn("BEGIN", self.rollback.upper())

    def test_fresh_schema_has_unique_index_but_not_redundant_index(self):
        self.assertIn("ADD CONSTRAINT metadata_file_id_unique UNIQUE (file_id)", self.schema)
        self.assertNotIn("CREATE INDEX idx_metadata_file_id ", self.schema)

    def test_post_check_verifies_index_and_representative_lookup(self):
        self.assertIn("metadata_file_id_unique", self.verify)
        self.assertIn("idx_metadata_file_id", self.verify)
        self.assertIn("EXPLAIN (ANALYZE, BUFFERS)", self.verify)


if __name__ == "__main__":
    unittest.main()
