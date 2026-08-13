from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
import redis
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from core.organization.target_path import CONTRACT_VERSION, propose_target
from core.organization.review_taxonomy import contextual_options, taxonomy
from core.organization.path_normalization import normalize_target_path, suggest_known_target_path
from core.organization.privacy_classification import RULE_VERSION as PRIVACY_RULE_VERSION, propose_privacy


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


def query_one(conn, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        columns = [item.name for item in cur.description]
        return dict(zip(columns, cur.fetchone()))


def query_all(conn, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        columns = [item.name for item in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


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


@app.get("/coreworkset")
def workset_page():
    return FileResponse(APP_DIR / "static" / "workset.html")


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


def smb_path(path: str) -> str:
    prefix = "/volume1/data"
    if path == prefix:
        return r"\\192.168.68.105\data"
    if path.startswith(prefix + "/"):
        return r"\\192.168.68.105\data" + "\\" + path[len(prefix) + 1:].replace("/", "\\")
    return ""


def review_writes_enabled() -> bool:
    return os.getenv("CORE_REVIEW_WRITES_ENABLED", "false").casefold() == "true"


WORKSET_SELECT = """
    SELECT
        w.file_id, w.content_group_id, w.content_sha256, w.filename, w.extension, w.path,
        w.size_bytes, w.workset_status, w.reason_code,
        w.last_qualifying_activity_at, w.activity_basis_source,
        w.activity_confidence, w.filesystem_modified_at,
        w.policy_version, w.policy_checksum,
        c.category, c.document_family, c.lifecycle,
        c.suggested_path, c.sensitivity, c.confidence AS classification_confidence
    FROM public.v_active_document_workset w
    LEFT JOIN public.v_current_file_classification c ON c.file_id = w.file_id
"""


def enrich_workset_row(row: dict[str, Any]) -> dict[str, Any]:
    item = {key: iso(value) for key, value in row.items()}
    item["smb_path"] = smb_path(str(row["path"]))
    item["classification_status"] = "accepted" if row.get("category") else "not_reviewed"
    item["migration_status"] = "virtual_only"
    privacy_proposal = propose_privacy(row)
    item["privacy_proposal"] = privacy_proposal
    item["current_privacy_classification"] = row.get("latest_privacy_classification")
    item["effective_privacy_classification"] = (
        row.get("latest_privacy_classification") or privacy_proposal["classification"]
    )
    item["privacy_source"] = (
        "human_review" if row.get("latest_privacy_classification") else "core_rule_proposal"
    )
    reviewed_family = (
        row.get("latest_review_family")
        if row.get("latest_review_decision") == "accepted" else None
    )
    reviewed_category = (
        row.get("latest_review_category")
        if row.get("latest_review_decision") == "accepted" else None
    )
    item["effective_category"] = reviewed_category or row.get("category")
    item["effective_document_family"] = reviewed_family or row.get("document_family")
    item["effective_family_source"] = (
        "accepted_portal_review" if reviewed_family else
        "accepted_classification" if row.get("document_family") else "core_proposal"
    )
    if row.get("workset_status") == "active":
        proposal = propose_target({
            **row,
            "accepted_category": item["effective_category"],
            "accepted_document_family": item["effective_document_family"],
            "accepted_lifecycle": row.get("lifecycle"),
        })
        initial_options = contextual_options(row, proposal)
        if proposal["category_code"] == "needs_review":
            proposal = propose_target({
                **row,
                "accepted_category": initial_options["category_options"][0]["code"],
                "accepted_document_family": item["effective_document_family"],
                "accepted_lifecycle": row.get("lifecycle"),
            })
        item["target_proposal"] = {
            key: proposal[key] for key in (
                "contract_version", "contract_checksum", "zone_code", "zone_label",
                "category_code", "category_label", "trajectory_code", "trajectory_label",
                "document_family_code", "folder_label", "suggested_target_path",
                "proposal_reason_code", "proposal_confidence",
            )
        }
        item["review_options"] = contextual_options(row, proposal)
    else:
        item["target_proposal"] = None
        item["review_options"] = None
    return item


@app.get("/api/v1/workset")
def workset(
    status: str = Query("active", pattern="^(active|inactive|needs_review|all)$"),
    extension: str = Query("all", pattern="^(pdf|docx|xlsx|all)$"),
    search: str = Query("", max_length=100),
    family: str = Query("all", max_length=80, pattern="^[a-z0-9_'-]{1,80}$|^all$"),
    review_state: str = Query("pending", pattern="^(pending|reviewed|all)$"),
    review_decision: str = Query("all", pattern="^(accepted|rejected|needs_review|passed|all)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conditions: list[str] = []
    params: list[Any] = []
    if status != "all":
        conditions.append("w.workset_status = %s")
        params.append(status)
    if extension != "all":
        conditions.append("w.extension = %s")
        params.append(extension)
    if search.strip():
        conditions.append("(w.filename ILIKE %s OR w.path ILIKE %s)")
        pattern = f"%{search.strip()}%"
        params.extend([pattern, pattern])
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    try:
        with db_connect() as conn:
            summary = query_one(conn, """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE workset_status = 'active') AS active,
                    COUNT(*) FILTER (WHERE workset_status = 'inactive') AS inactive,
                    COUNT(*) FILTER (WHERE workset_status = 'needs_review') AS needs_review
                FROM public.v_active_document_workset
            """)
            review_storage = bool(query_one(
                conn, "SELECT to_regclass('public.v_latest_document_review') IS NOT NULL AS available"
            )["available"])
            privacy_storage = bool(query_one(conn, """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'document_review_events'
                      AND column_name = 'corrected_privacy_classification'
                ) AS available
            """)["available"]) if review_storage else False
            review_select = """
                , r.id AS latest_review_id, r.decision AS latest_review_decision,
                  r.corrected_document_family_code AS latest_review_family,
                  r.corrected_category_code AS latest_review_category,
                  r.review_notes AS latest_review_notes, r.created_at AS latest_review_at
            """ if review_storage else ""
            review_join = """
                LEFT JOIN public.v_latest_document_review r
                  ON r.file_id = w.file_id AND r.review_type = 'target_path'
            """ if review_storage else ""
            privacy_select = """
                , p.id AS latest_privacy_review_id,
                  p.corrected_privacy_classification AS latest_privacy_classification,
                  p.created_at AS latest_privacy_review_at
            """ if privacy_storage else ""
            privacy_join = """
                LEFT JOIN public.v_latest_document_review p
                  ON p.file_id = w.file_id AND p.review_type = 'privacy_classification'
            """ if privacy_storage else ""
            rows = query_all(conn, WORKSET_SELECT.replace(
                "FROM public.v_active_document_workset w",
                review_select + privacy_select + " FROM public.v_active_document_workset w"
            ) + review_join + privacy_join + where +
                " ORDER BY w.last_qualifying_activity_at DESC NULLS LAST, w.filename, w.file_id",
                tuple(params),
            )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"workset unavailable: {type(exc).__name__}") from exc
    enriched = [enrich_workset_row(row) for row in rows]
    review_summary = {
        "pending": sum(not item.get("latest_review_id") for item in enriched),
        "reviewed": sum(bool(item.get("latest_review_id")) for item in enriched),
        "accepted": sum(item.get("latest_review_decision") == "accepted" for item in enriched),
        "needs_review": sum(item.get("latest_review_decision") == "needs_review" for item in enriched),
        "rejected": sum(item.get("latest_review_decision") == "rejected" for item in enriched),
        "passed": sum(item.get("latest_review_decision") == "passed" for item in enriched),
    }
    if review_state == "pending":
        enriched = [item for item in enriched if not item.get("latest_review_id")]
    elif review_state == "reviewed":
        enriched = [item for item in enriched if item.get("latest_review_id")]
    if review_decision != "all":
        enriched = [item for item in enriched if item.get("latest_review_decision") == review_decision]
    families: dict[str, dict[str, Any]] = {}
    for item in enriched:
        proposal = item.get("target_proposal") or {}
        code = str(proposal.get("document_family_code") or item.get("document_family") or "unknown")
        label = str(proposal.get("folder_label") or item.get("document_family") or "Nog te bepalen")
        families.setdefault(code, {"code": code, "label": label, "count": 0})["count"] += 1
    if family != "all":
        enriched = [item for item in enriched if str(
            (item.get("target_proposal") or {}).get("document_family_code")
            or item.get("document_family") or "unknown"
        ) == family]
    count = len(enriched)
    documents = enriched[offset:offset + limit]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "interactive_review" if review_writes_enabled() else "read_only",
        "summary": summary,
        "review_summary": review_summary,
        "filtered_total": count,
        "families": sorted(families.values(), key=lambda value: (value["label"].casefold(), value["code"])),
        "review_taxonomy": taxonomy(),
        "review_writes_enabled": review_writes_enabled(),
        "privacy_review_enabled": review_writes_enabled() and privacy_storage,
        "limit": limit,
        "offset": offset,
        "documents": documents,
        "safety": {"database_writes": review_writes_enabled(), "file_mutations": False,
                   "model_updates": False},
    }


@app.get("/api/v1/workset/{file_id}/reviews")
def workset_review_history(file_id: int):
    try:
        with db_connect() as conn:
            if not query_one(conn, "SELECT to_regclass('public.document_review_events') IS NOT NULL AS available")["available"]:
                raise HTTPException(status_code=503, detail="review storage migration is not applied")
            rows = query_all(conn, """
                SELECT id, review_contract_version, channel, review_type, file_id,
                       content_group_id, content_sha256, proposal_category_code,
                       proposal_document_family_code, proposal_lifecycle,
                       proposal_target_path, proposal_confidence, proposal_reason_code,
                       decision, corrected_document_family_code, corrected_category_code, review_notes,
                       reviewer, supersedes_event_id, created_at,
                       proposed_category_label, proposed_family_label, proposed_target_path,
                       proposed_target_path_raw, proposal_privacy_classification,
                       corrected_privacy_classification, privacy_rule_version, privacy_evidence,
                       target_path_input_kind, target_path_suggestion, target_path_suggestion_decision,
                       batch_id
                FROM public.document_review_events
                WHERE file_id = %s
                ORDER BY created_at DESC, id DESC
            """, (file_id,))
        return {"file_id": file_id, "events": [
            {key: iso(value) for key, value in row.items()} for row in rows
        ], "history_is_append_only": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"review history unavailable: {type(exc).__name__}") from exc


@app.get("/api/v1/workset/{file_id}/target-path-suggestion")
def workset_target_path_suggestion(file_id: int, value: str = Query(..., min_length=1, max_length=500)):
    """Offer a close confirmed path; never silently rewrite human input."""
    try:
        with db_connect() as conn:
            file_row = query_one(conn, "SELECT filename FROM public.files WHERE id = %s", (file_id,))
            known = query_all(conn, """
                SELECT proposed_target_path, proposal_target_path
                FROM public.document_review_events
                WHERE decision = 'accepted'
                  AND (proposed_target_path IS NOT NULL OR proposal_target_path IS NOT NULL)
                ORDER BY created_at DESC
                LIMIT 500
            """)
        paths = [
            str(path) for row in known
            for path in (row.get("proposed_target_path"), row.get("proposal_target_path")) if path
        ]
        result = suggest_known_target_path(value, filename=str(file_row["filename"]), known_paths=paths)
        return {**result, "mode": "advisory_only", "file_mutations": False}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"path suggestion unavailable: {type(exc).__name__}") from exc


@app.get("/api/v1/workset/{file_id}/target-path-preview")
def workset_target_path_preview(
    file_id: int, category: str = Query(..., min_length=1, max_length=80),
    family: str = Query(..., min_length=1, max_length=80),
):
    """Recalculate a target proposal from unsaved portal selections."""
    valid_categories = {item["code"] for item in taxonomy()["categories"]}
    valid_families = {item["code"] for item in taxonomy()["families"]}
    if category not in valid_categories or family not in valid_families:
        raise HTTPException(status_code=422, detail="invalid category or document family")
    try:
        with db_connect() as conn:
            matches = query_all(
                conn, WORKSET_SELECT + " WHERE w.file_id = %s AND w.workset_status = 'active'", (file_id,),
            )
        if not matches:
            raise HTTPException(status_code=409, detail="file is no longer an active workset candidate")
        row = matches[0]
        preview = propose_target({
            **row, "accepted_category": category,
            "accepted_document_family": family,
            "accepted_lifecycle": row.get("lifecycle"),
        })
        return {
            "category_code": category, "document_family_code": family,
            "suggested_target_path": preview["suggested_target_path"],
            "proposal_confidence": preview["proposal_confidence"],
            "proposal_reason_code": preview["proposal_reason_code"],
            "mode": "live_preview", "database_writes": False, "file_mutations": False,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"target path preview unavailable: {type(exc).__name__}") from exc


@app.get("/api/v1/workset/reviews/export")
def export_workset_reviews(format: str = Query("csv", pattern="^(csv|json)$")):
    try:
        with db_connect() as conn:
            if not query_one(conn, "SELECT to_regclass('public.document_review_events') IS NOT NULL AS available")["available"]:
                raise HTTPException(status_code=503, detail="review storage migration is not applied")
            rows = query_all(conn, """
                SELECT e.id, e.created_at, e.reviewer, e.channel, e.review_type,
                       e.file_id, f.filename, e.content_group_id, e.content_sha256,
                       e.decision, e.corrected_category_code, e.corrected_document_family_code, e.review_notes,
                       e.proposal_category_code, e.proposal_document_family_code,
                       e.proposal_lifecycle, e.proposal_target_path,
                       e.proposal_confidence, e.proposal_reason_code,
                       e.review_contract_version, e.supersedes_event_id,
                       e.proposed_category_label, e.proposed_family_label, e.proposed_target_path,
                       e.proposed_target_path_raw, e.proposal_privacy_classification,
                       e.corrected_privacy_classification, e.privacy_rule_version, e.privacy_evidence,
                       e.target_path_input_kind, e.target_path_suggestion, e.target_path_suggestion_decision,
                       e.batch_id
                FROM public.document_review_events e
                JOIN public.files f ON f.id = e.file_id
                ORDER BY e.created_at DESC, e.id DESC
            """)
        serializable = [{key: iso(value) for key, value in row.items()} for row in rows]
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        if format == "json":
            return Response(
                content=json.dumps({"schema_version": "document-review-export-v1", "events": serializable},
                                   ensure_ascii=False, indent=2, default=str) + "\n",
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="document-reviews-{stamp}.json"'},
            )
        fields = list(serializable[0]) if serializable else ["id", "created_at", "file_id", "decision"]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields, delimiter=";", lineterminator="\n")
        writer.writeheader()
        writer.writerows(serializable)
        return Response(
            content="\ufeff" + output.getvalue(), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="document-reviews-{stamp}.csv"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"review export unavailable: {type(exc).__name__}") from exc


def prepare_bulk_review(conn, payload: dict[str, Any]) -> list[dict[str, Any]]:
    selections = payload.get("items")
    if not isinstance(selections, list) or not 1 <= len(selections) <= 50:
        raise HTTPException(status_code=422, detail="select between 1 and 50 visible proposals")
    try:
        file_ids = [int(item["file_id"]) for item in selections]
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="every bulk item requires a valid file_id") from exc
    if len(set(file_ids)) != len(file_ids):
        raise HTTPException(status_code=422, detail="duplicate files are not allowed in a bulk review")
    rows = query_all(
        conn, WORKSET_SELECT + " WHERE w.file_id = ANY(%s) AND w.workset_status = 'active'", (file_ids,),
    )
    by_id = {int(row["file_id"]): row for row in rows}
    if set(by_id) != set(file_ids):
        raise HTTPException(status_code=409, detail="one or more files are no longer active workset candidates")
    valid_categories = {item["code"] for item in taxonomy()["categories"]}
    valid_families = {item["code"] for item in taxonomy()["families"]}
    prepared = []
    for selection in selections:
        file_id = int(selection["file_id"])
        category = str(selection.get("category") or "")
        family = str(selection.get("family") or "")
        privacy = str(selection.get("privacy") or "")
        if category not in valid_categories or family not in valid_families:
            raise HTTPException(status_code=422, detail=f"invalid classification for file {file_id}")
        if privacy not in {"low", "medium", "high"}:
            raise HTTPException(status_code=422, detail=f"invalid privacy label for file {file_id}")
        row = by_id[file_id]
        original = enrich_workset_row(row)["target_proposal"]
        proposal = propose_target({
            **row, "accepted_category": category, "accepted_document_family": family,
            "accepted_lifecycle": row.get("lifecycle"),
        })
        manual_path = str(selection.get("manual_target_path") or "").strip()
        normalized = normalize_target_path(
            manual_path or proposal["suggested_target_path"], filename=str(row["filename"]),
        )
        privacy_proposal = propose_privacy(row)
        prepared.append({
            "row": row, "file_id": file_id, "filename": str(row["filename"]),
            "category": category, "family": family, "privacy": privacy,
            "target_path": str(normalized["normalized"]),
            "target_path_raw": manual_path or str(normalized["normalized"]),
            "target_path_input_kind": str(normalized["input_kind"]),
            "original_proposal": original, "privacy_proposal": privacy_proposal,
        })
    return prepared


