from __future__ import annotations

import csv
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
import redis
from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles


APP_DIR = Path(__file__).parent
EXPORT_DIR = Path(os.getenv("EXPORT_DIR", "/exports/migration-inventory"))
HOST_PROC = Path(os.getenv("HOST_PROC", "/host/proc"))
STORAGE_PATH = Path(os.getenv("STORAGE_PATH", "/volume1"))
STARTED = time.monotonic()

app = FastAPI(title="CORE Pulse", version="0.1.0", docs_url=None, redoc_url=None)
app.mount("/coredashboard/assets", StaticFiles(directory=APP_DIR / "static"), name="assets")


def db_connect():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT", "5432"),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASS"),
        dbname=os.getenv("DB_NAME"), connect_timeout=3,
    )


def redis_connect():
    return redis.Redis(host=os.getenv("REDIS_HOST", "redis"), decode_responses=True,
                       socket_connect_timeout=2, socket_timeout=2)


def query_one(conn, sql: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(sql)
        columns = [item.name for item in cur.description]
        return dict(zip(columns, cur.fetchone()))


def iso(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value


def heartbeat_service(client, name: str, *, intentionally_paused: bool = False) -> dict[str, Any]:
    heartbeat = client.get(f"{name}:heartbeat")
    status = client.get(f"{name}:heartbeat:status")
    if intentionally_paused and not heartbeat:
        return {"name": name, "state": "paused", "detail": "Paused by policy"}
    state = "healthy" if heartbeat else "attention"
    return {"name": name, "state": state, "detail": status or ("heartbeat active" if heartbeat else "heartbeat missing"), "heartbeat": heartbeat}


def latest_classifier_progress() -> dict[str, Any]:
    manifests = sorted(EXPORT_DIR.glob("classification-inventory-*.csv"))
    checkpoints = sorted(EXPORT_DIR.glob(".classification-extract-*.csv"), key=lambda p: p.stat().st_mtime)
    total = 0
    processed = 0
    if manifests:
        with manifests[-1].open(encoding="utf-8-sig", newline="") as handle:
            total = sum(1 for _ in csv.DictReader(handle, delimiter=";"))
    if checkpoints:
        with checkpoints[-1].open(encoding="utf-8-sig", newline="") as handle:
            processed = sum(1 for _ in csv.DictReader(handle, delimiter=";"))
    return {
        "active": bool(checkpoints and processed < total), "processed": processed,
        "total": total, "percent": round(processed * 100 / total, 1) if total else 0,
        "updated_at": datetime.fromtimestamp(checkpoints[-1].stat().st_mtime, timezone.utc).isoformat() if checkpoints else None,
    }


def host_metrics() -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        lines = (HOST_PROC / "meminfo").read_text().splitlines()
        values = {line.split(":", 1)[0]: int(line.split()[1]) * 1024 for line in lines}
        result["memory_total"] = values["MemTotal"]
        result["memory_used"] = values["MemTotal"] - values.get("MemAvailable", values.get("MemFree", 0))
    except (OSError, KeyError, ValueError):
        pass
    try:
        usage = shutil.disk_usage(STORAGE_PATH)
        result.update(storage_total=usage.total, storage_used=usage.used, storage_free=usage.free)
    except OSError:
        pass
    try:
        result["load_1m"] = float((HOST_PROC / "loadavg").read_text().split()[0])
    except (OSError, ValueError):
        pass
    return result


@app.get("/")
def root():
    return RedirectResponse("/coredashboard", status_code=307)


@app.get("/coredashboard")
def dashboard():
    return FileResponse(APP_DIR / "static" / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "core-pulse", "uptime_seconds": round(time.monotonic() - STARTED)}


@app.get("/api/v1/overview")
def overview():
    errors: list[str] = []
    services = []
    metrics: dict[str, Any] = {}
    latest_scan: dict[str, Any] = {}
    recent_scans: list[dict[str, Any]] = []
    try:
        with db_connect() as conn:
            metrics = query_one(conn, """
                SELECT
                  COUNT(*) FILTER (WHERE deleted_at IS NULL) AS active_files,
                  COUNT(*) FILTER (WHERE deleted_at IS NOT NULL) AS deleted_files,
                  COUNT(*) FILTER (WHERE deleted_at IS NULL AND COALESCE(size_bytes, 0) = 0) AS empty_files,
                  COUNT(*) FILTER (WHERE deleted_at IS NULL AND updated_at >= now() - interval '24 hours') AS changed_24h,
                  (SELECT COUNT(*) FROM content_groups) AS content_groups,
                  (SELECT COUNT(*) FROM content_groups WHERE selection_status <> 'single_source') AS duplicate_groups,
                  (SELECT COUNT(*) FROM file_events WHERE event_status = 'active') AS active_events
                FROM files
            """)
            with conn.cursor() as cur:
                cur.execute("""SELECT id, type, status, started_at, finished_at, files_discovered,
                                      jobs_enqueued, jobs_processed
                               FROM scan_sessions ORDER BY started_at DESC LIMIT 8""")
                columns = [item.name for item in cur.description]
                recent_scans = [{key: iso(value) for key, value in zip(columns, row)} for row in cur.fetchall()]
                latest_scan = recent_scans[0] if recent_scans else {}
        services.append({"name": "postgres", "state": "healthy", "detail": "database connected"})
    except Exception as exc:
        errors.append(f"database: {type(exc).__name__}")
        services.append({"name": "postgres", "state": "degraded", "detail": "database unavailable"})
    try:
        client = redis_connect()
        client.ping()
        services.append({"name": "redis", "state": "healthy", "detail": "queue connected"})
        services.extend([
            heartbeat_service(client, "scanner"),
            heartbeat_service(client, "metadata_worker"),
            heartbeat_service(client, "watcher", intentionally_paused=True),
        ])
        metrics.update(
            polling_queue=client.xlen("scan_stream"),
            realtime_queue=client.xlen("scan_stream_realtime"),
            dlq=client.xlen("scan_stream_dlq"),
            dirty_roots=client.hlen("scanner:dirty_roots"),
        )
    except Exception as exc:
        errors.append(f"redis: {type(exc).__name__}")
        services.append({"name": "redis", "state": "degraded", "detail": "queue unavailable"})
    states = {service["state"] for service in services}
    overall = "degraded" if "degraded" in states else "attention" if "attention" in states else "healthy"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(), "overall": overall,
        "services": services, "metrics": {key: iso(value) for key, value in metrics.items()},
        "latest_scan": latest_scan, "recent_scans": recent_scans,
        "classifier": latest_classifier_progress(), "host": host_metrics(), "errors": errors,
    }
