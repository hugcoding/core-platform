import sys
import types
import unittest
import os
from unittest import mock


if "redis" not in sys.modules:
    redis_stub = types.ModuleType("redis")
    redis_stub.Redis = lambda *args, **kwargs: None
    sys.modules["redis"] = redis_stub

if "watchdog" not in sys.modules:
    watchdog_stub = types.ModuleType("watchdog")
    events_stub = types.ModuleType("watchdog.events")
    observers_stub = types.ModuleType("watchdog.observers")
    events_stub.FileSystemEventHandler = object
    observers_stub.Observer = object
    sys.modules["watchdog"] = watchdog_stub
    sys.modules["watchdog.events"] = events_stub
    sys.modules["watchdog.observers"] = observers_stub

import watcher


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.hashes = {}
        self.events = []

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value

    def xadd(self, stream, payload):
        self.events.append((stream, payload))


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.original_redis = watcher.r
        self.original_root = watcher.SCAN_ROOT
        watcher.r = FakeRedis()
        watcher.SCAN_ROOT = os.path.normpath("/volume1")

    def tearDown(self):
        watcher.r = self.original_redis
        watcher.SCAN_ROOT = self.original_root

    def test_publish_adds_durable_event_and_dirty_root(self):
        self.assertTrue(watcher.publish("UPSERT", "/volume1/data/document.txt"))

        _, payload = watcher.r.events[0]
        self.assertEqual("filesystem_watcher", payload["source"])
        self.assertEqual(os.path.normpath("/volume1/data/document.txt"), payload["path"])
        self.assertIn(
            os.path.normpath("/volume1/data"),
            watcher.r.hashes[watcher.DIRTY_ROOTS_KEY],
        )

    def test_duplicate_event_is_debounced(self):
        path = "/volume1/data/document.txt"

        self.assertTrue(watcher.publish("UPSERT", path))
        self.assertFalse(watcher.publish("UPSERT", path))
        self.assertEqual(1, len(watcher.r.events))

    def test_move_preserves_old_path_and_marks_both_roots_dirty(self):
        handler = watcher.CoreEventHandler()
        event = mock.Mock(
            is_directory=False,
            src_path="/volume1/homes/old.txt",
            dest_path="/volume1/data/new.txt",
        )

        handler.on_moved(event)

        _, payload = watcher.r.events[0]
        self.assertEqual("MOVE", payload["event"])
        self.assertEqual(os.path.normpath("/volume1/homes/old.txt"), payload["old_path"])
        self.assertEqual(
            {
                os.path.normpath("/volume1/homes"),
                os.path.normpath("/volume1/data"),
            },
            set(watcher.r.hashes[watcher.DIRTY_ROOTS_KEY]),
        )

    def test_ignored_path_is_not_published(self):
        self.assertFalse(watcher.publish("UPSERT", "/volume1/photo/@eaDir/thumb.jpg"))
        self.assertEqual([], watcher.r.events)


if __name__ == "__main__":
    unittest.main()
