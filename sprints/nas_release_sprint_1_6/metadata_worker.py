#!/usr/bin/env python3
import os
import json
import socket
import logging
from datetime import datetime, timezone

import redis
import psycopg2
import psycopg2.extras
import magic
import pyvips
import xxhash

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("metadata-worker")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

STREAM_KEY = "scan_stream"
GROUP_NAME = "metadata_group"
DLQ_STREAM = "scan_stream_dlq"

LOCK_KEY = "metadata_worker:lock"
LOCK_TTL = 90

HEARTBEAT_KEY = "metadata_worker:heartbeat"
HEARTBEAT_STATUS_KEY = "metadata_worker:heartbeat:status"
LAST_EVENT_KEY = "metadata_worker:last_event"
HEARTBEAT_TTL = 120

CONSUMER_NAME = socket.gethostname()
FORCE_FULL = os.getenv("FORCE_FULL_METADATA", "false").lower() == "true"

r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    socket_timeout=30,
    socket_connect_timeout=10,
    retry_on_timeout=True,
)

_db_conn = None


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def heartbeat(status="running"):
    try:
        r.set(HEARTBEAT_KEY, utc_now(), ex=HEARTBEAT_TTL)
        r.set(HEARTBEAT_STATUS_KEY, status, ex=HEARTBEAT_TTL)
    except Exception as e:
        logger.warning("Heartbeat failed: %s", e)


def get_db():
    global _db_conn
    if _db_conn is None or _db_conn.closed:
        _db_conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            dbname=os.getenv("DB_NAME"),
        )
        _db_conn.autocommit = True
        logger.info("Database connected")
    return _db_conn


def acquire_lock():
    owner = r.get(LOCK_KEY)
    if owner and owner != CONSUMER_NAME:
        owner_hb = r.get(HEARTBEAT_KEY)
        if owner_hb:
            logger.warning("Metadata worker already running: owner=%s heartbeat=%s", owner, owner_hb)
            return False
        logger.warning("Stale metadata worker lock found: owner=%s, taking over", owner)
        r.delete(LOCK_KEY)

    ok = r.set(LOCK_KEY, CONSUMER_NAME, nx=True, ex=LOCK_TTL)
    if not ok:
        logger.warning("Metadata worker lock busy: %s", r.get(LOCK_KEY))
        return False

    logger.info("Metadata worker lock acquired by %s", CONSUMER_NAME)
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


def ensure_group():
    try:
        r.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
        logger.info("Redis consumer group created")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def upsert_folder(cur, path):
    path = os.path.normpath(path)
    if not path or path == "/":
        return None

    cur.execute("SELECT id FROM folders WHERE path = %s", (path,))
    row = cur.fetchone()
    if row:
        return row["id"]

    parent = os.path.dirname(path)
    parent_id = None if parent == path else upsert_folder(cur, parent)

    cur.execute("""
        INSERT INTO folders (path, parent_id)
        VALUES (%s, %s)
        ON CONFLICT (path) DO UPDATE SET
            path = EXCLUDED.path
        RETURNING id
    """, (path, parent_id))

    return cur.fetchone()["id"]


def hash_first_1024(path):
    try:
        with open(path, "rb") as f:
            return xxhash.xxh64(f.read(1024)).hexdigest()
    except Exception:
        return None


def get_mime(path):
    try:
        return magic.from_file(path, mime=True)
    except Exception as e:
        logger.warning("MIME failed: %s err=%s", path, e)
        return None


def get_image_dims(path, mime):
    if not mime or not mime.startswith("image/"):
        return None, None

    try:
        img = pyvips.Image.new_from_file(path)
        return img.width, img.height
    except Exception as e:
        logger.warning("Image metadata failed: %s err=%s", path, e)
        return None, None


