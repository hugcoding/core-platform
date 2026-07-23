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
        _db_conn.autocommit = False
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


def path_is_missing(path):
    try:
        os.stat(path)
        return False
    except FileNotFoundError:
        return True
    except OSError:
        return False


def get_file_by_path(cur, path):
    cur.execute(
        "SELECT id, path, deleted_at FROM files WHERE path = %s",
        (path,),
    )
    return cur.fetchone()


def classify_path_mutation(existing_file):
    if not existing_file:
        return "CREATED"
    if existing_file["deleted_at"] is not None:
        return "RESTORED"
    return "MODIFIED"


def classify_rename_mutation(old_path, new_path):
    if os.path.dirname(old_path) == os.path.dirname(new_path):
        return "RENAMED"
    return "MOVED"


def identity_confidence(candidate, inode, size_bytes, modified_at_fs, content_hash):
    signals = {
        "inode_match": candidate.get("inode") == inode,
        "size_match": candidate.get("size_bytes") == size_bytes,
        "mtime_match": candidate.get("modified_at_fs") == modified_at_fs,
        "content_hash_match": bool(content_hash) and candidate.get("hash_content") == content_hash,
        "old_path_missing": path_is_missing(candidate["path"]),
    }
    weights = {
        "inode_match": 30,
        "size_match": 15,
        "mtime_match": 15,
        "content_hash_match": 30,
        "old_path_missing": 10,
    }
    score = sum(weights[name] for name, matched in signals.items() if matched)
    level = "high" if score >= 90 else "medium" if score >= 65 else "low"
    return score, level, signals


def insert_file_event(cur, *, file_id, event_type, source, old_path=None,
                      new_path=None, candidate_file_id=None, score=None,
                      level=None, decision=None, signals=None, reason=None,
                      scan_session_id=None):
    cur.execute("""
        INSERT INTO file_events (
            file_id, candidate_file_id, event_type, old_path, new_path,
            confidence_score, confidence_level, decision, signals, reason,
            scan_session_id, source
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
    """, (
        file_id, candidate_file_id, event_type, old_path, new_path,
        score, level, decision, json.dumps(signals or {}), reason,
        scan_session_id, source,
    ))


def evaluate_identity_match(cur, path, inode, size_bytes, modified_at_fs, content_hash):
    cur.execute("""
        SELECT id, path, inode, size_bytes, modified_at_fs, hash_content
        FROM files
        WHERE inode = %s
          AND path <> %s
          AND deleted_at IS NULL
        ORDER BY id
    """, (inode, path))

    rows = cur.fetchall()
    existing_paths = [row for row in rows if not path_is_missing(row["path"])]
    missing_candidates = [row for row in rows if row not in existing_paths]

    if existing_paths:
        return {
            "candidate": existing_paths[0],
            "event_type": "HARDLINK_DETECTED",
            "level": "ambiguous",
            "score": None,
            "signals": {"candidate_count": len(rows), "old_path_missing": False},
            "decision": "created_separate",
            "reason": "same inode is still active at another path",
        }

    if len(missing_candidates) != 1:
        return {
            "candidate": missing_candidates[0] if missing_candidates else None,
            "event_type": "IDENTITY_AMBIGUOUS" if missing_candidates else None,
            "level": "ambiguous" if missing_candidates else None,
            "score": None,
            "signals": {"candidate_count": len(missing_candidates)},
            "decision": "created_separate",
            "reason": "multiple missing candidates" if missing_candidates else "no candidate",
        }

    candidate = missing_candidates[0]
    score, level, signals = identity_confidence(
        candidate, inode, size_bytes, modified_at_fs, content_hash
    )
    signals["candidate_count"] = 1
    matched = level == "high"
    return {
        "candidate": candidate,
        "event_type": "IDENTITY_MATCHED" if matched else "IDENTITY_REJECTED",
        "level": level,
        "score": score,
        "signals": signals,
        "decision": "auto_linked" if matched else "created_separate",
        "reason": "unique high-confidence match" if matched else "confidence below automatic threshold",
    }


def find_rename_candidate(cur, path, inode, size_bytes, modified_at_fs, content_hash=None):
    result = evaluate_identity_match(
        cur, path, inode, size_bytes, modified_at_fs, content_hash
    )
    return result["candidate"] if result["decision"] == "auto_linked" else None


