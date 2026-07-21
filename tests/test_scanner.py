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

    def scan_iter(self, match=None, count=None):
        prefix = match[:-1] if match and match.endswith("*") else match
        return iter([key for key in list(self.values) if not prefix or key.startswith(prefix)])

    def xadd(self, stream, data):
        self.events.append((stream, data))


class ScannerStateTests(unittest.TestCase):
    def setUp(self):
        self.original_redis = scanner.r
        self.original_threshold = scanner.MISSING_SCAN_THRESHOLD
        scanner.r = FakeRedis()
        scanner.MISSING_SCAN_THRESHOLD = 2

    def tearDown(self):
        scanner.r = self.original_redis
        scanner.MISSING_SCAN_THRESHOLD = self.original_threshold

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
