"""SCRUM-116 controlled, append-only filesystem execution worker."""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
import redis

from core.cleanup.duplicate_executor import move_verified as move_exact_duplicate
from core.cleanup.duplicate_executor import resume_verified_move as resume_exact_duplicate
from core.cleanup.duplicate_executor import rollback_verified as rollback_exact_duplicate
from core.migration.personal_executor import (
    MigrationSafetyError, inspect_preconditions, move_verified, resume_verified_move,
    rollback_verified,
)

POLL_SECONDS = int(os.getenv("CORE_EXECUTION_POLL_SECONDS", "5"))
MIN_AVAILABLE_MIB = int(os.getenv("CORE_EXECUTION_MIN_AVAILABLE_MIB", "1024"))
MAX_LOAD_PER_CPU = float(os.getenv("CORE_EXECUTION_MAX_LOAD_PER_CPU", "1.5"))
MAX_STREAM_LAG = int(os.getenv("CORE_EXECUTION_MAX_STREAM_LAG", "1000"))
ACTOR = os.getenv("CORE_EXECUTION_ACTOR", "controlled-execution-worker")

QUARANTINE_ZONES = {
    "quarantine_content_similar": (Path("/volume1/data/.core/quarantaine/duplicaten/inhoudelijk"),),
    "quarantine_deletion_review": (Path("/volume1/data/.core/quarantaine/verwijderreview"),),
}


def db_connect():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"), port=os.getenv("DB_PORT", "5432"),
        user=os.environ["DB_USER"], password=os.environ["DB_PASS"], dbname=os.environ["DB_NAME"],
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def redis_connect():
    return redis.Redis(host=os.getenv("REDIS_HOST", "redis"), decode_responses=True,
                       socket_connect_timeout=2, socket_timeout=2)


def host_resources(proc_root: Path = Path("/host/proc")) -> dict[str, float]:
    load = float((proc_root / "loadavg").read_text().split()[0])
    cpus = max(1, sum(line.startswith("processor") for line in (proc_root / "cpuinfo").read_text().splitlines()))
    memory = {}
    for line in (proc_root / "meminfo").read_text().splitlines():
        key, value = line.split(":", 1); memory[key] = int(value.strip().split()[0])
    available = memory.get("MemAvailable", memory.get("MemFree", 0) + memory.get("Cached", 0))
    return {"load_per_cpu": round(load / cpus, 3), "available_memory_mib": round(available / 1024, 1)}


def stream_lag(client: redis.Redis) -> int:
    total = 0
    for stream in ("scan_stream", "scan_stream_realtime"):
        try: total += sum(int(group.get("lag") or 0) for group in client.xinfo_groups(stream))
        except redis.ResponseError: pass
    return total


def resource_block(resources: dict[str, float], lag: int) -> str | None:
    if resources["available_memory_mib"] < MIN_AVAILABLE_MIB: return "waiting_for_memory"
    if resources["load_per_cpu"] > MAX_LOAD_PER_CPU: return "waiting_for_cpu"
    if lag > MAX_STREAM_LAG: return "core_pipeline_priority"
    return None


