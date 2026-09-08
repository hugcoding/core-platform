import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class WorksetSourceContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = (ROOT / "database/migrations/20260908_add_workset_source_context.sql").read_text("utf-8")

    def test_projection_uses_effective_append_only_events(self):
        self.assertIn("public.v_file_events_effective", self.sql)
        self.assertIn("event.old_path", self.sql)
        self.assertIn("event.new_path", self.sql)
        self.assertNotIn("UPDATE public.file_events", self.sql)
        self.assertNotIn("DELETE FROM", self.sql)

    def test_documents_path_wins_then_earliest_event_is_stable(self):
        documents_rank = self.sql.index("current/documenten/%' THEN 0")
        observed_rank = self.sql.index("source_observed_at", documents_rank)
        event_rank = self.sql.index("source_event_id", observed_rank)
        self.assertLess(documents_rank, observed_rank)
        self.assertLess(observed_rank, event_rank)
        self.assertIn("WHERE position = 1", self.sql)

    def test_projection_is_explicitly_evidence_only(self):
        self.assertIn("for classification evidence only", self.sql)
        self.assertIn("never a physical execution target", self.sql)
        self.assertIn("source_context_relative_path", self.sql)
        self.assertIn("selection_reason", self.sql)

    def test_rollback_only_drops_source_context_view(self):
        rollback = (ROOT / "database/migrations/rollback/20260908_add_workset_source_context.sql").read_text("utf-8")
        self.assertIn("DROP VIEW IF EXISTS public.v_workset_source_context", rollback)
        self.assertNotIn("DROP TABLE", rollback)

    def test_container_integration_fixture_exists(self):
        root = ROOT / "tests/integration/workset-source-context"
        self.assertTrue((root / "compose.yml").is_file())
        self.assertTrue((root / "Dockerfile").is_file())
        runtime = (root / "run.py").read_text("utf-8")
        self.assertIn("workset source context integration passed", runtime)
        self.assertIn("projection must not mutate event history", runtime)


if __name__ == "__main__":
    unittest.main()