def process_event(cur, data):
    event = str(data.get("event", "")).lower()
    path = data.get("path")

    if not path:
        raise ValueError("Empty path")

    path = os.path.normpath(str(path))

    if "delete" in event:
        cur.execute("UPDATE files SET deleted_at = NOW() WHERE path = %s", (path,))
        logger.info("Deleted: %s", path)
        return

    if not os.path.exists(path):
        cur.execute("UPDATE files SET deleted_at = NOW() WHERE path = %s", (path,))
        logger.warning("Missing file, marked deleted: %s", path)
        return

    folder_path = os.path.dirname(path)
    folder_id = upsert_folder(cur, folder_path)

    if not folder_id:
        raise RuntimeError(f"No folder_id for {folder_path}")

    filename = os.path.basename(path)
    extension = os.path.splitext(filename)[1].lstrip(".").lower() or None

    stat = os.stat(path)
    size_bytes = stat.st_size
    modified_at_fs = int(stat.st_mtime)
    inode = stat.st_ino

    hash_path = xxhash.xxh64(path).hexdigest()
    hash_content = hash_first_1024(path)
    mime = get_mime(path)

    cur.execute("""
        INSERT INTO files (
            folder_id, filename, extension, size_bytes,
            modified_at_fs, inode, xxhash,
            path, source, hash_path, hash_content,
            mime_type, deleted_at
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL)
        ON CONFLICT (path) DO UPDATE SET
            folder_id       = EXCLUDED.folder_id,
            filename        = EXCLUDED.filename,
            extension       = EXCLUDED.extension,
            size_bytes      = EXCLUDED.size_bytes,
            modified_at_fs  = EXCLUDED.modified_at_fs,
            inode           = EXCLUDED.inode,
            xxhash          = EXCLUDED.xxhash,
            source          = EXCLUDED.source,
            hash_path       = EXCLUDED.hash_path,
            hash_content    = EXCLUDED.hash_content,
            mime_type       = EXCLUDED.mime_type,
            updated_at      = NOW(),
            deleted_at      = NULL
        RETURNING id
    """, (
        folder_id,
        filename,
        extension,
        size_bytes,
        modified_at_fs,
        inode,
        hash_path,
        path,
        data.get("source", "polling_scanner"),
        hash_path,
        hash_content,
        mime,
    ))

    file_id = cur.fetchone()["id"]

    if FORCE_FULL:
        cur.execute("DELETE FROM metadata WHERE file_id = %s", (file_id,))

    cur.execute("SELECT 1 FROM metadata WHERE file_id = %s", (file_id,))
    exists = cur.fetchone()

    if not exists:
        width, height = get_image_dims(path, mime)

        cur.execute("""
            INSERT INTO metadata (
                file_id, mime_type, width, height, duration, missing
            )
            VALUES (%s,%s,%s,%s,NULL,false)
            ON CONFLICT (file_id) DO UPDATE SET
                mime_type = EXCLUDED.mime_type,
                width     = EXCLUDED.width,
                height    = EXCLUDED.height,
                missing   = false
        """, (file_id, mime, width, height))

    r.set(LAST_EVENT_KEY, utc_now(), ex=HEARTBEAT_TTL * 4)
    logger.info("Processed: %s", path)


def main():
    if not acquire_lock():
        return

    heartbeat("started")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    ensure_group()
    logger.info("Worker started")

    try:
        while True:
            refresh_lock()
            heartbeat("waiting")

            try:
                resp = r.xreadgroup(
                    GROUP_NAME,
                    CONSUMER_NAME,
                    streams={STREAM_KEY: ">"},
                    count=50,
                    block=5000,
                )
            except redis.exceptions.ResponseError as e:
                if "NOGROUP" in str(e):
                    logger.warning("NOGROUP detected, recreating group")
                    ensure_group()
                    continue
                raise

            if not resp:
                continue

            heartbeat("processing")

            for _, msgs in resp:
                for msg_id, data in msgs:
                    try:
                        process_event(cur, data)
                    except Exception as e:
                        logger.error("DLQ msg=%s: %s", msg_id, e, exc_info=True)
                        r.xadd(DLQ_STREAM, {
                            "original_id": msg_id,
                            "data": json.dumps(data),
                            "error": str(e),
                            "ts": utc_now(),
                        })
                    finally:
                        r.xack(STREAM_KEY, GROUP_NAME, msg_id)

    finally:
        heartbeat("stopped")
        release_lock()


if __name__ == "__main__":
    main()