def append_event(conn, batch_id: str, item_id: str | None, event_type: str,
                 key: str, details: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO public.controlled_execution_events
          (batch_id,item_id,event_type,idempotency_key,actor,details)
          VALUES (%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT (idempotency_key) DO NOTHING""",
          (batch_id, item_id, event_type, key, ACTOR, json.dumps(details, default=str)))
    conn.commit()


def latest_batch_status(conn, batch_id: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT batch_status FROM public.v_controlled_execution_batch_progress WHERE id=%s", (batch_id,))
        row = cur.fetchone(); return str(row["batch_status"]) if row and row["batch_status"] else None


def claim_batch(conn) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute("""SELECT progress.* FROM public.v_controlled_execution_batch_progress progress
          WHERE progress.batch_status IN ('approved','queued','started','rollback_pending')
          ORDER BY progress.id LIMIT 1""")
        batch = cur.fetchone()
        if not batch: return None
        cur.execute("SELECT pg_try_advisory_lock(hashtext(%s)) AS locked", (str(batch["id"]),))
        locked = cur.fetchone()["locked"]
        return dict(batch) if locked else None


def batch_items(conn, batch_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("""SELECT * FROM public.v_controlled_execution_item_status
          WHERE batch_id=%s ORDER BY sequence_no""", (batch_id,))
        return [dict(row) for row in cur.fetchall()]


def item_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload = dict(item)
    payload.update(dict(item.get("latest_details") or {}))
    payload.update(dict(item.get("evidence_snapshot") or {}))
    return payload


def zones(item: dict[str, Any]):
    return QUARANTINE_ZONES.get(str(item["action_type"]))


def start_details(item: dict[str, Any]) -> dict[str, Any]:
    payload = item_payload(item)
    if item["action_type"] == "quarantine_exact_duplicate":
        from core.cleanup.duplicate_executor import inspect_preconditions as inspect_exact
        checked = inspect_exact(payload)
    else:
        checked = inspect_preconditions(payload, allowed_zones=zones(item))
    return {"source_path": str(checked.source), "target_path": str(checked.target),
            "size_bytes": checked.size_bytes, "mtime_ns": checked.mtime_ns,
            "content_sha256": checked.content_sha256}


def execute_item(item: dict[str, Any]) -> dict[str, Any]:
    payload = item_payload(item)
    if item["action_type"] == "quarantine_exact_duplicate":
        return (resume_exact_duplicate(payload) if item["current_status"] == "started" and Path(str(item["target_path"])).exists()
                else move_exact_duplicate(payload))
    return (resume_verified_move(payload, allowed_zones=zones(item))
            if item["current_status"] == "started" and Path(str(item["target_path"])).exists()
            else move_verified(payload, allowed_zones=zones(item)))


def rollback_item(item: dict[str, Any]) -> dict[str, Any]:
    payload = item_payload(item)
    if item["action_type"] == "quarantine_exact_duplicate": return rollback_exact_duplicate(payload)
    return rollback_verified(payload, allowed_zones=zones(item))


def process_forward(conn, batch: dict[str, Any], client: redis.Redis | None = None) -> None:
    batch_id = str(batch["id"])
    append_event(conn, batch_id, None, "started", f"{batch_id}:worker-started:{uuid.uuid4()}", {"worker": ACTOR})
    for item in batch_items(conn, batch_id):
        if latest_batch_status(conn, batch_id) == "paused": return
        if client is not None:
            resources, lag = host_resources(), stream_lag(client)
            waiting = resource_block(resources, lag)
            if waiting:
                append_event(conn, batch_id, None, "queued", f"{batch_id}:resource-wait:{uuid.uuid4()}",
                             {"waiting_reason": waiting, **resources, "stream_lag": lag})
                return
        if item["current_status"] in ("verified", "completed", "event_correlated", "blocked", "failed", "rolled_back"):
            continue
        if item["current_status"] not in ("queued", "started"):
            append_event(conn, batch_id, None, "paused", f"{batch_id}:invalid-state:{uuid.uuid4()}",
                         {"reason": "item_not_queued", "item_id": str(item["id"])})
            return
        item_id = str(item["id"])
        if item["current_status"] == "queued":
            try:
                details = start_details(item)
                append_event(conn, batch_id, item_id, "started", f"{item_id}:started", details)
                item = {**item, "current_status": "started", "latest_details": details}
            except (MigrationSafetyError, OSError, ValueError, KeyError) as exc:
                append_event(conn, batch_id, item_id, "blocked", f"{item_id}:blocked",
                             {"reason": str(exc), "exception": type(exc).__name__, "file_mutations": False})
                continue
        try:
            result = execute_item(item)
            append_event(conn, batch_id, item_id, "verified", f"{item_id}:verified", result)
        except (MigrationSafetyError, OSError, ValueError, KeyError) as exc:
            interrupted = {**dict(item.get("latest_details") or {}), "reason": str(exc),
                           "exception": type(exc).__name__, "recovery_required": True}
            append_event(conn, batch_id, item_id, "started",
                         f"{item_id}:interrupted:{uuid.uuid4()}", interrupted)
            append_event(conn, batch_id, None, "paused",
                         f"{batch_id}:worker-paused:{uuid.uuid4()}",
                         {"reason": "interrupted_move_requires_resume", "item_id": item_id})
            return
    final_items = batch_items(conn, batch_id)
    terminal = {"verified", "completed", "event_correlated", "blocked", "failed", "rolled_back"}
    if (len(final_items) != int(batch.get("item_count", len(final_items))) or not final_items
            or any(item["current_status"] not in terminal for item in final_items)):
        append_event(conn, batch_id, None, "paused", f"{batch_id}:incomplete:{uuid.uuid4()}",
                     {"reason": "unfinished_items_require_review"})
        return
    append_event(conn, batch_id, None, "completed", f"{batch_id}:completed", {"worker": ACTOR})


def process_rollback(conn, batch: dict[str, Any]) -> None:
    batch_id = str(batch["id"])
    for item in reversed(batch_items(conn, batch_id)):
        if item["current_status"] != "verified": continue
        item_id = str(item["id"])
        try:
            result = rollback_item(item)
            append_event(conn, batch_id, item_id, "rolled_back", f"{item_id}:rolled-back", result)
        except (MigrationSafetyError, OSError, ValueError, KeyError) as exc:
            append_event(conn, batch_id, item_id, "failed", f"{item_id}:rollback-failed",
                         {"reason": str(exc), "exception": type(exc).__name__})
    append_event(conn, batch_id, None, "rolled_back", f"{batch_id}:rolled-back", {"worker": ACTOR})


def run_once(client: redis.Redis | None = None) -> bool:
    conn = db_connect()
    try:
        batch = claim_batch(conn)
        if not batch: return False
        if batch["batch_status"] == "rollback_pending": process_rollback(conn, batch)
        else: process_forward(conn, batch, client)
        return True
    finally:
        conn.close()


def main() -> None:
    client = redis_connect()
    while True:
        try:
            resources = host_resources(); lag = stream_lag(client); waiting = resource_block(resources, lag)
            client.hset("controlled_execution_worker:heartbeat", mapping={
                "status": waiting or "active", "updated_at": int(time.time()), **resources, "stream_lag": lag,
            })
            if not waiting: run_once(client)
        except Exception as exc:
            client.hset("controlled_execution_worker:heartbeat", mapping={
                "status": "error", "error": type(exc).__name__, "updated_at": int(time.time()),
            })
        time.sleep(POLL_SECONDS)


if __name__ == "__main__": main()
