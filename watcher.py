#!/usr/bin/env python3
import logging
import os
import socket
import threading
import time
import json
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
DEFERRED_ROOTS_KEY = "scanner:deferred_roots"
SETTINGS_KEY = "scanner:runtime_settings"
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


def runtime_settings():
    defaults = {"dirty_parent_levels": 1, "dirty_min_depth": 3}
    try:
        raw = r.get(SETTINGS_KEY)
        if raw:
            defaults.update(json.loads(raw))
    except Exception:
        logger.warning("Invalid runtime scan settings; using safe defaults")
    return defaults


def watch_root_for_path(path):
    path = os.path.normpath(path)
    matches = [root for root in WATCH_ROOTS if path == root or path.startswith(root + os.sep)]
    return max(matches, key=len) if matches else None


def scope_for_path(path, settings=None):
    settings = settings or runtime_settings()
    watch_root = watch_root_for_path(path)
    if not watch_root:
        return None, "outside_watch_roots"
    scope = os.path.dirname(os.path.normpath(path))
    for _ in range(max(0, int(settings["dirty_parent_levels"]))):
        if scope == watch_root:
            break
        scope = os.path.dirname(scope)
    relative = os.path.relpath(scope, watch_root)
    depth = 0 if relative == os.curdir else len(relative.split(os.sep))
    if depth < max(1, int(settings["dirty_min_depth"])):
        return scope, "too_broad"
    return scope, None


def mark_dirty(path):
    scope, reason = scope_for_path(path)
    if not scope:
        return
    marker = utc_now()
    if reason:
        r.hset(DEFERRED_ROOTS_KEY, scope, json.dumps({"marked_at": marker, "reason": reason}))
        return
    current = r.hgetall(DIRTY_ROOTS_KEY)
    for existing in current:
        if scope == existing or scope.startswith(existing + os.sep):
            r.hset(DIRTY_ROOTS_KEY, existing, marker)
            return
    for existing in current:
        if existing.startswith(scope + os.sep):
            r.hdel(DIRTY_ROOTS_KEY, existing)
    r.hset(DIRTY_ROOTS_KEY, scope, marker)


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
        r.hset(DEFERRED_ROOTS_KEY, path, json.dumps({
            "marked_at": utc_now(), "reason": "watcher_startup_recovery",
        }))
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
