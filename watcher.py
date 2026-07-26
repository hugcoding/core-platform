#!/usr/bin/env python3
import logging
import os
import socket
import threading
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
WATCH_ROOTS = tuple(
    os.path.normpath(path.strip())
    for path in os.getenv("WATCH_ROOTS", "/volume1/data").split(",")
    if path.strip()
)
STREAM_KEY = os.getenv("STREAM_KEY", "scan_stream_realtime")
DEBOUNCE_SECONDS = max(1, int(os.getenv("WATCHER_DEBOUNCE_SECONDS", "2")))
HEARTBEAT_TTL = max(30, int(os.getenv("WATCHER_HEARTBEAT_TTL", "120")))

HEARTBEAT_KEY = "watcher:heartbeat"
HEARTBEAT_STATUS_KEY = "watcher:heartbeat:status"
LAST_EVENT_KEY = "watcher:last_event"
RECOVERY_ROOTS_KEY = "watcher:recovery_roots"
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


def schedule_startup_recovery():
    roots = []
    for path in WATCH_ROOTS:
        if (
            os.path.commonpath((SCAN_ROOT, path)) != SCAN_ROOT
            or not os.path.isdir(path)
            or should_skip_path(path)
        ):
            continue
        roots.append(path)
        r.hset(DIRTY_ROOTS_KEY, path, utc_now())
    r.set(RECOVERY_ROOTS_KEY, len(roots))
    return roots


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

    recovery_roots = schedule_startup_recovery()
    if not recovery_roots:
        raise RuntimeError(f"No valid watcher roots found within {SCAN_ROOT}: {WATCH_ROOTS}")

    heartbeat("recovering")
    observer = Observer()
    handler = CoreEventHandler()
    for root in recovery_roots:
        observer.schedule(handler, root, recursive=True)

    startup_done = threading.Event()

    def startup_heartbeat():
        while not startup_done.wait(10):
            heartbeat("recovering")

    heartbeat_thread = threading.Thread(target=startup_heartbeat, daemon=True)
    heartbeat_thread.start()
    try:
        observer.start()
    finally:
        startup_done.set()
        heartbeat_thread.join(timeout=1)

    logger.info(
        "Realtime watcher started host=%s roots=%s debounce=%ss",
        socket.gethostname(),
        ", ".join(recovery_roots),
        DEBOUNCE_SECONDS,
    )
    logger.info("Startup recovery scheduled for %s roots", len(recovery_roots))

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
