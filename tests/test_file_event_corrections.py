import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class FileEventCorrectionMigrationTests(unittest.TestCase):
    def test_corrections_are_append_only_and_effective_view_excludes_them(self):
        sql = (ROOT / "database/migrations/20260822_add_file_event_corrections.sql").read_text()
        self.assertIn("file_event_corrections", sql)
        self.assertIn("append-only", sql)
        self.assertIn("invalidated_as_non_material", sql)
        self.assertIn("CREATE OR REPLACE VIEW public.v_file_events_effective", sql)
        self.assertNotIn("DELETE FROM public.file_events", sql)

    def test_rollback_restores_original_effective_view(self):
        sql = (ROOT / "database/migrations/rollback/20260822_add_file_event_corrections.sql").read_text()
        self.assertIn("event_status <> 'invalidated'", sql)
        self.assertIn("DROP TABLE IF EXISTS public.file_event_corrections", sql)

    def test_duplicate_delete_correction_is_append_only_and_reversible(self):
        migration = (ROOT / "database/migrations/20260823_add_duplicate_delete_corrections.sql").read_text()
        rollback = (ROOT / "database/migrations/rollback/20260823_add_duplicate_delete_corrections.sql").read_text()
        self.assertIn("'duplicate_observation'", migration)
        self.assertIn("CREATE OR REPLACE VIEW public.v_file_events_effective", migration)
        self.assertNotIn("DELETE FROM public.file_events", migration)
        self.assertNotIn("UPDATE public.file_events", migration)
        self.assertIn("duplicate-observation evidence is preserved but inactive", rollback)


class FileEventCorrectionRuntimeTests(unittest.TestCase):
    def test_apply_requires_explicit_confirmation_and_never_changes_files(self):
        source = (ROOT / "tools/runtime/file_event_corrections.py").read_text()
        self.assertIn("INVALIDATE_NON_MATERIAL_WATCHER_EVENTS", source)
        self.assertIn("event.source = 'filesystem_watcher'", source)
        self.assertIn("interval '5 minutes'", source)
        self.assertIn('"file_mutations": False', source)
        self.assertNotIn("DELETE FROM", source)

    def test_operational_consumers_use_effective_history(self):
        dashboard = (ROOT / "dashboard/app.py").read_text()
        identity = (ROOT / "core/integrity/file_identity.py").read_text()
        personal = (ROOT / "tools/runtime/personal_migration_executor.py").read_text()
        duplicates = (ROOT / "tools/runtime/duplicate_cleanup_executor.py").read_text()

        self.assertIn("FROM v_file_events_effective", dashboard)
        self.assertEqual(2, identity.count("FROM v_file_events_effective"))
        self.assertIn("FROM public.v_file_events_effective", personal)
        self.assertIn("FROM public.v_file_events_effective", duplicates)

    def test_raw_history_is_reserved_for_writes_audit_and_correction_selection(self):
        dashboard = (ROOT / "dashboard/app.py").read_text()
        identity = (ROOT / "core/integrity/file_identity.py").read_text()

        self.assertNotIn("FROM file_events ", dashboard)
        self.assertNotIn("FROM file_events ", identity)

    def test_duplicate_delete_tool_requires_exact_sources_and_no_state_change(self):
        source = (ROOT / "tools/runtime/file_event_corrections.py").read_text()
        cli = (ROOT / "tools/runtime/core").read_text()
        self.assertIn("INVALIDATE_DUPLICATE_DELETE_OBSERVATIONS", source)
        self.assertIn("scanner.source = 'polling_scanner'", source)
        self.assertIn("candidate.source = 'filesystem_watcher'", source)
        for event_type in ("RESTORED", "CREATED", "MOVED", "RENAMED"):
            self.assertIn("'" + event_type + "'", source)
        self.assertIn("correct-duplicate-deletes", cli)
        self.assertIn('"original_events_deleted": False', source)


if __name__ == "__main__":
    unittest.main()
