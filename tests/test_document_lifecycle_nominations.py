import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "database/migrations/20260815_add_document_lifecycle_nominations.sql"
ROLLBACK = ROOT / "database/migrations/rollback/20260815_add_document_lifecycle_nominations.sql"


class DocumentLifecycleNominationMigrationTests(unittest.TestCase):
    def test_migration_is_append_only_and_independent(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS public.document_lifecycle_nomination_events", sql)
        self.assertIn("nomination_type IN ('archive', 'deletion')", sql)
        self.assertIn("action IN ('nominated', 'withdrawn')", sql)
        self.assertIn("reject_document_lifecycle_nomination_mutation", sql)
        self.assertIn("workset_status_snapshot", sql)
        self.assertNotIn("UPDATE public.files", sql)
        self.assertNotIn("DELETE FROM public.files", sql)

    def test_safe_policy_disables_file_mutation_and_permanent_delete(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("}'::jsonb)\n)\nINSERT INTO public.policy_versions", sql)
        self.assertIn('"direct_file_mutations": false', sql)
        self.assertIn('"automatic_archive_on_deletion_nomination": false', sql)
        self.assertIn('"permanent_delete_enabled": false', sql)
        self.assertIn("'document_retention'", sql)

    def test_rollback_preserves_immutable_policy_snapshot(self):
        sql = ROLLBACK.read_text(encoding="utf-8")
        self.assertIn("DROP TABLE IF EXISTS public.document_lifecycle_nomination_events", sql)
        self.assertNotIn("DELETE FROM public.policy_versions", sql)


if __name__ == "__main__":
    unittest.main()
