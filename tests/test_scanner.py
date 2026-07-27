import sys
import types
import unittest
from unittest import mock


if "redis" not in sys.modules:
    redis_stub = types.ModuleType("redis")
    redis_stub.Redis = lambda *args, **kwargs: None
    sys.modules["redis"] = redis_stub

if "psycopg2" not in sys.modules:
    psycopg2_stub = types.ModuleType("psycopg2")
    psycopg2_stub.connect = lambda *args, **kwargs: None
    sys.modules["psycopg2"] = psycopg2_stub

import scanner


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.events = []

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, **kwargs):
        self.values[key] = value
        return True

    def delete(self, key):
        self.values.pop(key, None)

    def hgetall(self, key):
        return dict(self.values.get(key, {}))

    def hdel(self, key, field):
        self.values.get(key, {}).pop(field, None)

    def eval(self, script, numkeys, key, field, expected):
        values = self.values.get(key, {})
        if values.get(field) != expected:
            return 0
        values.pop(field, None)
        return 1

    def scan_iter(self, match=None, count=None):
        prefix = match[:-1] if match and match.endswith("*") else match
        return iter([key for key in list(self.values) if not prefix or key.startswith(prefix)])

    def xadd(self, stream, data):
        self.events.append((stream, data))

    def pipeline(self, transaction=False):
        return self

    def execute(self):
        return []


