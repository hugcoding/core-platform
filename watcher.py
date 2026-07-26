#!/usr/bin/env python3
import logging
import os
import socket
import time
from datetime import datetime, timezone

import redis
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("watcher")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
SCAN_ROOT = os.path.normpath(os.getenv("SCAN_ROOT", "/volume1"))
STREAM_KEY = os.getenv("STREAM_KEY", "scan_stream")
DEBOUNCE_SECONDS = max(1, int(os.getenv("WATCHER_DEBOUNCE_SECONDS", "2")))
HEARTBEAT_TTL = max(30, int(os.getenv("WATCHER_HEARTBEAT_TTL", "120")))

HEARTBEAT_KEY = "watcher:heartbeat"
HEARTBEAT_STATUS_KEY = "watcher:heartbeat:status"
LAST_EVENT_KEY = "watcher:last_event"
DIRTY_ROOTS_KEY = "scanner:dirty_roots"
DEBOUNCE_PREFIX = "watcher:dedupe:"

IGNORE_PREFIXES = ("@", ".", "#")
IGNORE_NAMES = {"tmp", "lost+found"}
IGNORE_CONTAINS = (
    "/@eaDir/",
    "/#recycle/",
    "/.Trash/",
    "/docker/postgres/",
    "/docker/redis/",
)

r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    socket_timeout=30,
    socket_connect_timeout=10,
    retry_on_timeout=True,
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def should_skip_path(path):
    path = os.path.normpath(path)
    parts = path.split(os.sep)
    for part in parts:
        if not part:
            continue
        if part in IGNORE_NAMES or part.startswith(IGNORE_PREFIXES):
            return True
    return any(value in path for value in IGNORE_CONTAINS)


def root_for_path(path):
    relative = os.path.relpath(os.path.normpath(path), SCAN_ROOT)
    if relative == os.curdir or relative.startswith(os.pardir + os.sep):
        return None
    return os.path.join(SCAN_ROOT, relative.split(os.sep, 1)[0])


def mark_dirty(path):
    root = root_for_path(path)
    if root:
        r.hset(DIRTY_ROOTS_KEY, root, utc_now())


def publish(event, path, old_path=None):
    path = os.path.normpath(path)
    if should_skip_path(path):
        return False

    dedupe_key = f"{DEBOUNCE_PREFIX}{event}:{path}"
    if not r.set(dedupe_key, "1", nx=True, ex=DEBOUNCE_SECONDS):
        return False

    payload = {
        "event": event,
        "path": path,
        "source": "filesystem_watcher",
        "ts": utc_now(),
        "scan_session_id": "",
    }
    if old_path:
        payload["old_path"] = os.path.normpath(old_path)

    r.xadd(STREAM_KEY, payload)
    mark_dirty(path)
    if old_path:
        mark_dirty(old_path)
    r.set(LAST_EVENT_KEY, payload["ts"])
    return True


class CoreEventHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            publish("UPSERT", event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            publish("UPSERT", event.src_path)

    def on_closed(self, event):
        if not event.is_directory:
            publish("UPSERT", event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            publish("DELETE", event.src_path)
        else:
            mark_dirty(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            publish("MOVE", event.dest_path, old_path=event.src_path)
        else:
            mark_dirty(event.src_path)
            mark_dirty(event.dest_path)


def heartbeat(status):
    timestamp = utc_now()
    r.set(HEARTBEAT_KEY, timestamp, ex=HEARTBEAT_TTL)
    r.set(HEARTBEAT_STATUS_KEY, status, ex=HEARTBEAT_TTL)


def main():
    if not os.path.isdir(SCAN_ROOT):
        raise RuntimeError(f"Watcher root does not exist: {SCAN_ROOT}")

    observer = Observer()
    observer.schedule(CoreEventHandler(), SCAN_ROOT, recursive=True)
    observer.start()
    logger.info(
        "Realtime watcher started host=%s root=%s debounce=%ss",
        socket.gethostname(),
        SCAN_ROOT,
        DEBOUNCE_SECONDS,
    )

    try:
        while observer.is_alive():
            heartbeat("watching")
            time.sleep(min(10, HEARTBEAT_TTL / 3))
    finally:
        heartbeat("stopped")
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
