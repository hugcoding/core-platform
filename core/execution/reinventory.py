"""Targeted, idempotent reinventory requests for changed execution sources."""
from __future__ import annotations

import hashlib
import os
import stat
import time
from pathlib import Path
from typing import Any, Mapping

REINVENTORY_STREAM = os.getenv("CORE_REINVENTORY_STREAM", "scan_stream")
REINVENTORY_DEDUP_TTL = int(os.getenv("CORE_REINVENTORY_DEDUP_TTL", "604800"))


def enqueue_source_reinventory(client: Any, item: Mapping[str, Any]) -> dict[str, Any]:
    """Atomically enqueue one low-priority metadata refresh for a changed source."""
    if client is None:
        return {"reinventory_status": "unavailable", "reason": "redis_client_unavailable"}
    source_path = str(item["source_path"])
    if not source_path.startswith("/volume1/data/"):
        raise ValueError("reinventory path outside /volume1/data")
    source_stat = Path(source_path).lstat()
    if not stat.S_ISREG(source_stat.st_mode):
        raise ValueError("reinventory source is not a regular file")
    signature = f"{source_stat.st_size}:{source_stat.st_mtime_ns}:{source_stat.st_ino}"
    repair_key = hashlib.sha256(
        f"{item['file_id']}\n{source_path}\n{signature}".encode("utf-8")
    ).hexdigest()
    dedup_key = f"controlled_execution:reinventory:{repair_key}"
    script = """
    if redis.call('SET', KEYS[1], ARGV[1], 'NX', 'EX', ARGV[2]) then
      return redis.call('XADD', KEYS[2], '*',
        'event', 'UPSERT', 'path', ARGV[3], 'source', ARGV[4],
        'file_id', ARGV[5], 'batch_id', ARGV[6], 'item_id', ARGV[7],
        'reinventory_key', ARGV[8])
    end
    return ''
    """
    stream_id = client.eval(
        script, 2, dedup_key, REINVENTORY_STREAM, str(int(time.time())),
        str(REINVENTORY_DEDUP_TTL), source_path, "controlled_execution_reinventory",
        str(item["file_id"]), str(item["batch_id"]), str(item["id"]), repair_key,
    )
    return {
        "reinventory_status": "queued" if stream_id else "already_queued",
        "reinventory_key": repair_key,
        "reinventory_stream": REINVENTORY_STREAM,
        "observed_size_bytes": source_stat.st_size,
        "observed_mtime_ns": source_stat.st_mtime_ns,
        "file_mutations": False,
    }
