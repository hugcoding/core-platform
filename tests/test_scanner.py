import sys
import types
import unittest


if "redis" not in sys.modules:
    redis_stub = types.ModuleType("redis")
    redis_stub.Redis = lambda *args, **kwargs: None
    sys.modules["redis"] = redis_stub

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

    def test_seen_file_is_not_reconciled_as_missing(self):
        path = "/volume1/share/current.txt"
        scanner.changed(path, "10:20:30", "scan-current")

        checked, deleted = scanner.reconcile_missing("scan-current")

        self.assertEqual((0, 0), (checked, deleted))
        self.assertEqual([], scanner.r.events)


if __name__ == "__main__":
    unittest.main()
