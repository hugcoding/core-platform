import unittest
from pathlib import Path


class ContentGroupsMigrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.sql = (
            root / "database" / "migrations" / "20260727_add_content_groups.sql"
        ).read_text(encoding="utf-8")

    def test_golden_file_is_required_and_references_a_member(self):
        self.assertIn("golden_file_id integer NOT NULL", self.sql)
        self.assertIn("FOREIGN KEY (id, golden_file_id)", self.sql)
        self.assertIn(
            "REFERENCES public.content_group_members(content_group_id, file_id)",
            self.sql,
        )

    def test_exact_content_group_is_unique(self):
        self.assertIn(
            "CONSTRAINT content_groups_hash_size_unique UNIQUE NULLS NOT DISTINCT",
            self.sql,
        )

    def test_golden_flag_is_derived_not_stored_twice(self):
        self.assertIn("(m.file_id = g.golden_file_id) AS is_golden", self.sql)
        self.assertNotIn("is_golden boolean", self.sql)

    def test_selection_is_versioned_and_timezone_aware(self):
        self.assertIn("algorithm_version text NOT NULL", self.sql)
        self.assertIn("selected_at timestamptz NOT NULL", self.sql)
        self.assertIn("assessed_at timestamptz NOT NULL", self.sql)


if __name__ == "__main__":
    unittest.main()