def public_bulk_summary(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "file_id": item["file_id"], "filename": item["filename"],
        "target_path": item["target_path"], "privacy": item["privacy"],
    } for item in items]


@app.post("/api/v1/workset/reviews/bulk/preview")
def preview_bulk_workset_review(payload: dict[str, Any] = Body(...)):
    try:
        with db_connect() as conn:
            prepared = prepare_bulk_review(conn, payload)
        return {
            "mode": "confirmation_required", "document_count": len(prepared),
            "items": public_bulk_summary(prepared), "database_writes": False,
            "file_mutations": False, "privacy_confirmation_included": True,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"bulk preview unavailable: {type(exc).__name__}") from exc


@app.post("/api/v1/workset/reviews/bulk")
def create_bulk_workset_review(payload: dict[str, Any] = Body(...)):
    if not review_writes_enabled():
        raise HTTPException(status_code=403, detail="interactive reviews are disabled")
    try:
        idempotency_key = str(payload["idempotency_key"])
        uuid.UUID(idempotency_key)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="valid UUID idempotency_key required") from exc
    reviewer = os.getenv("CORE_REVIEWER", "hugo")
    try:
        with db_connect() as conn:
            prepared = prepare_bulk_review(conn, payload)
            snapshot = public_bulk_summary(prepared)
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO public.document_review_batches (
                        idempotency_key, channel, decision, document_count, selection_snapshot, reviewer
                    ) VALUES (%s, 'workset_portal', 'accepted', %s, %s::jsonb, %s)
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING id, created_at
                """, (idempotency_key, len(prepared), json.dumps(snapshot, ensure_ascii=False), reviewer))
                batch = cur.fetchone()
                if not batch:
                    cur.execute("""
                        SELECT id, created_at, document_count, selection_snapshot
                        FROM public.document_review_batches WHERE idempotency_key = %s
                    """, (idempotency_key,))
                    existing = cur.fetchone()
                    if int(existing[2]) != len(prepared) or existing[3] != snapshot:
                        raise HTTPException(status_code=409, detail="idempotency key belongs to another batch")
                    return {
                        "status": "already_stored", "batch_id": str(existing[0]),
                        "created_at": iso(existing[1]), "document_count": len(prepared),
                        "classification_reviews": len(prepared), "privacy_reviews": len(prepared),
                        "file_mutations": False, "model_updates": False,
                    }
                batch_id, created_at = batch
                for item in prepared:
                    row, original = item["row"], item["original_proposal"]
                    cur.execute("""
                        SELECT review_type, id FROM public.v_latest_document_review
                        WHERE file_id = %s AND review_type IN ('target_path', 'privacy_classification')
                    """, (item["file_id"],))
                    supersedes = {kind: event_id for kind, event_id in cur.fetchall()}
                    target_key = str(uuid.uuid5(uuid.UUID(idempotency_key), f"target:{item['file_id']}"))
                    cur.execute("""
                        INSERT INTO public.document_review_events (
                            idempotency_key, review_contract_version, channel, review_type,
                            file_id, content_group_id, content_sha256,
                            proposal_category_code, proposal_document_family_code, proposal_lifecycle,
                            proposal_target_path, proposal_confidence, proposal_reason_code,
                            decision, corrected_document_family_code, corrected_category_code,
                            reviewer, supersedes_event_id, proposed_target_path, proposed_target_path_raw,
                            target_path_input_kind, target_path_suggestion_decision, batch_id
                        ) VALUES (%s,%s,'workset_portal','target_path',%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                  'accepted',%s,%s,%s,%s,%s,%s,%s,'no_suggestion',%s)
                        ON CONFLICT (idempotency_key) DO NOTHING
                    """, (
                        target_key, CONTRACT_VERSION, item["file_id"], row["content_group_id"],
                        row["content_sha256"], original["category_code"],
                        original["document_family_code"], original["zone_code"],
                        original["suggested_target_path"], original["proposal_confidence"],
                        original["proposal_reason_code"], item["family"], item["category"], reviewer,
                        supersedes.get("target_path"), item["target_path"], item["target_path_raw"],
                        item["target_path_input_kind"], batch_id,
                    ))
                    privacy_proposal = item["privacy_proposal"]
                    privacy_key = str(uuid.uuid5(uuid.UUID(idempotency_key), f"privacy:{item['file_id']}"))
                    cur.execute("""
                        INSERT INTO public.document_review_events (
                            idempotency_key, review_contract_version, channel, review_type,
                            file_id, content_group_id, content_sha256, proposal_confidence,
                            proposal_reason_code, decision, reviewer, supersedes_event_id,
                            proposal_privacy_classification, corrected_privacy_classification,
                            privacy_rule_version, privacy_evidence, batch_id
                        ) VALUES (%s,%s,'workset_portal','privacy_classification',%s,%s,%s,%s,%s,
                                  'accepted',%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (idempotency_key) DO NOTHING
                    """, (
                        privacy_key, PRIVACY_RULE_VERSION, item["file_id"], row["content_group_id"],
                        row["content_sha256"], privacy_proposal["confidence"],
                        privacy_proposal["reason_code"], reviewer,
                        supersedes.get("privacy_classification"), privacy_proposal["classification"],
                        item["privacy"], privacy_proposal["rule_version"],
                        privacy_proposal["evidence"], batch_id,
                    ))
        return {
            "status": "stored", "batch_id": str(batch_id), "created_at": iso(created_at),
            "document_count": len(prepared), "classification_reviews": len(prepared),
            "privacy_reviews": len(prepared), "file_mutations": False, "model_updates": False,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"bulk review unavailable: {type(exc).__name__}") from exc


@app.post("/api/v1/workset/reviews")
def create_workset_review(payload: dict[str, Any] = Body(...)):
    if not review_writes_enabled():
        raise HTTPException(status_code=403, detail="interactive reviews are disabled")
    try:
        file_id = int(payload["file_id"])
        idempotency_key = str(payload["idempotency_key"])
        uuid.UUID(idempotency_key)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="valid file_id and UUID idempotency_key required") from exc
    decision = str(payload.get("decision") or "")
    if decision not in {"accepted", "rejected", "needs_review", "passed"}:
        raise HTTPException(status_code=422, detail="invalid review decision")
    review_type = str(payload.get("review_type") or "target_path")
    if review_type not in {"target_path", "privacy_classification"}:
        raise HTTPException(status_code=422, detail="invalid review type")
    privacy_classification = str(payload.get("privacy_classification") or "") or None
    if review_type == "privacy_classification" and privacy_classification not in {"low", "medium", "high"}:
        raise HTTPException(status_code=422, detail="invalid privacy classification")
    family = str(payload.get("corrected_document_family_code") or "") or None
    category = str(payload.get("corrected_category_code") or "") or None
    notes = str(payload.get("review_notes") or "") or None
    proposed_category = str(payload.get("proposed_category_label") or "").strip() or None
    proposed_family = str(payload.get("proposed_family_label") or "").strip() or None
    proposed_path_input = str(payload.get("proposed_target_path") or "").strip() or None
    proposed_path_raw = str(payload.get("proposed_target_path_original") or "").strip() or proposed_path_input
    path_suggestion = str(payload.get("target_path_suggestion") or "").strip() or None
    path_suggestion_decision = str(payload.get("target_path_suggestion_decision") or "no_suggestion")
    if path_suggestion_decision not in {"accepted", "dismissed", "new_path", "no_suggestion"}:
        raise HTTPException(status_code=422, detail="invalid target path suggestion decision")
    normalized_path = None
    proposed_path = None
    if family and not re.fullmatch(r"[a-z0-9_'-]{1,80}", family):
        raise HTTPException(status_code=422, detail="invalid document family code")
    valid_categories = {item["code"] for item in taxonomy()["categories"]}
    valid_families = {item["code"] for item in taxonomy()["families"]}
    if review_type == "target_path" and category not in valid_categories:
        raise HTTPException(status_code=422, detail="invalid category code")
    if review_type == "target_path" and family not in valid_families:
        raise HTTPException(status_code=422, detail="invalid document family code")
    if notes and len(notes) > 2000:
        raise HTTPException(status_code=422, detail="review note exceeds 2000 characters")
    if proposed_category and len(proposed_category) > 120:
        raise HTTPException(status_code=422, detail="proposed category exceeds 120 characters")
    if proposed_family and len(proposed_family) > 120:
        raise HTTPException(status_code=422, detail="proposed family exceeds 120 characters")
    if proposed_path and len(proposed_path) > 500:
        raise HTTPException(status_code=422, detail="proposed target path exceeds 500 characters")
    try:
        with db_connect() as conn:
            if not query_one(conn, "SELECT to_regclass('public.document_review_events') IS NOT NULL AS available")["available"]:
                raise HTTPException(status_code=503, detail="review storage migration is not applied")
            matches = query_all(
                conn, WORKSET_SELECT + " WHERE w.file_id = %s AND w.workset_status = 'active'", (file_id,),
            )
            if not matches:
                raise HTTPException(status_code=409, detail="file is no longer an active workset candidate")
            row = matches[0]
            try:
                normalized_path = normalize_target_path(
                    proposed_path_input, filename=str(row["filename"]),
                ) if proposed_path_input else None
                normalized_suggestion = normalize_target_path(
                    path_suggestion, filename=str(row["filename"]),
                ) if path_suggestion else None
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            proposed_path = str(normalized_path["normalized"]) if normalized_path else None
            path_suggestion = str(normalized_suggestion["normalized"]) if normalized_suggestion else None
            if path_suggestion_decision == "accepted" and proposed_path != path_suggestion:
                raise HTTPException(status_code=422, detail="accepted suggestion must equal proposed target path")
            if review_type == "privacy_classification":
                privacy = propose_privacy(row)
                latest = query_all(
                    conn,
                    "SELECT id FROM public.v_latest_document_review WHERE file_id = %s AND review_type = 'privacy_classification'",
                    (file_id,),
                )
                supersedes_event_id = latest[0]["id"] if latest else None
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO public.document_review_events (
                            idempotency_key, review_contract_version, channel, review_type,
                            file_id, content_group_id, content_sha256,
                            proposal_confidence, proposal_reason_code, decision,
                            review_notes, reviewer, supersedes_event_id,
                            proposal_privacy_classification, corrected_privacy_classification,
                            privacy_rule_version, privacy_evidence
                        ) VALUES (%s,%s,'workset_portal','privacy_classification',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (idempotency_key) DO NOTHING
                        RETURNING id, created_at, file_id, decision
                    """, (
                        idempotency_key, PRIVACY_RULE_VERSION, row["file_id"], row["content_group_id"],
                        row["content_sha256"], privacy["confidence"], privacy["reason_code"], decision,
                        notes, os.getenv("CORE_REVIEWER", "hugo"), supersedes_event_id,
                        privacy["classification"], privacy_classification, privacy["rule_version"],
                        privacy["evidence"],
                    ))
                    created = cur.fetchone()
                    if not created:
                        cur.execute(
                            "SELECT id, created_at, file_id, decision FROM public.document_review_events WHERE idempotency_key = %s",
                            (idempotency_key,),
                        )
                        created = cur.fetchone()
                    if int(created[2]) != file_id or str(created[3]) != decision:
                        raise HTTPException(status_code=409, detail="idempotency key belongs to another review")
                return {
                    "status": "stored", "review_id": str(created[0]), "created_at": iso(created[1]),
                    "review_type": review_type, "decision": decision,
                    "privacy_classification": privacy_classification,
                    "proposal_privacy_classification": privacy["classification"],
                    "privacy_rule_version": privacy["rule_version"],
                    "learning_evidence": True, "file_mutations": False, "model_updates": False,
                }
            proposal = enrich_workset_row(row).get("target_proposal")
            if not proposal:
                raise HTTPException(status_code=409, detail="file is no longer an active workset candidate")
            latest = query_all(
                conn,
                "SELECT id FROM public.v_latest_document_review WHERE file_id = %s AND review_type = 'target_path'",
                (file_id,),
            )
            supersedes_event_id = latest[0]["id"] if latest else None
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO public.document_review_events (
                        idempotency_key, review_contract_version, channel, review_type,
                        file_id, content_group_id, content_sha256,
                        proposal_category_code, proposal_document_family_code,
                        proposal_lifecycle, proposal_target_path, proposal_confidence,
                        proposal_reason_code, decision, corrected_document_family_code, corrected_category_code,
                        review_notes, reviewer, supersedes_event_id,
                        proposed_category_label, proposed_family_label, proposed_target_path,
                        proposed_target_path_raw, target_path_input_kind,
                        target_path_suggestion, target_path_suggestion_decision
                    ) VALUES (%s,%s,'workset_portal','target_path',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING id, created_at, file_id, decision
                """, (
                    idempotency_key, CONTRACT_VERSION, row["file_id"], row["content_group_id"],
                    row["content_sha256"], proposal["category_code"], proposal["document_family_code"],
                    proposal["zone_code"], proposal["suggested_target_path"],
                    proposal["proposal_confidence"], proposal["proposal_reason_code"], decision,
                    family, category, notes, os.getenv("CORE_REVIEWER", "hugo"), supersedes_event_id,
                    proposed_category, proposed_family, proposed_path, proposed_path_raw,
                    str(normalized_path["input_kind"]) if normalized_path else None,
                    path_suggestion, path_suggestion_decision,
                ))
                created = cur.fetchone()
                if not created:
                    cur.execute("SELECT id, created_at, file_id, decision FROM public.document_review_events WHERE idempotency_key = %s",
                                (idempotency_key,))
                    created = cur.fetchone()
                if int(created[2]) != file_id or str(created[3]) != decision:
                    raise HTTPException(status_code=409, detail="idempotency key belongs to another review")
        effective_proposal = proposal
        if decision == "accepted" and family and category:
            effective_proposal = propose_target({
                **row,
                "accepted_category": category,
                "accepted_document_family": family,
                "accepted_lifecycle": row.get("lifecycle"),
            })
        return {
            "status": "stored", "review_id": str(created[0]), "created_at": iso(created[1]),
            "decision": decision, "corrected_document_family_code": family,
            "corrected_category_code": category,
            "proposed_category_label": proposed_category,
            "proposed_family_label": proposed_family,
            "proposed_target_path": proposed_path,
            "proposed_target_path_raw": proposed_path_raw,
            "target_path_input_kind": normalized_path["input_kind"] if normalized_path else None,
            "target_path_suggestion": path_suggestion,
            "target_path_suggestion_decision": path_suggestion_decision,
            "target_path_normalized": bool(normalized_path and normalized_path["changed"]),
            "effective_target_proposal": {
                key: effective_proposal[key] for key in (
                    "document_family_code", "folder_label", "suggested_target_path",
                    "proposal_confidence", "proposal_reason_code",
                )
            },
            "database_writes": True, "file_mutations": False, "model_updates": False,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"review unavailable: {type(exc).__name__}") from exc
