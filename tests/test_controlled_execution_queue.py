import unittest
from unittest import mock
from pathlib import Path
from datetime import datetime, timezone

from core.execution.queue import partition_candidates, select_batch
from tools.runtime import controlled_execution_queue as runtime

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

    def test_path_outside_data_is_blocked_without_disabling_valid_queue(self):
        valid = self.candidate(7, "migrate_active", "/volume1/data/Persoonlijk/Actief/7.pdf")
        outside = {**self.candidate(8, "quarantine_exact_duplicate", "/volume1/data/.core/quarantaine/8.pdf"),
                   "source_path": "/volume1/backup/8.pdf"}
        ready, blocked = partition_candidates([outside, valid])
        self.assertEqual([7], [item["file_id"] for item in ready])
        self.assertEqual(8, blocked[0]["file_id"])
        self.assertIn("outside /volume1/data", blocked[0]["blocked_reason"])

    def test_mixed_review_time_types_sort_deterministically(self):
        rows = [
            {**self.candidate(1, "migrate_active", "/volume1/data/Persoonlijk/Actief/1.pdf"),
             "reviewed_at": datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)},
            {**self.candidate(2, "migrate_active", "/volume1/data/Persoonlijk/Actief/2.pdf"),
             "reviewed_at": "2026-08-28T12:00:00+00:00"},
            {**self.candidate(3, "migrate_active", "/volume1/data/Persoonlijk/Actief/3.pdf"),
             "reviewed_at": None},
        ]
        ready, blocked = partition_candidates(rows)
        self.assertEqual([], blocked)
        self.assertEqual([3, 2, 1], [item["file_id"] for item in ready])
        self.assertTrue(all(isinstance(item["reviewed_at"], str) for item in ready))

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
        self.assertIn("migration_candidates(limit, minimum_free_bytes)", runtime)
        self.assertIn('"--minimum-free-bytes"', runtime)
        self.assertIn('"ready_unique_files"', runtime)
        self.assertIn('"overlapping_candidate_rows"', runtime)
        self.assertIn('"file_mutations": False', runtime)
        self.assertIn("execution-queue", cli)

    def test_migration_inventory_passes_free_space_safety_limit(self):
        with mock.patch.object(runtime, "migration_candidates", return_value=([], [])) as inspect:
            runtime.migration_items(100, 12345)
        inspect.assert_called_once_with(100, 12345)

    def test_workset_exposes_bounded_human_approval_ui(self):
        html = (ROOT / "dashboard/static/workset.html").read_text("utf-8")
        script = (ROOT / "dashboard/static/execution-queue.js").read_text("utf-8")
        self.assertIn('id="executionQueueSection"', html)
        self.assertIn('id="executionQueueApprove"', html)
        self.assertIn("/api/v1/workset/execution-batches", script)
        self.assertIn("data-file-id", script)
        self.assertIn("Behouden golden record", script)
        self.assertIn("Behouden leidende kopie", script)
        self.assertIn("Naar quarantaine", script)
        self.assertIn("executionBatchPause", html)
        self.assertIn("executionBatchRollback", html)
        self.assertIn("/execution-batches/current", script)
        self.assertIn("control('cancel')", script)
        app = (ROOT / "dashboard/app.py").read_text("utf-8")
        self.assertIn("h.selected_file_id AS leader_file_id", app)
        self.assertIn("h.selected_path AS leader_path", app)
        self.assertIn("'leader_path',h.selected_path", app)
        self.assertIn("resume interrupted item before cancelling batch", app)

    def test_dashboard_image_contains_imported_queue_runtime(self):
        dockerfile = (ROOT / "Dockerfile.dashboard").read_text("utf-8")
        app = (ROOT / "dashboard/app.py").read_text("utf-8")
        self.assertIn("from tools.runtime.personal_migration_executor", app)
        self.assertIn("COPY tools ./tools", dockerfile)

    def test_parameterless_dashboard_queries_do_not_bind_percent_patterns(self):
        app = (ROOT / "dashboard/app.py").read_text("utf-8")
        helper_region = app[app.index("def query_one"):app.index("def effective_review_taxonomy")]
        self.assertEqual(2, helper_region.count("if params:"))
        self.assertEqual(2, helper_region.count("cur.execute(sql, params)"))
        self.assertEqual(2, helper_region.count("cur.execute(sql)"))


if __name__ == "__main__": unittest.main()
