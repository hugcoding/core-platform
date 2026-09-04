import unittest
from unittest import mock
from pathlib import Path
from datetime import datetime, timezone

from core.execution.queue import (
    build_flat_file_correction, build_flat_golden_correction, exclude_already_controlled,
    flat_personal_correction, partition_candidates, select_batch, check_source_availability,
)
from tools.runtime import controlled_execution_queue as runtime

ROOT = Path(__file__).parents[1]


class ControlledExecutionQueueTests(unittest.TestCase):
    def candidate(self, file_id, action, target):
        return {"file_id": file_id, "action_type": action,
                "source_path": f"/volume1/data/source/{file_id}.pdf", "target_path": target}

    def test_materialized_handoff_preserves_all_safety_conditions(self):
        original = (ROOT / "database/migrations/20260821_add_exact_duplicate_review.sql").read_text("utf-8")
        updated = (ROOT / "database/migrations/20260902_optimize_exact_duplicate_handoff.sql").read_text("utf-8")
        original_select = original.split("CREATE OR REPLACE VIEW public.v_exact_duplicate_review_handoff AS\n", 1)[1].split(";", 1)[0]
        updated_select = updated.split(")\nSELECT\n", 1)[1].split(";", 1)[0]
        updated_select = "SELECT\n" + updated_select.replace("JOIN groups_snapshot groups", "JOIN public.v_exact_duplicate_review_groups groups")
        self.assertEqual(original_select.strip(), updated_select.strip())
        self.assertIn("AS MATERIALIZED", updated)

    def test_flat_candidate_prefilter_keeps_both_registered_and_migrated_paths(self):
        source = (ROOT / "dashboard/app.py").read_text("utf-8")
        query = source.split('flat_files = query_all(conn, """', 1)[1].split('""")', 1)[0]
        self.assertIn("current_locations AS MATERIALIZED", query)
        self.assertIn("SELECT id FROM public.files WHERE path LIKE", query)
        self.assertIn("UNION", query)
        self.assertIn("SELECT file_id FROM current_locations WHERE current_path LIKE", query)
        self.assertIn("COALESCE(location.current_path, f.path)", query)

    def test_fifty_item_limit(self):
        rows = [self.candidate(i, "migrate_active", f"/volume1/data/target/{i}.pdf") for i in range(60)]
        self.assertEqual(50, len(select_batch(rows)))
        self.assertEqual(50, len(select_batch(rows, 50)))
        self.assertEqual(25, len(select_batch(rows, 25)))
        for limit in (0, 51):
            with self.assertRaises(ValueError):
                select_batch(rows, limit)
        sql = (ROOT / "database/migrations/20260902_expand_controlled_execution_batches.sql").read_text("utf-8")
        self.assertIn("item_count BETWEEN 1 AND 50", sql)
        self.assertIn("sequence_no BETWEEN 1 AND 50", sql)
        self.assertIn("maximaal 50 bestanden", (ROOT / "dashboard/static/workset.html").read_text("utf-8"))

    def test_missing_source_stays_blocked_until_repaired(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.pdf"
            candidate = {"file_id": 1, "source_path": str(source)}
            for _ in range(2):
                ready, blocked = check_source_availability([candidate])
                self.assertEqual([], ready)
                self.assertEqual("source_missing", blocked[0]["blocked_reason"])
            source.touch()
            self.assertEqual(([candidate], []), check_source_availability([candidate]))
            self.assertEqual("source_not_regular_file", check_source_availability([
                {"file_id": 2, "source_path": directory}])[1][0]["blocked_reason"])

    def test_changed_size_and_existing_target_are_not_offered_repeatedly(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory)/'source', Path(directory)/'target'
            source.write_bytes(b'changed')
            item={'file_id':1,'source_path':str(source),'target_path':str(target),'size_bytes':1}
            for _ in range(2):
                ready,blocked=check_source_availability([item])
                self.assertFalse(ready)
                self.assertEqual('source_size_changed',blocked[0]['blocked_reason'])
            item['size_bytes']=source.stat().st_size
            target.write_bytes(b'different')
            for _ in range(2):
                self.assertEqual('target_collision',check_source_availability([item])[1][0]['blocked_reason'])
            target.unlink()
            self.assertEqual(([item],[]),check_source_availability([item]))

    def test_hash_failure_is_held_until_plan_evidence_changes(self):
        from core.execution.queue import hold_previous_failures
        item={'file_id':1,'source_path':'/source','target_path':'/target','content_sha256':'a','size_bytes':1}
        history=[{**item,'current_status':'blocked','latest_details':{'reason':'source_hash_changed'}}]
        self.assertFalse(hold_previous_failures([item],history)[0])
        self.assertEqual([{**item,'content_sha256':'b'}],hold_previous_failures([{**item,'content_sha256':'b'}],history)[0])

    def test_deletion_candidates_use_current_location_for_selection_and_exclusion(self):
        from tools.runtime.personal_migration_executor import DELETION_CANDIDATES
        self.assertIn("COALESCE(location.current_path, file.path) AS source_path", DELETION_CANDIDATES)
        self.assertIn("location ON location.file_id = file.id", DELETION_CANDIDATES)
        self.assertIn("COALESCE(location.current_path, file.path) NOT LIKE '/volume1/data/.core/quarantaine/%'", DELETION_CANDIDATES)

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

    def test_duplicate_batch_target_is_blocked_before_approval(self):
        target = "/volume1/data/Persoonlijk/Actief/Werk/zelfde.pdf"
        rows = [self.candidate(1, "migrate_active", target),
                self.candidate(2, "migrate_active", target)]
        ready, blocked = partition_candidates(rows)
        self.assertEqual([], ready)
        self.assertEqual([1, 2], sorted(item["file_id"] for item in blocked))
        self.assertTrue(all(item["blocked_reason"] == "batch_target_collision" for item in blocked))

    def test_failed_batch_does_not_permanently_hide_unexecuted_item(self):
        app = (ROOT / "dashboard/app.py").read_text("utf-8")
        self.assertIn("batch.batch_status IN ('approved','queued','started','paused','rollback_pending')", app)
        self.assertIn("status.current_status IN ('verified','completed','event_correlated','blocked')", app)

    def test_successful_old_target_allows_corrective_migration(self):
        candidate = self.candidate(7, "migrate_inactive", "/volume1/data/Persoonlijk/Inactief/Te beoordelen/7.pdf")
        controlled = [{"file_id": 7, "target_path": "/volume1/data/Persoonlijk/Inactief/7.pdf",
                       "current_status": "verified", "batch_status": "completed"}]
        self.assertEqual([candidate], exclude_already_controlled([candidate], controlled))

    def test_reached_target_and_active_file_are_suppressed(self):
        candidate = self.candidate(7, "migrate_inactive", "/volume1/data/Persoonlijk/Inactief/Te beoordelen/7.pdf")
        reached = [{"file_id": 7, "target_path": candidate["target_path"],
                    "current_status": "verified", "batch_status": "completed"}]
        active = [{"file_id": 7, "target_path": "/volume1/data/elders/7.pdf",
                   "current_status": "planned", "batch_status": "started"}]
        self.assertEqual([], exclude_already_controlled([candidate], reached))
        self.assertEqual([], exclude_already_controlled([candidate], active))

    def test_corrective_migration_uses_verified_current_location(self):
        migration = (ROOT / "tools/runtime/personal_migration_executor.py").read_text("utf-8")
        self.assertIn("COALESCE(location.current_path, v.source_path) AS source_path", migration)
        self.assertIn("LEFT JOIN public.v_workset_current_physical_location location", migration)

    def test_flat_golden_record_gets_independent_fallback_correction(self):
        self.assertEqual(
            ("migrate_inactive", "/volume1/data/Persoonlijk/Inactief/Te beoordelen/payroll.pdf"),
            flat_personal_correction("/volume1/data/Persoonlijk/Inactief/payroll.pdf"),
        )
        self.assertEqual(
            ("migrate_active", "/volume1/data/Persoonlijk/Actief/Te beoordelen/cv.pdf"),
            flat_personal_correction("/volume1/data/Persoonlijk/Actief/cv.pdf"),
        )
        self.assertIsNone(flat_personal_correction("/volume1/data/Persoonlijk/Inactief/Werk/payroll.pdf"))

    def test_dashboard_queues_flat_golden_record_outside_workset_projection(self):
        app = (ROOT / "dashboard/app.py").read_text("utf-8")
        self.assertIn("build_flat_file_correction(file_row)", app)
        self.assertIn("^/volume1/data/Persoonlijk/(Actief|Inactief)/[^/]+$", app)
        self.assertIn("*direct_corrections.values()", app)

    def test_duplicate_review_builds_executable_flat_golden_correction(self):
        candidate = build_flat_golden_correction({
            "file_id": 3362590,
            "leader_file_id": 3361628,
            "leader_path": "/volume1/data/Persoonlijk/Inactief/payroll.pdf",
            "reviewed_at": "2026-08-31T12:00:00+00:00",
        }, {"content_sha256": "a" * 64, "size_bytes": 123})
        self.assertEqual(3361628, candidate["file_id"])
        self.assertEqual("migrate_inactive", candidate["action_type"])
        self.assertEqual(
            "/volume1/data/Persoonlijk/Inactief/Te beoordelen/payroll.pdf",
            candidate["target_path"],
        )
        self.assertEqual("flat_golden_record_correction", candidate["evidence_snapshot"]["kind"])

    def test_every_flat_personal_file_gets_controlled_review_fallback(self):
        candidate = build_flat_file_correction({
            "file_id": 42,
            "source_path": "/volume1/data/Persoonlijk/Actief/los.pdf",
            "content_sha256": "b" * 64,
            "size_bytes": 456,
            "updated_at": "2026-08-31T12:00:00+00:00",
        })
        self.assertEqual("migrate_active", candidate["action_type"])
        self.assertEqual(
            "/volume1/data/Persoonlijk/Actief/Te beoordelen/los.pdf",
            candidate["target_path"],
        )
        self.assertEqual("flat_personal_root_correction", candidate["evidence_snapshot"]["kind"])

    def test_duplicate_card_exposes_pending_golden_record_correction(self):
        app = (ROOT / "dashboard/app.py").read_text("utf-8")
        ui = (ROOT / "dashboard/static/execution-queue.js").read_text("utf-8")
        self.assertIn('"leader_correction_target": corrective_targets.get', app)
        self.assertIn('leader_candidates = [row for row in inventory', app)
        self.assertIn('queue_rank <= 500 OR file_id = ANY(%s)', app)
        self.assertIn('PERSONAL_MIGRATION_CANDIDATES.replace("%", "%%")', app)
        self.assertIn("Huidige locatie:", ui)
        self.assertIn("Nog te corrigeren naar:", ui)

    def test_dashboard_completes_reviewed_directory_targets_before_partitioning(self):
        app = (ROOT / "dashboard/app.py").read_text("utf-8")
        expected = "ensure_taxonomy_subdirectory_target(complete_directory_target(dict(row)))"
        self.assertIn(expected, app)
        self.assertLess(
            app.index(expected),
            app.index("ready, blocked = partition_candidates", app.index("def controlled_execution_candidates")),
        )

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
        self.assertIn("Geen bruikbaar categorie-/familiepad; daarom onder Te beoordelen.", script)
        self.assertIn("executionBatchPause", html)
        self.assertIn("executionBatchRollback", html)
        self.assertIn("/execution-batches/current", script)
        self.assertIn("control('cancel')", script)
        app = (ROOT / "dashboard/app.py").read_text("utf-8")
        self.assertIn("h.selected_file_id AS leader_file_id", app)
        self.assertIn("h.selected_path AS leader_path", app)
        self.assertIn("'leader_path',h.selected_path", app)
        self.assertIn("resume interrupted item before cancelling batch", app)

    def test_execution_document_links_are_separate_from_selection(self):
        script = (ROOT / "dashboard/static/execution-queue.js").read_text("utf-8")
        self.assertIn('/api/v1/workset/${Number(fileId)}/content', script)
        self.assertIn('target="_blank" rel="noopener noreferrer"', script)
        self.assertIn('documentLink(candidate.file_id,candidate.source_path)', script)
        self.assertIn('documentLink(candidate.leader_file_id,candidate.leader_path)', script)
        self.assertIn('return `<div class="execution-queue-item"><label><input', script)
        self.assertIn('checked></label><span>', script)
        self.assertNotIn('<label class="execution-queue-item">', script)
        self.assertNotIn('documentLink(candidate.file_id,candidate.target_path)', script)
        self.assertIn('Quarantainepad: ${esc(candidate.target_path)}', script)
        self.assertIn('Nog te corrigeren naar: ${esc(candidate.leader_correction_target)}', script)

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