class ScannerStateTests(unittest.TestCase):
    def setUp(self):
        self.original_redis = scanner.r
        self.original_threshold = scanner.MISSING_SCAN_THRESHOLD
        self.original_roots = scanner.SCAN_ROOTS
        scanner.r = FakeRedis()
        scanner.MISSING_SCAN_THRESHOLD = 2

    def tearDown(self):
        scanner.r = self.original_redis
        scanner.MISSING_SCAN_THRESHOLD = self.original_threshold
        scanner.SCAN_ROOTS = self.original_roots

    def test_unchanged_file_is_marked_seen_without_new_event(self):
        path = "/volume1/share/file.txt"

        self.assertTrue(scanner.changed(path, "10:20:30", "scan-1"))
        self.assertFalse(scanner.changed(path, "10:20:30", "scan-2"))

        state = scanner.parse_file_state(scanner.r.get(scanner.SIGNATURE_PREFIX + path))
        self.assertEqual(("10:20:30", "scan-2", 0), state)

    def test_missing_file_is_deleted_only_after_threshold(self):
        path = "/volume1/share/old-name.txt"
        key = scanner.SIGNATURE_PREFIX + path
        scanner.r.set(key, scanner.encode_file_state("10:20:30", "scan-1"))

        checked, deleted = scanner.reconcile_missing("scan-2")
        self.assertEqual((1, 0), (checked, deleted))
        self.assertEqual([], scanner.r.events)

        checked, deleted = scanner.reconcile_missing("scan-3")
        self.assertEqual((1, 1), (checked, deleted))
        self.assertNotIn(key, scanner.r.values)
        self.assertEqual("DELETE", scanner.r.events[0][1]["event"])
        self.assertEqual(path, scanner.r.events[0][1]["path"])

    def test_delete_event_carries_scan_session(self):
        path = "/volume1/share/old.txt"
        scanner.r.set(
            scanner.SIGNATURE_PREFIX + path,
            scanner.encode_file_state("10:20:30", "scan-1", missing_scans=1),
        )

        scanner.reconcile_missing("scan-2", session_id="session-7")

        self.assertEqual("session-7", scanner.r.events[0][1]["scan_session_id"])

    def test_seen_file_is_not_reconciled_as_missing(self):
        path = "/volume1/share/current.txt"
        scanner.changed(path, "10:20:30", "scan-current")

        checked, deleted = scanner.reconcile_missing("scan-current")

        self.assertEqual((0, 0), (checked, deleted))
        self.assertEqual([], scanner.r.events)

    def test_interval_update_preserves_full_sweep_state(self):
        path = "/volume1/share/file.txt"
        key = scanner.SIGNATURE_PREFIX + path
        scanner.r.set(key, scanner.encode_file_state("old", "full-1", missing_scans=1))

        self.assertTrue(scanner.changed(path, "new", "interval-9", full_sweep=False))

        self.assertEqual(("new", "full-1", 1), scanner.parse_file_state(scanner.r.get(key)))

    def test_interval_scan_never_reconciles_missing_files(self):
        path = "/volume1/share/missing.txt"
        key = scanner.SIGNATURE_PREFIX + path
        scanner.r.set(key, scanner.encode_file_state("sig", "full-1", missing_scans=1))

        result = scanner._scan_roots([], "interval-1", None, full_sweep=False)

        self.assertEqual((0, 0, 0, 0), result)
        self.assertIn(key, scanner.r.values)
        self.assertEqual([], scanner.r.events)

    def test_interval_roots_rotate_persistently(self):
        roots = ["/volume1/a", "/volume1/b"]

        self.assertEqual("/volume1/a", scanner.select_interval_root(roots))
        self.assertEqual("/volume1/b", scanner.select_interval_root(roots))
        self.assertEqual("/volume1/a", scanner.select_interval_root(roots))

    def test_dirty_root_takes_priority_and_is_removed_after_success(self):
        scanner.r.values[scanner.DIRTY_ROOTS_KEY] = {
            "/volume1/b": "2026-07-26T10:00:00+00:00",
        }

        with (
            mock.patch.object(scanner, "discover_roots", return_value=["/volume1/a", "/volume1/b"]),
            mock.patch.object(scanner, "run_scan", return_value=(1, 1, 0, 0)) as run_scan,
        ):
            result = scanner.scan_interval_once()

        self.assertEqual((1, 1, 0, 0), result)
        run_scan.assert_called_once_with(
            "interval",
            ["/volume1/b"],
            full_sweep=True,
            reconcile_scope="/volume1/b",
            missing_threshold=1,
        )
        self.assertEqual({}, scanner.r.values[scanner.DIRTY_ROOTS_KEY])

    def test_failed_dirty_root_scan_keeps_recovery_marker(self):
        scanner.r.values[scanner.DIRTY_ROOTS_KEY] = {
            "/volume1/b": "2026-07-26T10:00:00+00:00",
        }

        with (
            mock.patch.object(scanner, "discover_roots", return_value=["/volume1/b"]),
            mock.patch.object(scanner, "run_scan", side_effect=OSError("mount unavailable")),
        ):
            with self.assertRaises(OSError):
                scanner.scan_interval_once()

        self.assertIn("/volume1/b", scanner.r.values[scanner.DIRTY_ROOTS_KEY])

    def test_dirty_marker_changed_during_scan_is_not_removed(self):
        scanner.r.values[scanner.DIRTY_ROOTS_KEY] = {
            "/volume1/b": "old-marker",
        }

        def run_scan(*args, **kwargs):
            scanner.r.values[scanner.DIRTY_ROOTS_KEY]["/volume1/b"] = "new-marker"
            return 1, 1, 0, 0

        with (
            mock.patch.object(scanner, "discover_roots", return_value=["/volume1/b"]),
            mock.patch.object(scanner, "run_scan", side_effect=run_scan),
        ):
            scanner.scan_interval_once()

        self.assertEqual(
            "new-marker",
            scanner.r.values[scanner.DIRTY_ROOTS_KEY]["/volume1/b"],
        )

    def test_scoped_reconciliation_does_not_delete_outside_root(self):
        inside = "/volume1/data/missing.txt"
        outside = "/volume1/homes/keep.txt"
        scanner.r.set(
            scanner.SIGNATURE_PREFIX + inside,
            scanner.encode_file_state("sig", "older"),
        )
        scanner.r.set(
            scanner.SIGNATURE_PREFIX + outside,
            scanner.encode_file_state("sig", "older"),
        )

        checked, deleted = scanner.reconcile_missing(
            "current",
            root_scope="/volume1/data",
            threshold=1,
        )

        self.assertEqual((1, 1), (checked, deleted))
        self.assertEqual(inside, scanner.r.events[0][1]["path"])
        self.assertIn(scanner.SIGNATURE_PREFIX + outside, scanner.r.values)

    def test_manual_full_request_is_consumed_once(self):
        scanner.r.set(scanner.FULL_SCAN_REQUEST_KEY, "2026-07-21T17:00:00Z")

        self.assertTrue(scanner.consume_full_scan_request())
        self.assertFalse(scanner.consume_full_scan_request())

    def test_wait_is_interrupted_by_manual_full_request(self):
        scanner.r.set(scanner.FULL_SCAN_REQUEST_KEY, "now")

        with mock.patch.object(scanner.time, "sleep") as sleep:
            scanner.wait_for_next_scan(600)

        sleep.assert_not_called()

    def test_hash_backfill_request_is_consumed_once(self):
        source = "/volume1/backup/Documents"
        scanner.r.set(scanner.HASH_BACKFILL_REQUEST_KEY, source)

        self.assertEqual(source, scanner.consume_hash_backfill_request())
        self.assertIsNone(scanner.consume_hash_backfill_request())

    def test_hash_backfill_enqueues_only_paths_returned_by_database(self):
        cursor = mock.MagicMock()
        cursor.fetchall.return_value = [
            ("/volume1/backup/Documents/a.pdf",),
            ("/volume1/backup/Documents/b.docx",),
        ]
        connection = mock.MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        with mock.patch.object(scanner, "get_db", return_value=connection):
            count = scanner.run_hash_backfill("/volume1/backup/Documents")

        self.assertEqual(2, count)
        self.assertEqual(2, len(scanner.r.events))
        self.assertTrue(all(event[1]["source"] == "hash_backfill" for event in scanner.r.events))
        query, params = cursor.execute.call_args.args
        self.assertIn("content_sha256 IS NULL", query)
        self.assertEqual("/volume1/backup/Documents", params[1])

    def test_scan_once_registers_a_full_session(self):
        calls = []

        def session_call(query, params=(), fetch=False):
            calls.append((query, params, fetch))
            return "session-1" if "create_scan_session" in query else None

        with (
            mock.patch.object(scanner, "discover_roots", return_value=["/volume1/share"]),
            mock.patch.object(scanner, "session_call", side_effect=session_call),
            mock.patch.object(scanner, "_scan_roots", return_value=(0, 0, 0, 0)),
        ):
            scanner.scan_once()

        self.assertEqual(("full",), calls[0][1])

    def test_full_scan_without_roots_aborts_before_reconciliation(self):
        with mock.patch.object(scanner, "discover_roots", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "no scan roots"):
                scanner.scan_once()

    def test_configured_scan_roots_form_an_allowlist(self):
        scanner.SCAN_ROOTS = (
            "/volume1/backup/NITRO/D/data/hugo/Documents",
            "/volume1/data",
        )
        with mock.patch.object(scanner.os.path, "isdir", return_value=True):
            roots = scanner.discover_roots()

        self.assertEqual(
            [
                "/volume1/backup/NITRO/D/data/hugo/Documents",
                "/volume1/data",
            ],
            roots,
        )

    def test_full_reconciliation_is_scoped_to_scanned_roots(self):
        calls = []
        with (
            mock.patch.object(scanner.os, "walk", return_value=[]),
            mock.patch.object(
                scanner,
                "reconcile_missing",
                side_effect=lambda *args, **kwargs: calls.append(kwargs["root_scope"]) or (0, 0),
            ),
        ):
            scanner._scan_roots(
                ["/volume1/data", "/volume1/backup/Documents"],
                "scan",
                None,
                full_sweep=True,
            )

        self.assertEqual(
            ["/volume1/data", "/volume1/backup/Documents"],
            calls,
        )

    def test_failed_full_walk_does_not_reconcile(self):
        path = "/volume1/share/missing.txt"
        key = scanner.SIGNATURE_PREFIX + path
        scanner.r.set(key, scanner.encode_file_state("sig", "full-1", missing_scans=1))

        with mock.patch.object(scanner.os, "walk", side_effect=OSError("mount failed")):
            with self.assertRaises(OSError):
                scanner._scan_roots(["/volume1/share"], "full-2", None, full_sweep=True)

        self.assertIn(key, scanner.r.values)
        self.assertEqual([], scanner.r.events)


if __name__ == "__main__":
    unittest.main()
