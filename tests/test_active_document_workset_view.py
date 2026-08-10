import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "database/migrations/20260810_add_active_document_workset_view.sql"
ROLLBACK = ROOT / "database/migrations/rollback/20260810_add_active_document_workset_view.sql"


class ActiveDocumentWorksetViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")

    def test_view_is_policy_backed_and_scoped_to_current_golden_records(self):
        self.assertIn("CREATE OR REPLACE VIEW public.v_active_document_workset", self.sql)
        self.assertIn("FROM public.v_current_policies", self.sql)
        self.assertIn("p.policy_code = 'active_document_workset'", self.sql)
        self.assertIn("f.id = cg.golden_file_id", self.sql)
        self.assertIn("f.deleted_at IS NULL", self.sql)
        self.assertIn("jsonb_array_elements_text(p.configuration -> 'extensions')", self.sql)
        self.assertIn("jsonb_array_elements_text(p.configuration -> 'source_roots')", self.sql)

    def test_view_uses_temporal_profile_and_policy_window(self):
        self.assertIn("v_file_temporal_profile", self.sql)
        self.assertIn("make_interval(months => d.activity_window_months)", self.sql)
        self.assertIn("source_metadata_modified", self.sql)
        self.assertIn("source_metadata_created", self.sql)
        self.assertIn("filesystem_mtime", self.sql)
        self.assertNotIn("f.created_at", self.sql)

    def test_view_is_explainable_and_fail_safe(self):
        self.assertIn("'conflicting_temporal_evidence'", self.sql)
        self.assertIn("'invalid_or_missing_activity_timestamp'", self.sql)
        self.assertIn("'active'", self.sql)
        self.assertIn("'inactive'", self.sql)
        self.assertIn("'needs_review'", self.sql)
        self.assertIn("policy_checksum", self.sql)
        self.assertIn("policy_version", self.sql)

    def test_migration_has_no_data_or_file_mutation(self):
        upper = self.sql.upper()
        self.assertNotIn("INSERT INTO", upper)
        self.assertNotIn("UPDATE ", upper)
        self.assertNotIn("DELETE FROM", upper)
        self.assertEqual(
            "BEGIN;\n\nDROP VIEW IF EXISTS public.v_active_document_workset;\n\nCOMMIT;\n",
            self.rollback,
        )


if __name__ == "__main__":
    unittest.main()
