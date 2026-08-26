import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.migration import personal_executor as executor


ROOT = Path(__file__).parents[1]


class PersonalMigrationExecutorTests(unittest.TestCase):
    def test_nullable_database_values_do_not_become_empty_sql_literals(self):
        runtime = (ROOT / "tools/runtime/personal_migration_executor.py").read_text()
        self.assertIn("def pg_optional", runtime)
        self.assertIn('value is None or value == ""', runtime)
        self.assertIn('pg_optional(item["lifecycle_reviewed_at"])', runtime)
        self.assertIn('pg_optional(item.get("deletion_nomination_id"))', runtime)

    def test_schema_is_append_only_and_reversible(self):
        sql = (ROOT / "database/migrations/20260821_add_personal_migration_executor.sql").read_text()
        rollback = (ROOT / "database/migrations/rollback/20260821_add_personal_migration_executor.sql").read_text()
        for table in ("personal_migration_plans", "personal_migration_plan_items", "personal_migration_events"):
            self.assertIn("CREATE TABLE IF NOT EXISTS public." + table, sql)
            self.assertIn("DROP TABLE IF EXISTS public." + table, rollback)
        self.assertIn("reject_personal_migration_mutation", sql)
        self.assertIn("event_correlated", sql)
        self.assertNotIn("UPDATE public.personal_migration", sql)
        self.assertNotIn("DELETE FROM public.personal_migration", sql)

    def test_runtime_requires_separate_approval_and_confirmation(self):
        runtime = (ROOT / "tools/runtime/personal_migration_executor.py").read_text()
        self.assertIn('mode.add_argument("--dry-run"', runtime)
        self.assertIn('mode.add_argument("--create-plan"', runtime)
        self.assertIn("plan_not_approved", runtime)
        self.assertIn("i.id,'approved'", runtime)
        self.assertIn("explicit_confirmation_required", runtime)
        self.assertIn("duplicate_review_required", runtime)
        self.assertIn("v_exact_duplicate_review_handoff", runtime)
        self.assertIn('item["duplicate_resolution"] = "golden_only"', runtime)
        self.assertIn("target_path_reviewed_at,duplicate_resolution", runtime)
        self.assertIn("qualifies_for_activation", runtime)

    def test_duplicate_handoff_must_cover_every_other_available_copy(self):
        runtime = (ROOT / "tools/runtime/personal_migration_executor.py").read_text()
        self.assertIn("reviewed_redundant_copies != available_copies - 1", runtime)
        self.assertIn("h.selected_file_id = v.file_id", runtime)
        self.assertIn("h.eligible_for_executor", runtime)

    def test_candidate_query_uses_current_content_group_hash_column(self):
        runtime = (ROOT / "tools/runtime/personal_migration_executor.py").read_text()
        self.assertIn("g.content_sha256 = v.content_sha256", runtime)
        self.assertNotIn("g.hash_content", runtime)

    def test_plan_root_contract_accepts_canonical_data_root(self):
        base = (ROOT / "database/migrations/20260821_add_personal_migration_executor.sql").read_text()
        fix = (ROOT / "database/migrations/20260823_fix_personal_migration_root_contract.sql").read_text()
        rollback = (ROOT / "database/migrations/rollback/20260823_fix_personal_migration_root_contract.sql").read_text()
        contract = "source_root = '/volume1/data' OR source_root LIKE '/volume1/data/%'"
        self.assertIn(contract, base)
        self.assertIn(contract, fix)
        self.assertIn("rollback blocked: canonical /volume1/data migration plans exist", rollback)
        self.assertNotIn("DELETE FROM public.personal_migration_plans", fix)

    def test_core_cli_exposes_full_migration_lifecycle(self):
        cli = (ROOT / "tools/runtime/core").read_text()
        for command in ("migrate plan", "migrate approve", "migrate execute", "migrate reconcile", "migrate rollback", "run-all"):
            self.assertIn(command, cli)

    def test_run_all_retains_bounded_batches_and_explicit_confirmation(self):
        runtime = (ROOT / "tools/runtime/personal_migration_executor.py").read_text()
        self.assertIn('require_confirmation(args.confirm, "MIGRATE_ALL_REVIEWED")', runtime)
        self.assertIn('all_batches.add_argument("--batch-size", type=int, default=100)', runtime)
        self.assertIn('all_batches.add_argument("--max-batches", type=int, default=10)', runtime)
        self.assertIn('"physical_purge": False', runtime)
        self.assertIn("maximum_batch_count_reached", runtime)
        self.assertIn('("approved", "moving", "moved", "failed")', runtime)
        self.assertIn('item["current_status"] == "failed"', runtime)

    def test_rollback_can_be_limited_to_directory_shaped_review_targets(self):
        runtime = (ROOT / "tools/runtime/personal_migration_executor.py").read_text()
        self.assertIn('command.add_argument("--directory-targets-only", action="store_true")', runtime)
        self.assertIn('args.directory_targets_only and not is_directory_shaped_target(item)', runtime)
        self.assertIn('target_suffix != source_suffix', runtime)
        self.assertIn('"directory_targets_only" if args.directory_targets_only', runtime)

    def test_v2_routes_active_deletion_nominations_to_reversible_quarantine(self):
        runtime = (ROOT / "tools/runtime/personal_migration_executor.py").read_text()
        migration = (ROOT / "database/migrations/20260824_extend_personal_migration_to_deletion_quarantine.sql").read_text()
        rollback = (ROOT / "database/migrations/rollback/20260824_extend_personal_migration_to_deletion_quarantine.sql").read_text()
        self.assertIn("personal-migration-executor-v2", runtime)
        self.assertIn("v_active_document_lifecycle_nominations", runtime)
        self.assertIn("nomination.nomination_type = 'deletion'", runtime)
        self.assertIn("/volume1/data/.core/quarantaine/verwijderreview/", runtime)
        self.assertIn("core_deletion_quarantine", runtime)
        self.assertIn("physical_purge=False", runtime)
        self.assertIn("deletion_nomination_no_longer_current", runtime)
        self.assertIn("already_in_duplicate_cleanup", runtime)
        self.assertIn("deletion_nomination_id", migration)
        self.assertIn("effective_lifecycle = 'deletion_review'", migration)
        self.assertIn("rollback blocked: deletion-quarantine migration plans exist", rollback)

    def test_deletion_nomination_has_priority_over_active_or_archive_route(self):
        runtime = (ROOT / "tools/runtime/personal_migration_executor.py").read_text()
        self.assertIn("candidate_priority", runtime)
        self.assertIn("NOT EXISTS (", runtime)
        self.assertIn("nomination.nomination_type = 'deletion'", runtime)
        self.assertIn('item["duplicate_resolution"] = "deletion_review"', runtime)

    def test_policy_backed_workset_candidates_fill_the_remaining_migration_set(self):
        runtime = (ROOT / "tools/runtime/personal_migration_executor.py").read_text()
        migration = (ROOT / "database/migrations/20260824_add_policy_backed_personal_migration.sql").read_text()
        rollback = (ROOT / "database/migrations/rollback/20260824_add_policy_backed_personal_migration.sql").read_text()
        self.assertIn("'workset_policy' END AS lifecycle_basis", runtime)
        self.assertIn("'core_proposal'", runtime)
        self.assertIn("'zone_fallback'", runtime)
        self.assertIn("batch_target_collision", runtime)
        self.assertIn("WHERE source_path <> target_path", runtime)
        self.assertNotIn("AND v.lifecycle_reviewed_at IS NOT NULL", runtime)
        self.assertNotIn("AND v.target_path_decision = 'accepted'", runtime)
        self.assertIn("lifecycle_basis", migration)
        self.assertIn("target_path_basis", migration)
        self.assertIn("DROP NOT NULL", migration)
        self.assertIn("rollback blocked: policy-backed personal migration plans exist", rollback)

    def test_path_validation_rejects_escape_and_wrong_zone(self):
        with self.assertRaises(executor.MigrationSafetyError):
            executor.validate_paths("/tmp/source.pdf", "/volume1/data/Persoonlijk/Actief/a.pdf")
        with self.assertRaises(executor.MigrationSafetyError):
            executor.validate_paths("/volume1/data/source.pdf", "/volume1/data/Anders/a.pdf")

    def test_verified_move_and_rollback_preserve_hash_and_mtime(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "data"
            source = data / "import" / "source.pdf"
            target = data / "Persoonlijk" / "Actief" / "Wonen" / "source.pdf"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"controlled migration")
            expected_mtime = 1_700_000_000_123_456_789
            os.utime(source, ns=(expected_mtime, expected_mtime))
            expected_mtime = source.stat().st_mtime_ns
            digest = executor.sha256_file(source)
            item = {"source_path": str(source), "target_path": str(target),
                    "size_bytes": source.stat().st_size, "content_sha256": digest}
            with patch.object(executor, "DATA_ROOT", data), patch.object(
                executor, "PERSONAL_ROOT", data / "Persoonlijk"
            ), patch.object(executor, "ALLOWED_ZONES", (data / "Persoonlijk/Actief", data / "Persoonlijk/Inactief")):
                result = executor.move_verified(item)
                self.assertFalse(source.exists())
                self.assertEqual(digest, executor.sha256_file(target))
                self.assertEqual(expected_mtime, target.stat().st_mtime_ns)
                rollback_item = dict(item, mtime_ns=result["mtime_ns"])
                executor.rollback_verified(rollback_item)
                self.assertTrue(source.exists())
                self.assertFalse(target.exists())
                self.assertEqual(expected_mtime, source.stat().st_mtime_ns)

    def test_collision_blocks_even_when_content_is_identical(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); data = root / "data"
            source = data / "import/a.pdf"; target = data / "Persoonlijk/Actief/a.pdf"
            source.parent.mkdir(parents=True); target.parent.mkdir(parents=True)
            source.write_bytes(b"same"); target.write_bytes(b"same")
            item = {"source_path": str(source), "target_path": str(target),
                    "size_bytes": 4, "content_sha256": executor.sha256_file(source)}
            with patch.object(executor, "DATA_ROOT", data), patch.object(
                executor, "PERSONAL_ROOT", data / "Persoonlijk"
            ), patch.object(executor, "ALLOWED_ZONES", (data / "Persoonlijk/Actief", data / "Persoonlijk/Inactief")):
                with self.assertRaisesRegex(executor.MigrationSafetyError, "target_collision"):
                    executor.inspect_preconditions(item)

    def test_intermediate_target_file_is_blocked_before_move(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / "data"
            source = data / "import/a.pdf"
            blocking_parent = data / "Persoonlijk/Actief/Werk"
            source.parent.mkdir(parents=True)
            blocking_parent.parent.mkdir(parents=True)
            source.write_bytes(b"source")
            blocking_parent.write_bytes(b"not a directory")
            target = blocking_parent / "a.pdf"
            with patch.object(executor, "DATA_ROOT", data), patch.object(
                executor, "ALLOWED_ZONES", (data / "Persoonlijk/Actief", data / "Persoonlijk/Inactief")
            ):
                with self.assertRaisesRegex(executor.MigrationSafetyError, "target_parent_not_directory"):
                    executor.validate_paths(source, target)

    def test_interrupted_hardlink_move_can_resume_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / "data"
            source = data / "import/a.pdf"; target = data / "Persoonlijk/Actief/a.pdf"
            source.parent.mkdir(parents=True); target.parent.mkdir(parents=True)
            source.write_bytes(b"resume"); os.link(source, target)
            item = {"source_path": str(source), "target_path": str(target),
                    "size_bytes": 6, "content_sha256": executor.sha256_file(source),
                    "mtime_ns": source.stat().st_mtime_ns}
            with patch.object(executor, "DATA_ROOT", data), patch.object(
                executor, "ALLOWED_ZONES", (data / "Persoonlijk/Actief", data / "Persoonlijk/Inactief")):
                result = executor.resume_verified_move(item)
                self.assertTrue(result["resumed"])
                self.assertFalse(source.exists())
                self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