def process_event(cur, data):
    event = str(data.get("event", "")).lower()
    path = data.get("path")

    if not path:
        raise ValueError("Empty path")

    path = os.path.normpath(str(path))

    if "delete" in event:
        cur.execute("""
            UPDATE files SET
                deleted_at = NOW(),
                updated_at = NOW(),
                last_mutation_type = 'DELETED'
            WHERE path = %s
            RETURNING id
        """, (path,))
        row = cur.fetchone()
        if row:
            insert_file_event(
                cur, file_id=row["id"], event_type="DELETED",
                source=data.get("source", "polling_scanner"),
                old_path=path, scan_session_id=data.get("scan_session_id"),
            )
        logger.info("Deleted: %s", path)
        return

    if not os.path.exists(path):
        cur.execute("""
            UPDATE files SET
                deleted_at = NOW(),
                updated_at = NOW(),
                last_mutation_type = 'DELETED'
            WHERE path = %s
            RETURNING id
        """, (path,))
        row = cur.fetchone()
        if row:
            insert_file_event(
                cur, file_id=row["id"], event_type="DELETED",
                source=data.get("source", "polling_scanner"),
                old_path=path, reason="path_missing",
                scan_session_id=data.get("scan_session_id"),
            )
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

    values = (
        folder_id,
        filename,
        extension,
        size_bytes,
        modified_at_fs,
        inode,
        path,
        data.get("source", "polling_scanner"),
        hash_path,
        hash_content,
        mime,
    )

    existing_file = get_file_by_path(cur, path)
    rename_candidate = None
    identity_match = None
    if not existing_file:
        identity_match = evaluate_identity_match(
            cur, path, inode, size_bytes, modified_at_fs, hash_content
        )
        if identity_match["decision"] == "auto_linked":
            rename_candidate = identity_match["candidate"]

    if rename_candidate:
        mutation_type = classify_rename_mutation(rename_candidate["path"], path)
        cur.execute("""
            UPDATE files SET
                folder_id          = %s,
                filename           = %s,
                extension          = %s,
                size_bytes         = %s,
                modified_at_fs     = %s,
                inode              = %s,
                path               = %s,
                source             = %s,
                hash_path          = %s,
                hash_content       = %s,
                mime_type          = %s,
                last_mutation_type = %s,
                updated_at         = NOW(),
                deleted_at         = NULL
            WHERE id = %s
            RETURNING id
        """, values + (mutation_type, rename_candidate["id"]))
        logger.info(
            "%s: %s -> %s",
            mutation_type.title(),
            rename_candidate["path"],
            path,
        )
    else:
        mutation_type = classify_path_mutation(existing_file)
        cur.execute("""
            INSERT INTO files (
                folder_id, filename, extension, size_bytes,
                modified_at_fs, inode,
                path, source, hash_path, hash_content,
                mime_type, deleted_at,
                last_mutation_type
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s)
            ON CONFLICT (path) DO UPDATE SET
                folder_id          = EXCLUDED.folder_id,
                filename           = EXCLUDED.filename,
                extension          = EXCLUDED.extension,
                size_bytes         = EXCLUDED.size_bytes,
                modified_at_fs     = EXCLUDED.modified_at_fs,
                inode              = EXCLUDED.inode,
                source             = EXCLUDED.source,
                hash_path          = EXCLUDED.hash_path,
                hash_content       = EXCLUDED.hash_content,
                mime_type          = EXCLUDED.mime_type,
                last_mutation_type = EXCLUDED.last_mutation_type,
                updated_at         = NOW(),
                deleted_at         = NULL
            RETURNING id
        """, values + (mutation_type,))
    file_id = cur.fetchone()["id"]
    insert_file_event(
        cur,
        file_id=file_id,
        candidate_file_id=rename_candidate["id"] if rename_candidate else None,
        event_type=mutation_type,
        source=data.get("source", "polling_scanner"),
        old_path=rename_candidate["path"] if rename_candidate else None,
        new_path=path,
        decision="auto_linked" if rename_candidate else "state_updated",
        scan_session_id=data.get("scan_session_id"),
    )
    if identity_match and identity_match["event_type"]:
        insert_file_event(
            cur,
            file_id=file_id,
            candidate_file_id=(
                identity_match["candidate"]["id"]
                if identity_match["candidate"] else None
            ),
            event_type=identity_match["event_type"],
            source=data.get("source", "polling_scanner"),
            old_path=(
                identity_match["candidate"]["path"]
                if identity_match["candidate"] else None
            ),
            new_path=path,
            score=identity_match["score"],
            level=identity_match["level"],
            decision=identity_match["decision"],
            signals=identity_match["signals"],
            reason=identity_match["reason"],
            scan_session_id=data.get("scan_session_id"),
        )

    if FORCE_FULL:
        cur.execute("DELETE FROM metadata WHERE file_id = %s", (file_id,))

    width, height = get_image_dims(path, mime)

    cur.execute("""
        INSERT INTO metadata (
            file_id, width, height, duration, missing
        )
        VALUES (%s,%s,%s,NULL,false)
        ON CONFLICT (file_id) DO UPDATE SET
            width     = EXCLUDED.width,
            height    = EXCLUDED.height,
            missing   = false
    """, (file_id, width, height))

    r.set(LAST_EVENT_KEY, utc_now(), ex=HEARTBEAT_TTL * 4)
    logger.info("Processed: %s", path)


def mark_session_job_processed(cur, data):
    session_id = data.get("scan_session_id")
    if session_id:
        try:
            cur.execute("SELECT increment_jobs_processed(%s)", (session_id,))
        except Exception as exc:
            # Session accounting must never turn an otherwise valid legacy
            # metadata event into a DLQ entry.
            logger.warning("Scan session update failed: %s", exc)


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
                        mark_session_job_processed(cur, data)
                        conn.commit()
                    except Exception as e:
                        conn.rollback()
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
