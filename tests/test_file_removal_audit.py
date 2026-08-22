import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "database/migrations/20260823_add_file_removal_audit_view.sql"
ROLLBACK = ROOT / "database/migrations/rollback/20260823_add_file_removal_audit_view.sql"


class FileRemovalAuditViewTests(unittest.TestCase):
    def test_view_uses_only_effective_deleted_events(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("CREATE OR REPLACE VIEW public.v_file_removal_audit", sql)
        self.assertIn("FROM public.v_file_events_effective file_event", sql)
        self.assertIn("WHERE file_event.event_type = 'DELETED'", sql)
        self.assertNotIn("UPDATE public.file_events", sql)
        self.assertNotIn("DELETE FROM public.file_events", sql)

    def test_view_distinguishes_proven_core_operations_from_unattributed_removals(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        for value in (
            "core_quarantine", "core_migration", "external_or_unattributed",
            "core_managed", "unattributed", "correlated", "observed_only",
        ):
            self.assertIn(value, sql)
        self.assertNotIn("'manual'", sql)

    def test_view_requires_append_only_correlation_and_verification_evidence(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("duplicate_cleanup_events", sql)
        self.assertIn("personal_migration_events", sql)
        self.assertGreaterEqual(sql.count("event_type = 'event_correlated'"), 2)
        self.assertGreaterEqual(sql.count("event_type = 'verified'"), 2)
        self.assertIn("event.details->>'file_event_id' = file_event.id::text", sql)
        self.assertIn("verified_sha256", sql)
        self.assertIn("recovery_available", sql)
        self.assertIn("physical_purge", sql)

    def test_rollback_only_drops_the_view(self):
        rollback = ROLLBACK.read_text(encoding="utf-8")
        self.assertIn("DROP VIEW IF EXISTS public.v_file_removal_audit", rollback)
        self.assertNotIn("DROP TABLE", rollback)


if __name__ == "__main__":
    unittest.main()
