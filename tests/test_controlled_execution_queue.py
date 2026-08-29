import unittest
from pathlib import Path

from core.execution.queue import select_batch

ROOT = Path(__file__).parents[1]


class ControlledExecutionQueueTests(unittest.TestCase):
    def candidate(self, file_id, action, target):
        return {"file_id": file_id, "action_type": action,
                "source_path": f"/volume1/data/source/{file_id}.pdf", "target_path": target}

    def test_priority_and_limit_are_deterministic(self):
        rows = [self.candidate(1, "migrate_active", "/volume1/data/Persoonlijk/Actief/1.pdf"),
                self.candidate(2, "quarantine_exact_duplicate", "/volume1/data/.core/quarantaine/duplicaten/2.pdf"),
                self.candidate(3, "quarantine_content_similar", "/volume1/data/.core/quarantaine/duplicaten/inhoudelijk/3.pdf")]
        self.assertEqual([2, 3, 1], [row["file_id"] for row in select_batch(rows)])

    def test_same_file_is_never_queued_twice(self):
        rows = [self.candidate(7, "migrate_inactive", "/volume1/data/Persoonlijk/Inactief/7.pdf"),
                self.candidate(7, "quarantine_exact_duplicate", "/volume1/data/.core/quarantaine/duplicaten/7.pdf")]
        selected = select_batch(rows)
        self.assertEqual(1, len(selected)); self.assertEqual("quarantine_exact_duplicate", selected[0]["action_type"])

    def test_database_contract_is_append_only_and_bounded(self):
        sql = (ROOT / "database/migrations/20260829_add_controlled_execution_queue.sql").read_text("utf-8")
        self.assertIn("item_count BETWEEN 1 AND 25", sql)
        self.assertIn("reject_controlled_execution_mutation", sql)
        self.assertIn("v_controlled_execution_batch_progress", sql)
        self.assertNotIn("UPDATE public.files", sql); self.assertNotIn("DELETE FROM public.files", sql)

    def test_runtime_combines_all_candidate_sources_without_writes(self):
        runtime = (ROOT / "tools/runtime/controlled_execution_queue.py").read_text("utf-8")
        cli = (ROOT / "tools/runtime/core").read_text("utf-8")
        self.assertIn("exact_candidates", runtime)
        self.assertIn("similar_items", runtime)
        self.assertIn("migration_candidates", runtime)
        self.assertIn('"file_mutations": False', runtime)
        self.assertIn("execution-queue", cli)


if __name__ == "__main__": unittest.main()
