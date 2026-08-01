import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class EmptyGoldenMigrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = (ROOT / "database/migrations/20260801_exclude_empty_golden_records.sql").read_text()
        cls.rollback = (
            ROOT / "database/migrations/rollback/20260801_exclude_empty_golden_records.sql"
        ).read_text()

    def test_legacy_empty_groups_are_audited_before_removal(self):
        self.assertLess(self.sql.index("INSERT INTO public.file_events"), self.sql.index("DELETE FROM public.content_groups"))
        self.assertIn("excluded_empty_file", self.sql)
        self.assertIn("migration_20260801_exclude_empty_golden_records", self.sql)

    def test_database_prevents_new_empty_content_groups(self):
        self.assertIn("content_groups_nonempty_check", self.sql)
        self.assertIn("CHECK (size_bytes > 0)", self.sql)

    def test_derived_full_hash_is_cleared_but_file_row_is_preserved(self):
        self.assertIn("UPDATE public.files", self.sql)
        self.assertIn("SET content_sha256 = NULL", self.sql)
        self.assertNotIn("DELETE FROM public.files", self.sql)

    def test_rollback_does_not_reconstruct_meaningless_groups(self):
        self.assertIn("DROP CONSTRAINT IF EXISTS content_groups_nonempty_check", self.rollback)
        self.assertNotIn("INSERT INTO public.content_groups", self.rollback)


if __name__ == "__main__":
    unittest.main()
