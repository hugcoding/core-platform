import os
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.cleanup import duplicate_executor
from core.migration import personal_executor


ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "database/migrations/20260822_add_duplicate_cleanup_executor.sql"
ROLLBACK = ROOT / "database/migrations/rollback/20260822_add_duplicate_cleanup_executor.sql"
RUNTIME = ROOT / "tools/runtime/duplicate_cleanup_executor.py"


def load_runtime():
    spec = importlib.util.spec_from_file_location("duplicate_cleanup_runtime", RUNTIME)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DuplicateCleanupExecutorTests(unittest.TestCase):
    def test_schema_is_append_only_reversible_and_has_no_purge(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        rollback = ROLLBACK.read_text(encoding="utf-8")
        for table in ("duplicate_cleanup_plans", "duplicate_cleanup_plan_items", "duplicate_cleanup_events"):
            self.assertIn("CREATE TABLE IF NOT EXISTS public." + table, sql)
            self.assertIn("DROP TABLE IF EXISTS public." + table, rollback)
        self.assertIn("reject_duplicate_cleanup_mutation", sql)
        self.assertIn("v_duplicate_cleanup_item_status", sql)
        self.assertNotIn("'purged'", sql)
        self.assertNotIn("DELETE FROM public.files", sql)

    def test_runtime_uses_validated_handoff_and_explicit_confirmation(self):
        runtime = RUNTIME.read_text(encoding="utf-8")
        self.assertIn("public.v_exact_duplicate_review_handoff", runtime)
        self.assertIn("h.eligible_for_executor", runtime)
        self.assertIn("explicit_confirmation_required", runtime)
        self.assertIn("physical_purge_supported", runtime)
        self.assertIn("core_duplicate_quarantine", runtime)
        self.assertIn("qualifies_for_activation", runtime)

    def test_cli_exposes_reversible_cleanup_lifecycle(self):
        cli = (ROOT / "tools/runtime/core").read_text(encoding="utf-8")
        for command in (
            "duplicates plan", "duplicates approve", "duplicates execute",
            "duplicates reconcile", "duplicates rollback",
        ):
            self.assertIn(command, cli)

    def test_quarantine_move_and_rollback_preserve_leader_hash_and_mtime(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / "data"
            leader = data / "Persoonlijk/Actief/leader.pdf"
            source = data / "import/redundant.pdf"
            target = data / ".core/quarantaine/duplicaten/group/redundant.pdf"
            leader.parent.mkdir(parents=True)
            source.parent.mkdir(parents=True)
            leader.write_bytes(b"exact duplicate")
            source.write_bytes(b"exact duplicate")
            expected_mtime = 1_700_000_000_123_456_789
            os.utime(source, ns=(expected_mtime, expected_mtime))
            expected_mtime = source.stat().st_mtime_ns
            digest = personal_executor.sha256_file(source)
            item = {
                "leader_path": str(leader), "source_path": str(source),
                "target_path": str(target), "size_bytes": source.stat().st_size,
                "content_sha256": digest, "mtime_ns": expected_mtime,
            }
            zones = (data / ".core/quarantaine/duplicaten",)
            with patch.object(personal_executor, "DATA_ROOT", data), patch.object(
                duplicate_executor, "QUARANTINE_ZONES", zones
            ):
                result = duplicate_executor.move_verified(item)
                self.assertTrue(result["leader_hash_verified"])
                self.assertTrue(leader.exists())
                self.assertFalse(source.exists())
                self.assertEqual(digest, personal_executor.sha256_file(target))
                self.assertEqual(expected_mtime, target.stat().st_mtime_ns)
                duplicate_executor.rollback_verified(item)
                self.assertTrue(leader.exists())
                self.assertTrue(source.exists())
                self.assertFalse(target.exists())

    def test_changed_or_missing_leader_blocks_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / "data"
            source = data / "import/redundant.pdf"
            target = data / ".core/quarantaine/duplicaten/group/redundant.pdf"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"expected")
            digest = personal_executor.sha256_file(source)
            item = {"leader_path": str(data / "missing.pdf"), "source_path": str(source),
                    "target_path": str(target), "size_bytes": source.stat().st_size,
                    "content_sha256": digest}
            with self.assertRaisesRegex(personal_executor.MigrationSafetyError, "leader_missing"):
                duplicate_executor.inspect_preconditions(item)

    def test_reconciliation_prefers_effective_moved_event(self):
        runtime = load_runtime()
        item = {
            "id": "item-1", "redundant_file_id": "42", "content_sha256": "abc123",
            "source_path": "/volume1/data/import/source.pdf",
            "target_path": "/volume1/data/.core/quarantaine/duplicaten/group/source.pdf",
        }
        with patch.object(runtime, "copy_rows", return_value=[{
            "id": "move-event", "event_type": "MOVED",
        }]) as query, patch.object(runtime, "event") as append_event:
            self.assertTrue(runtime.correlate("plan-1", item, "tester"))
        self.assertEqual(query.call_count, 1)
        details = append_event.call_args.args[5]
        self.assertEqual(details["correlation_kind"], "effective_moved_event")
        self.assertFalse(details["qualifies_for_activation"])

    def test_reconciliation_accepts_deleted_only_with_verified_evidence(self):
        runtime = load_runtime()
        item = {
            "id": "item-1", "redundant_file_id": "42", "content_sha256": "ABC123",
            "source_path": "/volume1/data/import/source.pdf",
            "target_path": "/volume1/data/.core/quarantaine/duplicaten/group/source.pdf",
        }
        with patch.object(runtime, "copy_rows", side_effect=[[], [{
            "id": "delete-event", "event_type": "DELETED",
        }]]) as query, patch.object(runtime, "event") as append_event:
            self.assertTrue(runtime.correlate("plan-1", item, "tester"))
        self.assertEqual(query.call_count, 2)
        fallback_sql = query.call_args_list[1].args[0]
        self.assertIn("verified.event_type='verified'", fallback_sql)
        self.assertIn("verified.details->>'content_sha256'='abc123'", fallback_sql)
        self.assertIn("verified.details->>'target_path'", fallback_sql)
        details = append_event.call_args.args[5]
        self.assertEqual(details["file_event_type"], "DELETED")
        self.assertEqual(details["correlation_kind"], "verified_move_to_excluded_quarantine")
        self.assertFalse(details["physical_purge"])
        self.assertTrue(details["recovery_available"])

    def test_reconciliation_rejects_unverified_deleted_event(self):
        runtime = load_runtime()
        item = {
            "id": "item-1", "redundant_file_id": "42", "content_sha256": "abc123",
            "source_path": "/volume1/data/import/source.pdf",
            "target_path": "/volume1/data/.core/quarantaine/duplicaten/group/source.pdf",
        }
        with patch.object(runtime, "copy_rows", side_effect=[[], []]), patch.object(
            runtime, "event"
        ) as append_event:
            self.assertFalse(runtime.correlate("plan-1", item, "tester"))
        append_event.assert_not_called()

    def test_reconciliation_uses_a_stable_idempotency_key(self):
        runtime = load_runtime()
        item = {
            "id": "item-1", "redundant_file_id": "42", "content_sha256": "abc123",
            "source_path": "/volume1/data/import/source.pdf",
            "target_path": "/volume1/data/.core/quarantaine/duplicaten/group/source.pdf",
        }
        keys = []
        for _ in range(2):
            with patch.object(runtime, "copy_rows", side_effect=[[], [{
                "id": "delete-event", "event_type": "DELETED",
            }]]), patch.object(runtime, "event") as append_event:
                self.assertTrue(runtime.correlate("plan-1", item, "tester"))
                keys.append(append_event.call_args.args[3])
        self.assertEqual(keys, [
            "plan-1:item-1:correlated:delete-event",
            "plan-1:item-1:correlated:delete-event",
        ])


if __name__ == "__main__":
    unittest.main()
