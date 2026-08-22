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


class FileEventCorrectionRuntimeTests(unittest.TestCase):
    def test_apply_requires_explicit_confirmation_and_never_changes_files(self):
        source = (ROOT / "tools/runtime/file_event_corrections.py").read_text()
        self.assertIn("INVALIDATE_NON_MATERIAL_WATCHER_EVENTS", source)
        self.assertIn("event.source = 'filesystem_watcher'", source)
        self.assertIn("interval '5 minutes'", source)
        self.assertIn('"file_mutations": False', source)
        self.assertNotIn("DELETE FROM", source)


if __name__ == "__main__":
    unittest.main()
