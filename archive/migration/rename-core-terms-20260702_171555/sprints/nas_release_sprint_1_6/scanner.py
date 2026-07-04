#!/usr/bin/env python3
import os
import time
import socket
import logging
from datetime import datetime, timezone

import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("scanner")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

SCAN_ROOT = os.getenv("SCAN_ROOT", "/volume1")
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "30"))

STREAM_KEY = os.getenv("STREAM_KEY", "scan_stream")
LOCK_KEY = "scanner:lock:event"
LOCK_TTL = 90

HEARTBEAT_KEY = "scanner:heartbeat"
HEARTBEAT_STATUS_KEY = "scanner:heartbeat:status"
LAST_SCAN_KEY = "scanner:last_scan"
HEARTBEAT_TTL = 120

CONSUMER_NAME = socket.gethostname()

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
    parts = path.split(os.sep)
    for part in parts:
        if not part:
            continue
        if part in IGNORE_NAMES:
            return True
        if part.startswith(IGNORE_PREFIXES):
            return True
    return any(x in path for x in IGNORE_CONTAINS)


def heartbeat(status="running"):
    try:
        r.set(HEARTBEAT_KEY, utc_now(), ex=HEARTBEAT_TTL)
        r.set(HEARTBEAT_STATUS_KEY, status, ex=HEARTBEAT_TTL)
    except Exception as e:
        logger.warning("Heartbeat failed: %s", e)


def acquire_lock():
    owner = r.get(LOCK_KEY)
    if owner and owner != CONSUMER_NAME:
        owner_hb = r.get(HEARTBEAT_KEY)
        if owner_hb:
            logger.warning("Scanner already running: owner=%s heartbeat=%s", owner, owner_hb)
            return False
        logger.warning("Stale scanner lock found: owner=%s, taking over", owner)
        r.delete(LOCK_KEY)

    ok = r.set(LOCK_KEY, CONSUMER_NAME, nx=True, ex=LOCK_TTL)
    if not ok:
        logger.warning("Scanner lock busy: %s", r.get(LOCK_KEY))
        return False

    logger.info("Scanner lock acquired by %s", CONSUMER_NAME)
    return True


def refresh_lock():
    try:
        if r.get(LOCK_KEY) == CONSUMER_NAME:
            r.expire(LOCK_KEY, LOCK_TTL)
    except Exception as e:
        logger.warning("Lock refresh failed: %s", e)


def release_lock():
    try:
        if r.get(LOCK_KEY) == CONSUMER_NAME:
            r.delete(LOCK_KEY)
    except Exception:
        pass


def discover_roots():
    if not os.path.isdir(SCAN_ROOT):
        logger.error("SCAN_ROOT does not exist: %s", SCAN_ROOT)
        return []

    roots = []
    for name in os.listdir(SCAN_ROOT):
        path = os.path.join(SCAN_ROOT, name)
        if not os.path.isdir(path):
            continue
        if name in IGNORE_NAMES or name.startswith(IGNORE_PREFIXES):
            continue
        if should_skip_path(path):
            continue
        roots.append(path)

    roots.sort()
    return roots


def file_signature(path, st):
    return f"{int(st.st_mtime)}:{st.st_size}:{st.st_ino}"


def changed(path, signature):
    key = "scanner:sig:" + path
    old = r.get(key)
    if old == signature:
        return False
    r.set(key, signature)
    return True


def scan_once():
    roots = discover_roots()
    logger.info("Discovered scan roots: %s", ", ".join(roots))

    discovered = 0
    enqueued = 0

    for root_base in roots:
        heartbeat("scanning")
        refresh_lock()

        for root, dirs, files in os.walk(root_base):
            dirs[:] = [
                d for d in dirs
                if d not in IGNORE_NAMES
                and not d.startswith(IGNORE_PREFIXES)
                and not should_skip_path(os.path.join(root, d))
            ]

            for filename in files:
                path = os.path.join(root, filename)

                if should_skip_path(path):
                    continue

                try:
                    st = os.stat(path)
                except FileNotFoundError:
                    continue
                except PermissionError:
                    logger.warning("Permission denied: %s", path)
                    continue
                except Exception as e:
                    logger.warning("stat failed: %s err=%s", path, e)
                    continue

                discovered += 1
                sig = file_signature(path, st)

                if not changed(path, sig):
                    continue

                r.xadd(STREAM_KEY, {
                    "event": "UPSERT",
                    "path": path,
                    "source": "polling_scanner",
                    "mtime": str(int(st.st_mtime)),
                    "size": str(st.st_size),
                    "inode": str(st.st_ino),
                    "ts": utc_now(),
                })
                enqueued += 1

    r.set(LAST_SCAN_KEY, utc_now(), ex=HEARTBEAT_TTL * 4)
    return discovered, enqueued


def main():
    if not acquire_lock():
        return

    heartbeat("started")
    logger.info("Starting polling scanner on %s interval=%ss", SCAN_ROOT, SCAN_INTERVAL)

    try:
        while True:
            refresh_lock()
            heartbeat("running")

            started = time.time()
            try:
                discovered, enqueued = scan_once()
                elapsed = time.time() - started
                heartbeat("idle")
                logger.info("Scan done: discovered=%s enqueued=%s elapsed=%.1fs", discovered, enqueued, elapsed)
            except Exception as e:
                heartbeat("error")
                logger.exception("Scan loop failed: %s", e)

            time.sleep(SCAN_INTERVAL)

    finally:
        heartbeat("stopped")
        release_lock()


if __name__ == "__main__":
    main()
