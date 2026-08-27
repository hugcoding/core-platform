from __future__ import annotations

import csv
import io
import json
import mimetypes
import os
import re
import shutil
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Optional
from collections import Counter

import psycopg2
import redis
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from core.organization.target_path import CONTRACT_VERSION, propose_target
from core.organization.review_taxonomy import (
    build_taxonomy_proposals,
    contextual_options,
    extend_taxonomy,
    normalize_taxonomy_label,
    taxonomy,
    taxonomy_extension_code,
    taxonomy_fallback_proposal,
)
from core.organization.review_learning import (build_proposed_family_candidates,build_learned_family_preferences,)
from core.organization.path_normalization import normalize_target_path, suggest_known_target_path
from core.organization.filename_normalization import normalize_proposed_filename, target_with_filename
from core.organization.privacy_classification import RULE_VERSION as PRIVACY_RULE_VERSION, propose_privacy
from core.organization.similar_documents import apply_similar_review_proposals
from core.organization.trajectory_learning import build_trajectory_rules, matching_trajectory_rule
from core.organization.learning_context import build_learning_context_rules, matching_learning_context_rule
from core.semantic.rag import GenerationRequest, OpenAICompatibleLocalProvider
from core.semantic.workset_llm import (
    MAX_DOCUMENTS as LLM_MAX_DOCUMENTS, PROMPT_VERSION as LLM_PROMPT_VERSION,
    SCHEMA_VERSION as LLM_SCHEMA_VERSION, abstention as llm_abstention,
    build_prompt as build_llm_prompt, extract_bounded_context, validate_proposal as validate_llm_proposal,
)


APP_DIR = Path(__file__).parent
EXPORT_DIR = Path(os.getenv("EXPORT_DIR", "/exports/migration-inventory"))
HOST_PROC = Path(os.getenv("HOST_PROC", "/host/proc"))
STORAGE_PATH = Path(os.getenv("STORAGE_PATH", "/volume1"))
STARTED = time.monotonic()
CLASSIFIABLE_WORKSET_STATUSES = {"active", "inactive", "quarantine"}
TARGET_PATH_REFERENCE_TTL_SECONDS = 30.0
_target_path_reference_lock = threading.Lock()
_target_path_reference_cache: dict[str, Any] = {
    "expires_at": 0.0, "paths": None, "filenames": {},
}

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


def effective_review_taxonomy(conn: Any) -> dict[str, Any]:
    # Keep this optional extension independent from the established query
    # sequence: older deployments and test doubles do not have the view yet.
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass('public.v_active_document_taxonomy_extensions') IS NOT NULL"
            )
            result = cur.fetchone()
            available = bool(result and isinstance(result[0], bool) and result[0])
    except Exception:
        available = False
    extensions = query_all(conn, """
        SELECT proposal_type, proposed_label, taxonomy_code, category_code
        FROM public.v_active_document_taxonomy_extensions
        ORDER BY proposal_type, proposed_label, taxonomy_code
    """) if available else []
    return extend_taxonomy(taxonomy(), extensions)


def taxonomy_proposal_rows(conn: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    reviews = query_all(conn, """
        SELECT id, file_id, review_type, decision, corrected_category_code,
               proposed_category_label, proposed_family_label, created_at
        FROM public.document_review_events
        WHERE review_type = 'target_path'
          AND (proposed_category_label IS NOT NULL OR proposed_family_label IS NOT NULL)
        ORDER BY file_id, created_at, id
    """)
    available = query_one(
        conn, "SELECT to_regclass('public.v_latest_document_taxonomy_proposal_review') IS NOT NULL AS available"
    )["available"]
    decisions = query_all(conn, """
        SELECT proposal_key, decision, reviewer, created_at
        FROM public.v_latest_document_taxonomy_proposal_review
    """) if available else []
    return reviews, decisions


def iso(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value


def invalidate_target_path_reference_cache() -> None:
    """Make newly accepted human paths available to the next advisory request."""
    with _target_path_reference_lock:
        _target_path_reference_cache["expires_at"] = 0.0
        _target_path_reference_cache["paths"] = None


def target_path_reference_data(file_id: int) -> tuple[str, list[str]]:
    """Reuse read-only path evidence while a user is typing in one review panel."""
    now = time.monotonic()
    with _target_path_reference_lock:
        filename = _target_path_reference_cache["filenames"].get(file_id)
        paths = _target_path_reference_cache["paths"]
        if now >= float(_target_path_reference_cache["expires_at"]):
            paths = None
        if filename is not None and paths is not None:
            return str(filename), list(paths)
        # Keep concurrent stale browser requests from repeating the same database work.
        with db_connect() as conn:
            if filename is None:
                file_row = query_one(conn, "SELECT filename FROM public.files WHERE id = %s", (file_id,))
                filename = str(file_row["filename"])
            if paths is None:
                known = query_all(conn, """
                    SELECT proposed_target_path, proposal_target_path
                    FROM public.document_review_events
                    WHERE decision = 'accepted'
                      AND (proposed_target_path IS NOT NULL OR proposal_target_path IS NOT NULL)
                    ORDER BY created_at DESC
                    LIMIT 500
                """)
                # Matching is directory-based. Compare each confirmed directory once,
                # rather than repeatedly comparing every reviewed file in that directory.
                paths = sorted({
                    str(PurePosixPath(str(path).replace("\\", "/")).parent)
                    for row in known
                    for path in (row.get("proposed_target_path"), row.get("proposal_target_path")) if path
                })
        filenames = _target_path_reference_cache["filenames"]
        if len(filenames) >= 2048:
            filenames.clear()
        filenames[file_id] = filename
        _target_path_reference_cache["paths"] = paths
        _target_path_reference_cache["expires_at"] = now + TARGET_PATH_REFERENCE_TTL_SECONDS
        return filename, list(paths)


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


@app.get("/api/v1/workset/{file_id}/content")
def open_workset_document(file_id: int):
    """Open the current verified physical content; never mutate it."""
    try:
        with db_connect() as conn:
            rows = query_all(conn, """
                SELECT f.id, COALESCE(location.current_path, f.path) AS path, f.filename
                FROM public.files f
                LEFT JOIN public.v_workset_current_physical_location location
                  ON location.file_id = f.id
                WHERE f.id = %s
                  AND (f.deleted_at IS NULL OR location.current_path IS NOT NULL)
            """, (file_id,))
        if not rows:
            raise HTTPException(status_code=404, detail="document not found")
        row = rows[0]
        root = Path("/volume1/data").resolve()
        source = Path(str(row["path"])).resolve()
        if source == root or root not in source.parents:
            raise HTTPException(status_code=403, detail="document is outside the managed data root")
        if not source.is_file():
            raise HTTPException(status_code=404, detail="document is unavailable on storage")
        extension = source.suffix.casefold()
        inline_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".txt"}
        media_type = mimetypes.guess_type(str(source))[0] or "application/octet-stream"
        return FileResponse(
            source, filename=str(row["filename"]), media_type=media_type,
            content_disposition_type="inline" if extension in inline_extensions else "attachment",
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"document unavailable: {type(exc).__name__}") from exc


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
                  (SELECT COUNT(*) FROM v_file_events_effective
                   WHERE event_status = 'active') AS active_events
                FROM files
            """)
            with conn.cursor() as cur:
                cur.execute("""SELECT id, type, status, started_at, finished_at, files_discovered,
                                      jobs_enqueued, jobs_processed
                               FROM scan_sessions ORDER BY started_at DESC LIMIT 8""")
                columns = [item.name for item in cur.description]
                recent_scans = [{key: iso(value) for key, value in zip(columns, row)} for row in cur.fetchall()]
                latest_scan = recent_scans[0] if recent_scans else {}
            if query_one(conn, "SELECT to_regclass('public.workset_ai_jobs') IS NOT NULL AS available")["available"]:
                ai_counts = query_all(conn, """
                    SELECT status, count(*) AS job_count FROM public.workset_ai_jobs GROUP BY status
                """)
                for item in ai_counts:
                    metrics[f"ai_{item['status']}"] = int(item["job_count"])
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
        if llm_enabled():
            services.append(heartbeat_service(client, "workset_ai_worker"))
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


def llm_enabled() -> bool:
    return os.getenv("CORE_LLM_ENABLED", "false").casefold() == "true"


def validated_similarity_evidence(
    conn,
    raw: Any,
    category: str | None,
    family: str | None,
) -> dict[str, Any]:
    if not raw:
        return {}

    if not isinstance(raw, dict) or raw.get("status") != "consensus_proposal":
        raise HTTPException(
            status_code=422,
            detail="invalid similar-document evidence",
        )

    try:
        review_ids = [
            str(uuid.UUID(value))
            for value in raw["source_review_event_ids"]
        ]
        related_ids = [
            int(value)
            for value in raw.get("related_file_ids", [])
        ]
        score = float(raw["score"])
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=422,
            detail="invalid similar-document evidence",
        ) from exc

    if (
        not 1 <= len(review_ids) <= 10
        or len(related_ids) > 10
        or not 0.0 <= score <= 1.0
    ):
        raise HTTPException(
            status_code=422,
            detail="invalid similar-document evidence bounds",
        )

    sources = query_all(
        conn,
        """
        SELECT
            id,
            file_id,
            corrected_category_code,
            corrected_document_family_code
        FROM public.document_review_events
        WHERE id = ANY(%s::uuid[])
          AND review_type = 'target_path'
          AND decision = 'accepted'
        """,
        (review_ids,),
    )

    if len(sources) != len(set(review_ids)):
        raise HTTPException(
            status_code=409,
            detail="similar-document source review changed",
        )

    judgment_counts = Counter(
        (
            str(source["corrected_category_code"]),
            str(source["corrected_document_family_code"]),
        )
        for source in sources
    )

    most_common = judgment_counts.most_common()

    if not most_common:
        raise HTTPException(
            status_code=409,
            detail="similar-document source review changed",
        )

    (winning_category, winning_family), support_count = most_common[0]

    second_count = (
        most_common[1][1]
        if len(most_common) > 1
        else 0
    )

    if support_count <= second_count:
        raise HTTPException(
            status_code=409,
            detail="similar-document reviews no longer have a clear majority",
        )

    if winning_category != category or winning_family != family:
        raise HTTPException(
            status_code=409,
            detail="similar-document majority changed",
        )

    total = len(sources)

    return {
        "rule_version": str(raw.get("rule_version") or "")[:80],
        "normalized_identity": str(
            raw.get("normalized_identity") or ""
        )[:200],
        "match_kind": "normalized_filename_cross_format",
        "score": score,
        "related_file_ids": sorted(set(related_ids)),
        "source_review_event_ids": sorted(set(review_ids)),
        "proposed_category_code": category,
        "proposed_document_family_code": family,
        "support_count": support_count,
        "review_count": total,
        "support_ratio": round(support_count / total, 2),
        "conflicting_human_judgments": len(judgment_counts) > 1,
    }


WORKSET_SELECT = """
    SELECT
        w.file_id,
        w.content_group_id,
        w.content_sha256,
        w.filename,
        w.extension,
        COALESCE(location.current_path, w.path) AS path,
        w.path AS registered_path,
        location.current_path AS current_physical_path,
        location.location_kind AS physical_location_kind,
        location.current_status AS physical_location_status,
        location.plan_id AS physical_location_plan_id,
        location.plan_item_id AS physical_location_item_id,
        location.status_changed_at AS physical_location_changed_at,
        w.size_bytes,
        w.workset_status,
        w.reason_code,
        w.last_qualifying_activity_at,
        w.activity_basis_source,
        w.activity_confidence,
        w.filesystem_modified_at,
        w.policy_version,
        w.policy_checksum,
        c.category,
        c.document_family,
        c.lifecycle,
        c.suggested_path,
        c.sensitivity,
        c.confidence AS classification_confidence,
        pe.classification AS content_privacy_classification,
        pe.confidence AS content_privacy_confidence,
        pe.signals AS content_privacy_signals,
        pe.rule_version AS content_privacy_rule_version,
        pe.extractor_version AS content_privacy_extractor_version,
        pe.created_at AS content_privacy_created_at
    FROM public.v_active_document_workset w
    LEFT JOIN public.v_current_file_classification c
        ON c.file_id = w.file_id
    LEFT JOIN public.v_workset_current_physical_location location
        ON location.file_id = w.file_id
    LEFT JOIN LATERAL (
        SELECT
            p.classification,
            p.confidence,
            p.signals,
            p.rule_version,
            p.extractor_version,
            p.created_at
        FROM public.file_privacy_evidence p
        WHERE p.file_id = w.file_id
          AND p.content_sha256 = w.content_sha256
        ORDER BY p.created_at DESC, p.id DESC
        LIMIT 1
    ) pe ON TRUE
"""

def workset_order_by(
    sort: str, review_state: str, review_decision: str, review_storage: bool,
) -> str:
    effective = sort
    if effective == "context":
        effective = (
            "review_desc"
            if review_storage and (review_state == "reviewed" or review_decision != "all")
            else "activity_desc"
        )
    orders = {
        "activity_desc": "w.last_qualifying_activity_at DESC NULLS LAST, LOWER(w.filename), w.filename, w.file_id",
        "review_desc": (
            "r.created_at DESC NULLS LAST, LOWER(w.filename), w.filename, w.file_id"
            if review_storage else
            "w.last_qualifying_activity_at DESC NULLS LAST, LOWER(w.filename), w.filename, w.file_id"
        ),
        "filename_asc": "LOWER(w.filename), w.filename, w.file_id",
        "filename_desc": "LOWER(w.filename) DESC, w.filename DESC, w.file_id",
    }
    return " ORDER BY " + orders[effective]


def resolve_effective_lifecycle(
    calculated_workset_status: Any,
    corrected_lifecycle: Any = None,
    active_until: Any = None,
    *,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Resolve the portal lifecycle once, including expiring human overrides."""
    calculated_lifecycle = {
        "active": "active", "inactive": "archive", "needs_review": "needs_review",
    }.get(str(calculated_workset_status), "needs_review")
    current = now or datetime.now(timezone.utc)
    lifecycle_expired = bool(
        corrected_lifecycle == "active" and active_until and active_until <= current
    )
    effective_lifecycle = (
        calculated_lifecycle if lifecycle_expired else corrected_lifecycle or calculated_lifecycle
    )
    return {
        "calculated_lifecycle": calculated_lifecycle,
        "effective_lifecycle": effective_lifecycle,
        "workset_status": {
            "active": "active", "archive": "inactive", "needs_review": "needs_review",
        }[effective_lifecycle],
        "lifecycle_expired": lifecycle_expired,
    }


def effective_lifecycle_for_file(conn: Any, row: dict[str, Any]) -> dict[str, Any]:
    """Read latest human lifecycle evidence for endpoints using the compact base query."""
    latest = query_all(conn, """
        SELECT corrected_lifecycle, lifecycle_active_until
        FROM public.v_latest_document_review
        WHERE file_id = %s AND review_type = 'lifecycle'
    """, (row["file_id"],))
    review = latest[0] if latest else {}
    resolved = resolve_effective_lifecycle(
        row.get("workset_status"), review.get("corrected_lifecycle"),
        review.get("lifecycle_active_until"),
    )
    if row.get("physical_location_kind") == "deletion_quarantine":
        return {
            **resolved, "effective_lifecycle": "quarantine", "workset_status": "quarantine",
            "lifecycle_expired": False, "restore_lifecycle": resolved["effective_lifecycle"],
            "restore_workset_status": resolved["workset_status"],
        }
    return {**resolved, "restore_lifecycle": resolved["effective_lifecycle"],
            "restore_workset_status": resolved["workset_status"]}

def effective_privacy_proposal(row: dict[str, Any]) -> dict[str, Any]:
    """Combine metadata privacy rules with persisted deterministic content evidence."""
    proposal = propose_privacy(row)

    content_privacy = str(
        row.get("content_privacy_classification") or ""
    ).casefold()

    if content_privacy != "high":
        return proposal

    content_confidence = str(
        row.get("content_privacy_confidence") or ""
    ).casefold()

    content_signals = list(
        row.get("content_privacy_signals") or []
    )

    return {
        **proposal,
        "classification": "high",
        "confidence": content_confidence or "high",
        "reason_code": "persisted_content_privacy_evidence",
        "rule_version": str(
            row.get("content_privacy_rule_version")
            or PRIVACY_RULE_VERSION
        ),
        "evidence": content_signals,
        "requires_human_review": True,
        "external_llm_content_allowed": False,
    }

def enrich_workset_row(row: dict[str, Any]) -> dict[str, Any]:
    item = {key: iso(value) for key, value in row.items()}
    item["calculated_workset_status"] = row.get("workset_status")
    item["smb_path"] = smb_path(str(row["path"]))
    item["classification_status"] = "accepted" if row.get("category") else "not_reviewed"
    item["migration_status"] = row.get("physical_location_status") or "virtual_only"
    item["physical_location_kind"] = row.get("physical_location_kind") or "registered_path"
    item["is_deletion_quarantined"] = row.get("physical_location_kind") == "deletion_quarantine"
    privacy_proposal = effective_privacy_proposal(row)

    item["privacy_proposal"] = privacy_proposal

    item["current_privacy_classification"] = row.get(
        "latest_privacy_classification"
    )

    item["effective_privacy_classification"] = (
        row.get("latest_privacy_classification")
        or privacy_proposal["classification"]
    )

    item["privacy_source"] = (
        "human_review"
        if row.get("latest_privacy_classification")
        else "content_privacy_evidence"
        if privacy_proposal["reason_code"] == "persisted_content_privacy_evidence"
        else "core_rule_proposal"
    )
    lifecycle = resolve_effective_lifecycle(
        row.get("workset_status"), row.get("latest_corrected_lifecycle"),
        row.get("latest_lifecycle_active_until"),
    )
    item["calculated_lifecycle"] = lifecycle["calculated_lifecycle"]
    item["current_lifecycle_decision"] = row.get("latest_corrected_lifecycle")
    active_until = row.get("latest_lifecycle_active_until")
    item["effective_lifecycle"] = lifecycle["effective_lifecycle"]
    item["lifecycle_active_until"] = iso(active_until)
    item["workset_status"] = lifecycle["workset_status"]
    item["lifecycle_source"] = (
        "expired_human_review" if lifecycle["lifecycle_expired"] else
        "human_review" if row.get("latest_corrected_lifecycle") else "core_workset_policy"
    )
    proposal_lifecycle = lifecycle["effective_lifecycle"]
    if item["is_deletion_quarantined"]:
        item["effective_lifecycle"] = "quarantine"
        item["workset_status"] = "quarantine"
        item["lifecycle_source"] = "verified_deletion_quarantine"
        item["restore_lifecycle"] = proposal_lifecycle
    item["nominations"] = {
        "archive": ({
            "id": str(row["archive_nomination_id"]),
            "review_at": iso(row.get("archive_review_at")),
            "reason": row.get("archive_nomination_reason"),
            "policy_version": row.get("archive_policy_version"),
        } if row.get("archive_nomination_id") else None),
        "deletion": ({
            "id": str(row["deletion_nomination_id"]),
            "review_at": iso(row.get("deletion_review_at")),
            "reason": row.get("deletion_nomination_reason"),
            "policy_version": row.get("deletion_policy_version"),
        } if row.get("deletion_nomination_id") else None),
    }
    if row.get("ai_proposal_id"):
        item["ai_proposal"] = {
            "id": str(row["ai_proposal_id"]), "run_id": str(row["ai_run_id"]),
            "file_id": int(row["file_id"]),
            "status": row.get("ai_status"), "category_code": row.get("ai_category_code"),
            "family_code": row.get("ai_family_code"), "lifecycle": row.get("ai_lifecycle"),
            "privacy_advice": row.get("ai_privacy_advice"), "confidence": row.get("ai_confidence"),
            "relation_kind": row.get("ai_relation_kind"), "related_file_ids": row.get("ai_related_file_ids") or [],
            "reason": row.get("ai_reason"), "model_id": row.get("ai_model_id"),
            "prompt_version": row.get("ai_prompt_version"), "created_at": iso(row.get("ai_created_at")),
        }
    else:
        item["ai_proposal"] = None
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
    if item.get("workset_status") in CLASSIFIABLE_WORKSET_STATUSES:
        proposal = propose_target({
            **row,
            "accepted_category": item["effective_category"],
            "accepted_document_family": item["effective_document_family"],
            "accepted_lifecycle": proposal_lifecycle,
        })

        fallback = taxonomy_fallback_proposal(row, proposal)

        if fallback:
            proposal = propose_target({
                **row,
                "accepted_category": fallback["category_code"],
                "accepted_document_family": fallback["document_family_code"],
                "accepted_lifecycle": proposal_lifecycle,
            })

            proposal["proposal_reason_code"] = fallback["reason_code"]
            proposal["proposal_confidence"] = fallback["confidence"]

            item["taxonomy_fallback_proposal"] = fallback

        item["target_proposal"] = {
            key: proposal[key] for key in (
                "contract_version",
                "contract_checksum",
                "zone_code",
                "zone_label",
                "category_code",
                "category_label",
                "trajectory_code",
                "trajectory_label",
                "document_family_code",
                "folder_label",
                "suggested_target_path",
                "proposal_reason_code",
                "proposal_confidence",
            )
        }

        item["review_options"] = contextual_options(row, proposal)

    else:
        item["target_proposal"] = None
        item["review_options"] = None

    return item


@app.get("/api/v1/workset")
def workset(
    status: str = Query("active", pattern="^(active|inactive|needs_review|quarantine|all)$"),
    extension: str = Query("all", pattern="^(pdf|docx|xlsx|all)$"),
    search: str = Query("", max_length=100),
    family: str = Query("all", max_length=80, pattern="^[a-z0-9_'-]{1,80}$|^all$"),
    review_state: str = Query("pending", pattern="^(pending|reviewed|all)$"),
    review_decision: str = Query("all", pattern="^(accepted|rejected|needs_review|passed|all)$"),
    nomination: str = Query("all", pattern="^(all|archive|deletion|none)$"),
    sort: str = Query("context", pattern="^(context|activity_desc|review_desc|filename_asc|filename_desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conditions: list[str] = []
    params: list[Any] = []
    if extension != "all":
        conditions.append("w.extension = %s")
        params.append(extension)
    if search.strip():
        conditions.append("(w.filename ILIKE %s OR w.path ILIKE %s OR location.current_path ILIKE %s)")
        pattern = f"%{search.strip()}%"
        params.extend([pattern, pattern, pattern])
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    try:
        with db_connect() as conn:
            review_taxonomy = effective_review_taxonomy(conn)
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
                  r.review_notes AS latest_review_notes, r.created_at AS latest_review_at,
                  r.proposed_category_label AS latest_proposed_category_label,
                  r.proposed_family_label AS latest_proposed_family_label,
                  r.proposed_target_path AS latest_proposed_target_path,
                  r.proposed_filename AS latest_proposed_filename,
                  r.proposed_filename_raw AS latest_proposed_filename_raw
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
            lifecycle_storage = bool(query_one(conn, """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'document_review_events'
                      AND column_name = 'corrected_lifecycle'
                ) AS available
            """)["available"]) if review_storage else False
            lifecycle_select = """
                , l.id AS latest_lifecycle_review_id,
                  l.decision AS latest_lifecycle_decision,
                  l.corrected_lifecycle AS latest_corrected_lifecycle,
                  l.lifecycle_active_until AS latest_lifecycle_active_until,
                  l.created_at AS latest_lifecycle_review_at
            """ if lifecycle_storage else ""
            lifecycle_join = """
                LEFT JOIN public.v_latest_document_review l
                  ON l.file_id = w.file_id AND l.review_type = 'lifecycle'
            """ if lifecycle_storage else ""
            ai_storage = bool(query_one(
                conn, "SELECT to_regclass('public.v_latest_workset_ai_proposal') IS NOT NULL AS available"
            )["available"])
            ai_select = """
                , a.id AS ai_proposal_id, a.run_id AS ai_run_id, a.status AS ai_status,
                  a.category_code AS ai_category_code, a.family_code AS ai_family_code,
                  a.lifecycle AS ai_lifecycle, a.privacy_advice AS ai_privacy_advice,
                  a.confidence AS ai_confidence, a.relation_kind AS ai_relation_kind,
                  a.related_file_ids AS ai_related_file_ids, a.reason AS ai_reason,
                  a.model_id AS ai_model_id, a.prompt_version AS ai_prompt_version,
                  a.created_at AS ai_created_at
            """ if ai_storage else ""
            ai_join = """
                LEFT JOIN public.v_latest_workset_ai_proposal a ON a.file_id = w.file_id
            """ if ai_storage else ""
            nomination_storage = bool(query_one(
                conn, "SELECT to_regclass('public.v_active_document_lifecycle_nominations') IS NOT NULL AS available"
            )["available"])
            nomination_select = """
                , na.id AS archive_nomination_id, na.review_at AS archive_review_at,
                  na.reason AS archive_nomination_reason, na.policy_version AS archive_policy_version,
                  nd.id AS deletion_nomination_id, nd.review_at AS deletion_review_at,
                  nd.reason AS deletion_nomination_reason, nd.policy_version AS deletion_policy_version
            """ if nomination_storage else ""
            nomination_join = """
                LEFT JOIN public.v_active_document_lifecycle_nominations na
                  ON na.file_id = w.file_id AND na.nomination_type = 'archive'
                LEFT JOIN public.v_active_document_lifecycle_nominations nd
                  ON nd.file_id = w.file_id AND nd.nomination_type = 'deletion'
            """ if nomination_storage else ""
            nomination_summary = query_one(conn, """
                SELECT
                    COUNT(*) FILTER (WHERE nomination_type = 'archive') AS archive,
                    COUNT(*) FILTER (WHERE nomination_type = 'deletion') AS deletion
                FROM public.v_active_document_lifecycle_nominations
            """) if nomination_storage else {"archive": 0, "deletion": 0}
            trajectory_reviews = query_all(conn, """
    SELECT DISTINCT ON (e.file_id)
           e.id, e.file_id, e.decision, e.proposed_target_path,
           e.created_at, e.review_type, e.proposed_family_label,
           e.corrected_category_code,
           e.corrected_document_family_code,
           f.filename, f.path
    FROM public.document_review_events e
    JOIN public.files f ON f.id = e.file_id
    WHERE e.review_type = 'target_path'
    ORDER BY e.file_id, e.created_at DESC, e.id DESC
""") if review_storage else []
            accepted_similarity_reviews = query_all(conn, """
                SELECT
                    r.id AS latest_review_id,
                    r.file_id,
                    r.decision AS latest_review_decision,
                    r.corrected_category_code AS latest_review_category,
                    r.corrected_document_family_code AS latest_review_family,
                    f.filename
                FROM public.v_latest_document_review r
                JOIN public.files f ON f.id = r.file_id
                WHERE r.review_type = 'target_path'
                AND r.decision = 'accepted'
                AND r.corrected_category_code IS NOT NULL
                AND r.corrected_document_family_code IS NOT NULL
            """) if review_storage else []
            rows = query_all(conn, WORKSET_SELECT.replace(
                "FROM public.v_active_document_workset w",
                review_select + privacy_select + lifecycle_select + ai_select + nomination_select
                + " FROM public.v_active_document_workset w"
            ) + review_join + privacy_join + lifecycle_join + ai_join + nomination_join + where + workset_order_by(
                sort, review_state, review_decision, review_storage,
            ),
                tuple(params),
            )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"workset unavailable: {type(exc).__name__}: {exc}"
        ) from exc
    category_labels = {item["code"]: item["label"] for item in review_taxonomy["categories"]}
    family_labels = {item["code"]: item["label"] for item in review_taxonomy["families"]}
    for row in rows:
        row["accepted_category_label"] = category_labels.get(str(row.get("latest_review_category") or ""))
        row["accepted_document_family_label"] = family_labels.get(str(row.get("latest_review_family") or ""))
    enriched = [enrich_workset_row(row) for row in rows]

    visible_ids = {int(item["file_id"]) for item in enriched}

    similarity_evidence = [
        {
            "file_id": row["file_id"],
            "filename": row["filename"],
            "extension": Path(str(row["filename"])).suffix.lstrip(".").casefold(),
            "latest_review_id": row["latest_review_id"],
            "latest_review_decision": row["latest_review_decision"],
            "latest_review_category": row["latest_review_category"],
            "latest_review_family": row["latest_review_family"],
        }
        for row in accepted_similarity_reviews
        if int(row["file_id"]) not in visible_ids
    ]

    similarity_result = apply_similar_review_proposals(
        enriched + similarity_evidence
    )

    enriched = [
        item
        for item in similarity_result
        if int(item["file_id"]) in visible_ids
    ]
    summary = {
        "total": len(enriched),
        "active": sum(item.get("workset_status") == "active" for item in enriched),
        "inactive": sum(item.get("workset_status") == "inactive" for item in enriched),
        "needs_review": sum(item.get("workset_status") == "needs_review" for item in enriched),
        "quarantine": sum(item.get("workset_status") == "quarantine" for item in enriched),
    }
    if status != "all":
        enriched = [item for item in enriched if item.get("workset_status") == status]
    learning_context_rules = build_learning_context_rules(trajectory_reviews)
    for item in enriched:
        rule = matching_learning_context_rule(item, learning_context_rules)
        if not rule or item.get("workset_status") not in CLASSIFIABLE_WORKSET_STATUSES:
            continue
        row = next(row for row in rows if int(row["file_id"]) == int(item["file_id"]))
        proposal = propose_target({
            **row,
            "accepted_category": rule["category_code"],
            "accepted_document_family": rule["family_code"],
            "accepted_lifecycle": item["effective_lifecycle"],
        })
        item["target_proposal"] = {key: proposal[key] for key in (
            "contract_version", "contract_checksum", "zone_code", "zone_label",
            "category_code", "category_label", "trajectory_code", "trajectory_label",
            "document_family_code", "folder_label", "suggested_target_path",
            "proposal_reason_code", "proposal_confidence",
        )}
        item["target_proposal"]["proposal_reason_code"] = "learned_human_course_context"
        item["target_proposal"]["proposal_confidence"] = rule["confidence"]
        item["learning_context_proposal"] = rule
        item["review_options"] = contextual_options(row, proposal)
    for item in enriched:
        similar = item.get("similar_document_proposal") or {}
        if (
            similar.get("status") != "consensus_proposal"
            or item.get("workset_status") not in {"active", "inactive"}
        ):
            continue
        row = next(row for row in rows if int(row["file_id"]) == int(item["file_id"]))
        proposal = propose_target({
            **row,
            "accepted_category": similar["proposed_category_code"],
            "accepted_document_family": similar["proposed_document_family_code"],
            "accepted_lifecycle": item["effective_lifecycle"],
        })
        item["target_proposal"] = {key: proposal[key] for key in (
            "contract_version", "contract_checksum", "zone_code", "zone_label",
            "category_code", "category_label", "trajectory_code", "trajectory_label",
            "document_family_code", "folder_label", "suggested_target_path",
            "proposal_reason_code", "proposal_confidence",
        )}
        item["target_proposal"]["proposal_reason_code"] = "similar_human_review_consensus"
        item["target_proposal"]["proposal_confidence"] = "high"
        item["review_options"] = contextual_options(row, proposal)
    trajectory_rules = build_trajectory_rules(trajectory_reviews, minimum_support=1)
    family_candidates = build_proposed_family_candidates(trajectory_reviews)
    learned_families = build_learned_family_preferences(trajectory_reviews)
    for item in enriched:
        current = item.get("target_proposal") or {}
        if current.get("category_code") != "work_career":
            continue
        rule = matching_trajectory_rule(item, trajectory_rules)
        if not rule:
            continue
        row = next(row for row in rows if int(row["file_id"]) == int(item["file_id"]))
        proposal = propose_target({
            **row,
            "accepted_category": item.get("effective_category") or current.get("category_code"),
            "accepted_document_family": item.get("effective_document_family")
                or current.get("document_family_code"),
            "accepted_lifecycle": item["effective_lifecycle"],
            "accepted_trajectory_label": rule["trajectory_label"],
            "accepted_trajectory_parts": rule["trajectory_parts"],
        })
        item["target_proposal"] = {key: proposal[key] for key in (
            "contract_version", "contract_checksum", "zone_code", "zone_label",
            "category_code", "category_label", "trajectory_code", "trajectory_label",
            "document_family_code", "folder_label", "suggested_target_path",
            "proposal_reason_code", "proposal_confidence",
        )}
        item["target_proposal"]["proposal_reason_code"] = (
            "learned_human_trajectory_consensus" if rule["support"] >= 3
            else "learned_human_trajectory_context"
        )
        item["target_proposal"]["proposal_confidence"] = rule["confidence"]
        item["trajectory_learning_proposal"] = rule
        item["review_options"] = contextual_options(row, proposal)
    for item in enriched:
        options = item.get("review_options")
        if not options:
            continue
        options["candidate_families"] = family_candidates
        options["learned_families"] = learned_families
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
    if nomination == "archive":
        enriched = [item for item in enriched if item["nominations"]["archive"]]
    elif nomination == "deletion":
        enriched = [item for item in enriched if item["nominations"]["deletion"]]
    elif nomination == "none":
        enriched = [item for item in enriched if not any(item["nominations"].values())]
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
        "nomination_summary": nomination_summary,
        "filtered_total": count,
        "families": sorted(families.values(), key=lambda value: (value["label"].casefold(), value["code"])),
        "review_taxonomy": review_taxonomy,
        "review_writes_enabled": review_writes_enabled(),
        "privacy_review_enabled": review_writes_enabled() and privacy_storage,
        "lifecycle_review_enabled": review_writes_enabled() and lifecycle_storage,
        "nomination_writes_enabled": review_writes_enabled() and nomination_storage,
        "llm_enabled": llm_enabled() and ai_storage,
        "limit": limit,
        "offset": offset,
        "documents": documents,
        "safety": {"database_writes": review_writes_enabled(), "file_mutations": False,
                   "model_updates": False},
    }


@app.get("/api/v1/workset/taxonomy-proposals")
def workset_taxonomy_proposals(
    decision: str = Query("pending", pattern="^(pending|accepted|rejected|all)$"),
):
    try:
        with db_connect() as conn:
            reviews, decisions = taxonomy_proposal_rows(conn)
            proposals = build_taxonomy_proposals(reviews, decisions)
            if decision != "all":
                proposals = [item for item in proposals if item["decision"] == decision]
            effective = effective_review_taxonomy(conn)
        category_labels = {item["code"]: item["label"] for item in effective["categories"]}
        for proposal in proposals:
            proposal["category_label"] = category_labels.get(
                proposal.get("category_code"), proposal.get("category_code")
            )
        return {
            "status": "ok", "proposals": proposals, "count": len(proposals),
            "writes_enabled": review_writes_enabled(), "file_mutations": False,
            "existing_reviews_mutated": False,
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"taxonomy proposals unavailable: {type(exc).__name__}: {exc}") from exc


@app.post("/api/v1/workset/taxonomy-proposals/reviews")
def review_workset_taxonomy_proposal(payload: dict[str, Any] = Body(...)):
    if not review_writes_enabled():
        raise HTTPException(status_code=403, detail="review writes are disabled")
    proposal_key = str(payload.get("proposal_key") or "").strip()
    decision = str(payload.get("decision") or "").strip()
    notes = str(payload.get("review_notes") or "").strip() or None
    try:
        idempotency_key = str(uuid.UUID(str(payload.get("idempotency_key") or "")))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="valid idempotency key required") from exc
    if decision not in {"accepted", "rejected"}:
        raise HTTPException(status_code=422, detail="invalid taxonomy decision")
    if notes and len(notes) > 2000:
        raise HTTPException(status_code=422, detail="review note exceeds 2000 characters")
    try:
        with db_connect() as conn:
            available = query_one(
                conn, "SELECT to_regclass('public.document_taxonomy_proposal_reviews') IS NOT NULL AS available"
            )["available"]
            if not available:
                raise HTTPException(status_code=503, detail="taxonomy proposal migration is not applied")
            reviews, decisions = taxonomy_proposal_rows(conn)
            candidate = next(
                (item for item in build_taxonomy_proposals(reviews, decisions)
                 if item["proposal_key"] == proposal_key), None,
            )
            if not candidate:
                raise HTTPException(status_code=409, detail="taxonomy proposal is stale or unavailable")
            latest = query_all(conn, """
                SELECT id FROM public.v_latest_document_taxonomy_proposal_review
                WHERE proposal_key = %s
            """, (proposal_key,))
            supersedes = latest[0]["id"] if latest else None
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO public.document_taxonomy_proposal_reviews (
                        idempotency_key, proposal_key, proposal_type, proposed_label,
                        normalized_label, taxonomy_code, category_code, decision,
                        source_review_event_ids, review_notes, reviewer, supersedes_event_id
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::uuid[],%s,%s,%s)
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING id, created_at
                """, (
                    idempotency_key, candidate["proposal_key"], candidate["proposal_type"],
                    candidate["proposed_label"], normalize_taxonomy_label(candidate["proposed_label"]),
                    taxonomy_extension_code(candidate["proposed_label"]), candidate.get("category_code"),
                    decision, candidate["source_review_event_ids"], notes,
                    os.getenv("CORE_REVIEWER", "hugo"), supersedes,
                ))
                created = cur.fetchone()
                if not created:
                    cur.execute("""
                        SELECT id, created_at, proposal_key, decision, taxonomy_code
                        FROM public.document_taxonomy_proposal_reviews
                        WHERE idempotency_key = %s
                    """, (idempotency_key,))
                    created = cur.fetchone()
                    if str(created[2]) != proposal_key or str(created[3]) != decision:
                        raise HTTPException(status_code=409, detail="idempotency key belongs to another taxonomy review")
        return {
            "status": "stored", "review_id": str(created[0]), "created_at": iso(created[1]),
            "proposal_key": proposal_key, "decision": decision,
            "taxonomy_code": candidate["taxonomy_code"], "file_mutations": False,
            "existing_reviews_mutated": False,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"taxonomy review unavailable: {type(exc).__name__}: {exc}") from exc


@app.post("/api/v1/workset/nominations")
def create_document_lifecycle_nomination(payload: dict[str, Any] = Body(...)):
    """Append or withdraw a nomination without changing a file or its workset state."""
    if not review_writes_enabled():
        raise HTTPException(status_code=403, detail="interactive nominations are disabled")
    try:
        file_id = int(payload["file_id"])
        idempotency_key = str(uuid.UUID(str(payload["idempotency_key"])))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="valid file_id and idempotency key required") from exc
    nomination_type = str(payload.get("nomination_type") or "")
    action = str(payload.get("action") or "")
    reason = str(payload.get("reason") or "manual_portal_nomination").strip()
    if nomination_type not in {"archive", "deletion"} or action not in {"nominated", "withdrawn"}:
        raise HTTPException(status_code=422, detail="invalid nomination type or action")
    if not 1 <= len(reason) <= 1000:
        raise HTTPException(status_code=422, detail="nomination reason must contain 1 to 1000 characters")
    environment = os.getenv("CORE_ENVIRONMENT", "acceptance")
    try:
        with db_connect() as conn:
            if not query_one(conn, """
                SELECT to_regclass('public.document_lifecycle_nomination_events') IS NOT NULL AS available
            """)["available"]:
                raise HTTPException(status_code=503, detail="nomination migration is not applied")
            matches = query_all(conn, WORKSET_SELECT + " WHERE w.file_id = %s", (file_id,))
            if not matches:
                raise HTTPException(status_code=409, detail="file is no longer in the document workset")
            row = matches[0]
            latest = query_all(conn, """
                SELECT * FROM public.v_latest_document_lifecycle_nomination
                WHERE file_id = %s AND nomination_type = %s
            """, (file_id, nomination_type))
            previous = latest[0] if latest else None
            if action == "withdrawn" and (not previous or previous["action"] != "nominated"):
                raise HTTPException(status_code=409, detail="there is no active nomination to withdraw")
            policy = query_all(conn, """
                SELECT id, policy_code, policy_version, configuration
                FROM public.v_current_policies
                WHERE policy_code = 'document_retention' AND environment = %s
            """, (environment,))
            if not policy:
                raise HTTPException(status_code=409, detail="no active document retention policy is available")
            policy = policy[0]
            try:
                days = int(policy["configuration"][
                    "archive_review_days" if nomination_type == "archive" else "deletion_review_days"
                ])
            except (KeyError, TypeError, ValueError) as exc:
                raise HTTPException(status_code=409, detail="active retention policy is incomplete") from exc
            if days < 0 or days > 3650:
                raise HTTPException(status_code=409, detail="active retention policy review period is invalid")
            review_at = (
                previous["review_at"] if action == "withdrawn"
                else datetime.now(timezone.utc) + timedelta(days=days)
            )
            privacy = effective_privacy_proposal(row)["classification"]
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO public.document_lifecycle_nomination_events (
                        idempotency_key, file_id, content_group_id, content_sha256,
                        nomination_type, action, reason, policy_id, policy_code,
                        policy_version, policy_snapshot, review_at, workset_status_snapshot,
                        category_snapshot, family_snapshot, privacy_snapshot, nominated_by,
                        supersedes_event_id
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING id, created_at, file_id, nomination_type, action
                """, (
                    idempotency_key, row["file_id"], row["content_group_id"], row["content_sha256"],
                    nomination_type, action, reason, policy["id"], policy["policy_code"],
                    policy["policy_version"], json.dumps(policy["configuration"], ensure_ascii=False),
                    review_at, row["workset_status"], row.get("category"), row.get("document_family"),
                    privacy, os.getenv("CORE_REVIEWER", "hugo"), previous["id"] if previous else None,
                ))
                created = cur.fetchone()
                if not created:
                    cur.execute("""
                        SELECT id, created_at, file_id, nomination_type, action
                        FROM public.document_lifecycle_nomination_events WHERE idempotency_key = %s
                    """, (idempotency_key,))
                    created = cur.fetchone()
                if int(created[2]) != file_id or created[3] != nomination_type or created[4] != action:
                    raise HTTPException(status_code=409, detail="idempotency key belongs to another nomination")
        return {
            "status": "stored", "nomination_id": str(created[0]), "created_at": iso(created[1]),
            "file_id": file_id, "nomination_type": nomination_type, "action": action,
            "review_at": iso(review_at), "policy_version": policy["policy_version"],
            "workset_status_unchanged": True, "archive_status_unchanged": True,
            "file_mutations": False, "model_updates": False,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"nomination unavailable: {type(exc).__name__}") from exc


@app.get("/api/v1/workset/duplicates")
def exact_duplicate_reviews(
    review_state: str = Query("pending", pattern="^(pending|reviewed|all)$"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Expose exact-content groups as review units without mutating storage."""
    state_filter = {
        "pending": " AND (g.latest_review_id IS NULL OR g.latest_review_action = 'withdrawn')",
        "reviewed": " AND g.latest_review_action = 'selected_leader'",
        "all": "",
    }[review_state]
    try:
        with db_connect() as conn:
            available = query_one(conn, """
                SELECT to_regclass('public.v_exact_duplicate_review_groups') IS NOT NULL AS available
            """)["available"]
            if not available:
                raise HTTPException(status_code=503, detail="duplicate review migration is not applied")
            summary = query_one(conn, """
                SELECT count(*) AS total,
                       count(*) FILTER (WHERE latest_review_id IS NULL OR latest_review_action = 'withdrawn') AS pending,
                       count(*) FILTER (WHERE latest_review_action = 'selected_leader') AS reviewed,
                       coalesce(sum(potential_savings_bytes), 0) AS potential_savings_bytes
                FROM public.v_exact_duplicate_review_groups
            """)
            groups = query_all(conn, """
                SELECT g.*, r.review_notes, r.reviewer, r.policy_version,
                       r.redundant_file_ids, r.golden_file_id_snapshot
                FROM public.v_exact_duplicate_review_groups g
                LEFT JOIN public.v_latest_exact_duplicate_review r ON r.id = g.latest_review_id
                WHERE true
            """ + state_filter + """
                ORDER BY g.reviewed_at DESC NULLS LAST, g.potential_savings_bytes DESC,
                         g.content_group_id
                LIMIT %s OFFSET %s
            """, (limit, offset))
            group_ids = [str(group["content_group_id"]) for group in groups]
            members = query_all(conn, """
                SELECT gm.content_group_id, f.id AS file_id, f.filename, f.path,
                       f.size_bytes, f.content_sha256, f.deleted_at,
                       (f.id = cg.golden_file_id) AS is_current_golden,
                       w.workset_status, w.last_qualifying_activity_at,
                       privacy.corrected_privacy_classification AS privacy_classification
                FROM public.content_group_members gm
                JOIN public.content_groups cg ON cg.id = gm.content_group_id
                JOIN public.files f ON f.id = gm.file_id
                LEFT JOIN public.v_active_document_workset w ON w.file_id = f.id
                LEFT JOIN public.v_latest_document_review privacy
                  ON privacy.file_id = f.id AND privacy.review_type = 'privacy_classification'
                WHERE gm.content_group_id = ANY(%s::uuid[])
                ORDER BY gm.content_group_id, (f.id = cg.golden_file_id) DESC,
                         lower(f.path), f.id
            """, (group_ids,)) if group_ids else []
            handoffs = query_all(conn, """
                SELECT review_event_id, redundant_file_id, eligible_for_executor, handoff_reason,
                       quarantine_path
                FROM public.v_exact_duplicate_review_handoff
                WHERE content_group_id = ANY(%s::uuid[])
            """, (group_ids,)) if group_ids else []
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"duplicate review unavailable: {type(exc).__name__}: {exc}") from exc

    members_by_group: dict[str, list[dict[str, Any]]] = {}
    for member in members:
        key = str(member.pop("content_group_id"))
        member["file_id"] = int(member["file_id"])
        member["smb_path"] = smb_path(str(member["path"]))
        members_by_group.setdefault(key, []).append({k: iso(v) for k, v in member.items()})
    handoffs_by_review: dict[str, list[dict[str, Any]]] = {}
    for handoff in handoffs:
        key = str(handoff.pop("review_event_id"))
        handoffs_by_review.setdefault(key, []).append({k: iso(v) for k, v in handoff.items()})
    output = []
    for group in groups:
        group_id = str(group["content_group_id"])
        review_id = str(group["latest_review_id"]) if group.get("latest_review_id") else None
        output.append({
            **{key: iso(value) for key, value in group.items()},
            "content_group_id": group_id,
            "golden_file_id": int(group["golden_file_id"]),
            "selected_file_id": int(group["selected_file_id"]) if group.get("selected_file_id") else None,
            "members": members_by_group.get(group_id, []),
            "handoff": handoffs_by_review.get(review_id or "", []),
        })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "review_state": review_state,
        "summary": {key: int(value) for key, value in summary.items()},
        "groups": output,
        "review_writes_enabled": review_writes_enabled(),
        "safety": {"file_mutations": False, "golden_record_updates": False,
                   "automatic_deletions": False},
    }


@app.post("/api/v1/workset/duplicate-reviews")
def create_exact_duplicate_review(payload: dict[str, Any] = Body(...)):
    """Append one human leader choice and revalidated handoff evidence."""
    if not review_writes_enabled():
        raise HTTPException(status_code=403, detail="interactive reviews are disabled")
    try:
        group_id = str(uuid.UUID(str(payload["content_group_id"])))
        idempotency_key = str(uuid.UUID(str(payload["idempotency_key"])))
        selected_file_id = int(payload["selected_file_id"])
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="valid group, selected file and idempotency key required") from exc
    action = str(payload.get("action") or "selected_leader")
    notes = str(payload.get("review_notes") or "").strip()
    if action not in {"selected_leader", "withdrawn"} or len(notes) > 2000:
        raise HTTPException(status_code=422, detail="invalid duplicate review action or notes")
    environment = os.getenv("CORE_ENVIRONMENT", "acceptance")
    try:
        with db_connect() as conn:
            group_rows = query_all(conn, """
                SELECT id, content_sha256, size_bytes, golden_file_id
                FROM public.content_groups WHERE id = %s FOR SHARE
            """, (group_id,))
            if not group_rows:
                raise HTTPException(status_code=404, detail="content group not found")
            group = group_rows[0]
            members = query_all(conn, """
                SELECT f.id, f.path, f.filename, f.content_sha256, f.size_bytes, f.deleted_at
                FROM public.content_group_members gm
                JOIN public.files f ON f.id = gm.file_id
                WHERE gm.content_group_id = %s AND f.deleted_at IS NULL
                ORDER BY f.id FOR SHARE OF f
            """, (group_id,))
            member_ids = [int(member["id"]) for member in members]
            if len(members) < 2 or selected_file_id not in member_ids:
                raise HTTPException(status_code=409, detail="duplicate membership changed")
            if any(
                member["content_sha256"] != group["content_sha256"]
                or int(member["size_bytes"]) != int(group["size_bytes"])
                for member in members
            ):
                raise HTTPException(status_code=409, detail="duplicate evidence changed")
            previous_rows = query_all(conn, """
                SELECT * FROM public.v_latest_exact_duplicate_review WHERE content_group_id = %s
            """, (group_id,))
            previous = previous_rows[0] if previous_rows else None
            if action == "withdrawn" and (not previous or previous["action"] != "selected_leader"):
                raise HTTPException(status_code=409, detail="there is no active duplicate review to withdraw")
            if action == "withdrawn":
                selected_file_id = int(previous["selected_file_id"])
            redundant_ids = sorted(file_id for file_id in member_ids if file_id != selected_file_id)
            policies = query_all(conn, """
                SELECT id, policy_code, policy_version, configuration
                FROM public.v_current_policies
                WHERE policy_code = 'document_retention' AND environment = %s
            """, (environment,))
            if not policies:
                raise HTTPException(status_code=409, detail="no active document retention policy is available")
            policy = policies[0]
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO public.exact_duplicate_review_events (
                        idempotency_key, content_group_id, content_sha256, size_bytes,
                        action, selected_file_id, golden_file_id_snapshot, redundant_file_ids,
                        review_notes, policy_id, policy_code, policy_version, policy_snapshot,
                        reviewer, supersedes_event_id
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::bigint[],%s,%s,%s,%s,%s::jsonb,%s,%s)
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING id, created_at, content_group_id, selected_file_id, action
                """, (
                    idempotency_key, group_id, group["content_sha256"], group["size_bytes"],
                    action, selected_file_id, group["golden_file_id"], redundant_ids, notes,
                    policy["id"], policy["policy_code"], policy["policy_version"],
                    json.dumps(policy["configuration"], ensure_ascii=False),
                    os.getenv("CORE_REVIEWER", "hugo"), previous["id"] if previous else None,
                ))
                created = cur.fetchone()
                if not created:
                    cur.execute("""
                        SELECT id, created_at, content_group_id, selected_file_id, action
                        FROM public.exact_duplicate_review_events WHERE idempotency_key = %s
                    """, (idempotency_key,))
                    created = cur.fetchone()
                if str(created[2]) != group_id or int(created[3]) != selected_file_id or created[4] != action:
                    raise HTTPException(status_code=409, detail="idempotency key belongs to another duplicate review")
            handoff = query_all(conn, """
                SELECT redundant_file_id, quarantine_path, intended_lifecycle,
                       nomination_reason, eligible_for_executor, handoff_reason
                FROM public.v_exact_duplicate_review_handoff WHERE review_event_id = %s
                ORDER BY redundant_file_id
            """, (created[0],))
        return {
            "status": "stored", "review_event_id": str(created[0]),
            "created_at": iso(created[1]), "content_group_id": group_id,
            "selected_file_id": selected_file_id, "action": action,
            "selected_is_current_golden": selected_file_id == int(group["golden_file_id"]),
            "handoff": [{key: iso(value) for key, value in row.items()} for row in handoff],
            "file_mutations": False, "golden_record_updated": False,
            "retention_events_created": False,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"duplicate review unavailable: {type(exc).__name__}: {exc}") from exc


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
                       batch_id, source_filename, proposed_filename_raw, proposed_filename,
                       filename_normalization_reasons, target_path_conflict, target_path_conflict_details
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
        filename, paths = target_path_reference_data(file_id)
        result = suggest_known_target_path(value, filename=filename, known_paths=paths)
        return {**result, "mode": "advisory_only", "file_mutations": False}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"path suggestion unavailable: {type(exc).__name__}") from exc


@app.get("/api/v1/workset/{file_id}/target-path-preview")
def workset_target_path_preview(
    file_id: int, category: str = Query(..., min_length=1, max_length=80),
    family: str = Query(..., min_length=1, max_length=80),
    filename: Optional[str] = Query(None, max_length=255),
    proposed_target_path: Optional[str] = Query(None, alias="target_path", max_length=500),
):
    """Recalculate a target proposal from unsaved portal selections."""
    try:
        with db_connect() as conn:
            effective_taxonomy = effective_review_taxonomy(conn)
            valid_categories = {item["code"] for item in effective_taxonomy["categories"]}
            valid_families = {item["code"] for item in effective_taxonomy["families"]}
            if category not in valid_categories or family not in valid_families:
                raise HTTPException(status_code=422, detail="invalid category or document family")
            matches = query_all(conn, WORKSET_SELECT + " WHERE w.file_id = %s", (file_id,))
            lifecycle = effective_lifecycle_for_file(conn, matches[0]) if matches else None
        if not matches:
            raise HTTPException(status_code=409, detail="file is no longer a workset candidate")
        row = matches[0]
        preview = propose_target({
            **row, "accepted_category": category,
            "accepted_category_label": next(
                (item["label"] for item in effective_taxonomy["categories"] if item["code"] == category), None
            ),
            "accepted_document_family": family,
            "accepted_document_family_label": next(
                (item["label"] for item in effective_taxonomy["families"] if item["code"] == family), None
            ),
            "accepted_lifecycle": lifecycle.get("restore_lifecycle", lifecycle["effective_lifecycle"]),
        })
        filename_proposal = None
        target_path = preview["suggested_target_path"]
        conflict_details = {"active_file_ids": [], "accepted_review_event_ids": []}
        if proposed_target_path and proposed_target_path.strip():
            target_path = str(normalize_target_path(
                proposed_target_path, filename=str(row["filename"]),
            )["normalized"])
        if filename and filename.strip():
            filename_proposal = normalize_proposed_filename(filename, current_filename=str(row["filename"]))
            target_path = target_with_filename(target_path, str(filename_proposal["normalized"]))
        if (filename and filename.strip()) or (proposed_target_path and proposed_target_path.strip()):
            with db_connect() as conflict_conn:
                conflict_details = target_path_conflicts(conflict_conn, file_id, target_path)
        return {
            "category_code": category, "document_family_code": family,
            "suggested_target_path": target_path,
            "filename_proposal": filename_proposal,
            "target_path_conflict": any(conflict_details.values()),
            "target_path_conflict_details": conflict_details,
            "proposal_confidence": preview["proposal_confidence"],
            "proposal_reason_code": preview["proposal_reason_code"],
            "mode": "live_preview", "database_writes": False, "file_mutations": False,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"target path preview unavailable: {type(exc).__name__}") from exc


def target_path_conflicts(conn, file_id: int, target_path: str) -> dict[str, list[object]]:
    """Read-only collision evidence from current files and accepted human paths."""
    active = query_all(conn, """
        SELECT id FROM public.files
        WHERE id <> %s AND deleted_at IS NULL AND LOWER(path) = LOWER(%s)
        ORDER BY id LIMIT 10
    """, (file_id, target_path))
    reviews = query_all(conn, """
        SELECT id FROM public.document_review_events
        WHERE file_id <> %s AND decision = 'accepted'
          AND LOWER(COALESCE(proposed_target_path, proposal_target_path)) = LOWER(%s)
        ORDER BY created_at DESC, id DESC LIMIT 10
    """, (file_id, target_path))
    return {
        "active_file_ids": [int(item["id"]) for item in active],
        "accepted_review_event_ids": [str(item["id"]) for item in reviews],
    }


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
                       e.batch_id, e.source_filename, e.proposed_filename_raw, e.proposed_filename,
                       e.filename_normalization_reasons, e.target_path_conflict, e.target_path_conflict_details
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
    rows = query_all(conn,
        WORKSET_SELECT + """
            WHERE w.file_id = ANY(%s)
            AND w.workset_status IN ('active', 'inactive', 'needs_review')
        """,
        (file_ids,),
    )
    by_id = {int(row["file_id"]): row for row in rows}
    if set(by_id) != set(file_ids):
        raise HTTPException(status_code=409, detail="one or more files are no longer classifiable workset candidates")
    effective_taxonomy = effective_review_taxonomy(conn)
    valid_categories = {item["code"] for item in effective_taxonomy["categories"]}
    valid_families = {item["code"] for item in effective_taxonomy["families"]}
    category_labels = {item["code"]: item["label"] for item in effective_taxonomy["categories"]}
    family_labels = {item["code"]: item["label"] for item in effective_taxonomy["families"]}
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
        similarity_evidence = validated_similarity_evidence(
            conn, selection.get("similarity_evidence"), category, family,
        )
        original = enrich_workset_row(row)["target_proposal"]
        proposal = propose_target({
            **row, "accepted_category": category, "accepted_document_family": family,
            "accepted_category_label": category_labels.get(category),
            "accepted_document_family_label": family_labels.get(family),
            "accepted_lifecycle": (
                "quarantine" if row.get("physical_location_kind") == "deletion_quarantine"
                else row.get("lifecycle")
            ),
        })
        manual_path = str(selection.get("manual_target_path") or "").strip()
        normalized = normalize_target_path(
            manual_path or proposal["suggested_target_path"], filename=str(row["filename"]),
        )
        privacy_proposal = effective_privacy_proposal(row)
        prepared.append({
            "row": row, "file_id": file_id, "filename": str(row["filename"]),
            "category": category, "family": family, "privacy": privacy,
            "target_path": str(normalized["normalized"]),
            "target_path_raw": manual_path or str(normalized["normalized"]),
            "target_path_input_kind": str(normalized["input_kind"]),
            "original_proposal": original, "privacy_proposal": privacy_proposal,
            "similarity_evidence": similarity_evidence,
        })
    return prepared


def public_bulk_summary(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "file_id": item["file_id"], "filename": item["filename"],
        "target_path": item["target_path"], "privacy": item["privacy"],
    } for item in items]


def relevant_review_examples(document: dict[str, Any], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terms = {term for term in re.split(r"[^a-z0-9]+", str(document["filename"]).casefold()) if len(term) > 2}
    ranked = sorted(
        (item for item in candidates if int(item["file_id"]) != int(document["file_id"])),
        key=lambda item: (-len(terms.intersection({
            term for term in re.split(r"[^a-z0-9]+", str(item["filename"]).casefold()) if len(term) > 2
        })), str(item["created_at"]), int(item["file_id"])),
    )
    return ranked[:3]


def public_ai_proposal(row: dict[str, Any]) -> dict[str, Any]:
    return {key: iso(value) for key, value in row.items() if key != "content_sha256"}


def public_ai_job(row: dict[str, Any]) -> dict[str, Any]:
    return {key: iso(value) for key, value in row.items() if key != "content_sha256"}


@app.get("/api/v1/workset/ai-jobs")
def workset_ai_jobs(status: str = Query("all", pattern="^(all|pending|running|ready|failed|abstained|cancelled)$")):
    where, params = ("", ()) if status == "all" else (" WHERE j.status=%s", (status,))
    try:
        with db_connect() as conn:
            rows = query_all(conn, """
                SELECT j.*, f.filename, p.category_code, p.family_code, p.lifecycle,
                       p.privacy_advice, p.confidence, p.reason, p.relation_kind,
                       p.related_file_ids, p.extraction_metadata,
                       p.created_at AS proposal_created_at,
                       (
                        j.dismissed_at IS NULL
                        AND NOT EXISTS (
                            SELECT 1
                            FROM public.document_review_events e
                            WHERE e.ai_proposal_id=j.proposal_id
                            AND e.decision='accepted'
                        )
                    ) AS awaiting_human_review
                FROM public.workset_ai_jobs j
                JOIN public.files f ON f.id=j.file_id
                LEFT JOIN public.workset_ai_proposals p ON p.id=j.proposal_id
            """ + where + " ORDER BY j.priority DESC,j.requested_at,j.id LIMIT 200", params)
            ready_ids = [int(row["file_id"]) for row in rows if row["status"] == "ready"]
            candidates = query_all(
                conn, WORKSET_SELECT + " WHERE w.file_id=ANY(%s)", (ready_ids,),
            ) if ready_ids else []
            candidates_by_id = {int(item["file_id"]): item for item in candidates}
            for item in rows:
                candidate = candidates_by_id.get(int(item["file_id"]))
                if item["status"] == "ready" and candidate:
                    target = propose_target({
                        **candidate,
                        "accepted_category": item["category_code"],
                        "accepted_document_family": item["family_code"],
                        "accepted_lifecycle": item["lifecycle"],
                    })
                    item["suggested_target_path"] = target["suggested_target_path"]
                    item["suggested_filename"] = candidate["filename"]
            summary_rows = query_all(conn, "SELECT * FROM public.v_workset_ai_job_summary")
            ready_review = query_one(conn, """
                SELECT count(*)::bigint AS count
                FROM public.workset_ai_jobs j
                WHERE j.status='ready' AND NOT EXISTS (
                    SELECT 1 FROM public.document_review_events e
                    WHERE e.ai_proposal_id=j.proposal_id AND e.decision='accepted'
                )
            """)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"AI queue unavailable: {type(exc).__name__}") from exc
    summary = {item: 0 for item in ("pending", "running", "ready", "failed", "abstained", "cancelled")}
    summary.update({str(row["status"]): int(row["job_count"]) for row in summary_rows})
    summary["ready_for_review"] = int(ready_review["count"])
    return {"summary": summary, "jobs": [public_ai_job(row) for row in rows]}


@app.post("/api/v1/workset/ai-jobs")
def create_workset_ai_job(payload: dict[str, Any] = Body(...)):
    if not review_writes_enabled() or not llm_enabled():
        raise HTTPException(status_code=403, detail="local workset AI is disabled")
    try:
        idempotency_key = str(uuid.UUID(str(payload["idempotency_key"])))
        file_id = int(payload["file_id"])
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="valid file ID and idempotency key required") from exc
    model = os.getenv("CORE_LLM_MODEL", "qwen3.6:latest")
    priority_by_status = {"active": 300, "needs_review": 200, "inactive": 100}
    try:
        with db_connect() as conn, conn.cursor() as cur:
            rows = query_all(conn, WORKSET_SELECT + " WHERE w.file_id=%s", (file_id,))
            if not rows:
                raise HTTPException(status_code=409, detail="file is no longer a workset candidate")
            row = rows[0]
            status = effective_lifecycle_for_file(conn, row)["workset_status"]
            cur.execute("""
                INSERT INTO public.workset_ai_jobs
                  (idempotency_key,file_id,content_sha256,workset_status_snapshot,priority,
                   model_id,prompt_version,requested_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING *
            """, (idempotency_key, file_id, row["content_sha256"], status,
                  priority_by_status[status], model, LLM_PROMPT_VERSION,
                  os.getenv("CORE_REVIEWER", "hugo")))
            job = cur.fetchone()
            if job:
                job = dict(zip((column.name for column in cur.description), job))
            if not job:
                cur.execute("SELECT * FROM public.workset_ai_jobs WHERE idempotency_key=%s", (idempotency_key,))
                stored = cur.fetchone()
                job = dict(zip((column.name for column in cur.description), stored)) if stored else None
            if not job:
                raise HTTPException(status_code=503, detail="AI request could not be read after storage")
            if int(job["file_id"]) != file_id:
                raise HTTPException(status_code=409, detail="idempotency key belongs to another request")
    except psycopg2.errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="an AI request for this document is already pending") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"AI queue unavailable: {type(exc).__name__}") from exc
    return {"status": "queued", "job": public_ai_job(job), "file_mutations": False}


@app.get("/api/v1/workset/ocr-jobs")
def workset_ocr_jobs():
    try:
        with db_connect() as conn:
            rows = query_all(conn, """
                SELECT j.*,f.filename
                FROM public.workset_ocr_jobs j JOIN public.files f ON f.id=j.file_id
                ORDER BY j.requested_at DESC,j.id DESC LIMIT 200
            """)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"OCR queue unavailable: {type(exc).__name__}") from exc
    return {"jobs": [{key: iso(value) for key, value in row.items()
                       if key not in {"content_sha256", "artifact_path"}} for row in rows]}


@app.post("/api/v1/workset/ocr-jobs")
def create_workset_ocr_job(payload: dict[str, Any] = Body(...)):
    if not review_writes_enabled():
        raise HTTPException(status_code=403, detail="OCR requests are disabled")
    try:
        file_id = int(payload["file_id"])
        idempotency_key = str(uuid.UUID(str(payload["idempotency_key"])))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="valid file ID and idempotency key required") from exc
    try:
        with db_connect() as conn, conn.cursor() as cur:
            rows = query_all(conn, WORKSET_SELECT + " WHERE w.file_id=%s", (file_id,))
            if not rows:
                raise HTTPException(status_code=409, detail="file is no longer a workset candidate")
            row = rows[0]
            if str(row.get("extension") or "").casefold().lstrip(".") != "pdf":
                raise HTTPException(status_code=409, detail="OCR MVP supports PDF only")
            cur.execute("""
                INSERT INTO public.workset_ocr_jobs
                  (idempotency_key,file_id,content_sha256,priority,requested_by)
                VALUES (%s,%s,%s,%s,%s)
                RETURNING *
            """, (idempotency_key,file_id,row["content_sha256"],
                  300 if row["workset_status"] == "active" else 100,
                  os.getenv("CORE_REVIEWER", "hugo")))
            columns = [column.name for column in cur.description]
            job = dict(zip(columns, cur.fetchone()))
    except psycopg2.errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="OCR is already pending for this content") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"OCR queue unavailable: {type(exc).__name__}") from exc
    return {"status": "queued", "job": {key: iso(value) for key, value in job.items()
                                           if key not in {"content_sha256", "artifact_path"}},
            "file_mutations": False}

@app.post("/api/v1/workset/ai-jobs/{job_id}/dismiss")
def dismiss_workset_ai_job(
    job_id: str,
    payload: dict[str, Any] = Body(...),
):
    try:
        job_uuid = str(uuid.UUID(job_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(
            status_code=422,
            detail="valid AI job ID required",
        ) from exc

    reviewer = str(
        payload.get("dismissed_by")
        or os.getenv("CORE_REVIEWER", "hugo")
    ).strip()[:200]

    try:
        with db_connect() as conn, conn.cursor() as cur:
            cur.execute("""
                UPDATE public.workset_ai_jobs
                SET dismissed_at = now(),
                    dismissed_by = %s,
                    updated_at = now()
                WHERE id = %s
                  AND status = 'ready'
                RETURNING id, file_id, dismissed_at, dismissed_by
            """, (reviewer, job_uuid))

            dismissed = cur.fetchone()

            if not dismissed:
                raise HTTPException(
                    status_code=409,
                    detail="AI proposal is not ready or no longer available",
                )

            dismissed = dict(
                zip(
                    (column.name for column in cur.description),
                    dismissed,
                )
            )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"AI dismiss unavailable: {type(exc).__name__}: {exc}",
        ) from exc

    return {
        "status": "dismissed",
        "job_id": str(dismissed["id"]),
        "file_id": int(dismissed["file_id"]),
        "dismissed_at": iso(dismissed["dismissed_at"]),
        "dismissed_by": dismissed["dismissed_by"],
        "proposal_preserved": True,
    }

@app.post("/api/v1/workset/ai-jobs/{job_id}/accept")
def accept_complete_ai_proposal(job_id: str, payload: dict[str, Any] = Body(...)):
    if not review_writes_enabled():
        raise HTTPException(status_code=403, detail="interactive reviews are disabled")
    try:
        job_uuid = str(uuid.UUID(job_id))
        idempotency_key = uuid.UUID(str(payload["idempotency_key"]))
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="valid job and idempotency key required") from exc
    reviewer = os.getenv("CORE_REVIEWER", "hugo")
    try:
        with db_connect() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT j.*,p.category_code,p.family_code,p.lifecycle,p.privacy_advice,
                       p.confidence,p.reason,p.id AS ai_proposal_id
                FROM public.workset_ai_jobs j JOIN public.workset_ai_proposals p ON p.id=j.proposal_id
                WHERE j.id=%s AND j.status='ready'
            """, (job_uuid,))
            ai = cur.fetchone()

            if ai:
                ai = dict(zip((column.name for column in cur.description), ai))

            if not ai:
                raise HTTPException(
                    status_code=409,
                    detail="AI proposal is not ready",
                )
            rows = query_all(conn, WORKSET_SELECT + " WHERE w.file_id=%s", (ai["file_id"],))
            if not rows or rows[0]["content_sha256"] != ai["content_sha256"]:
                raise HTTPException(status_code=409, detail="AI proposal is stale")
            row = rows[0]
            target = propose_target({**row, "accepted_category": ai["category_code"],
                "accepted_document_family": ai["family_code"], "accepted_lifecycle": ai["lifecycle"]})
            event_ids = []
            for review_type in ("target_path", "privacy_classification", "lifecycle"):
                event_key = str(uuid.uuid5(idempotency_key, review_type))
                cur.execute("""
                    INSERT INTO public.document_review_events (
                      idempotency_key,review_contract_version,channel,review_type,file_id,
                      content_group_id,content_sha256,proposal_category_code,
                      proposal_document_family_code,proposal_lifecycle,proposal_target_path,
                      proposal_confidence,proposal_reason_code,decision,
                      corrected_document_family_code,corrected_category_code,
                      proposal_privacy_classification,corrected_privacy_classification,
                      privacy_rule_version,corrected_lifecycle,reviewer,ai_proposal_id)
                    VALUES (%s,'scrum-106-complete-ai-proposal-v1','workset_portal',%s,%s,%s,%s,
                            %s,%s,%s,%s,%s,'human_accepted_complete_ai_proposal','accepted',
                            %s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (idempotency_key) DO NOTHING RETURNING id
                """, (event_key, review_type, row["file_id"], row["content_group_id"],
                      row["content_sha256"], ai["category_code"], ai["family_code"],
                      ai["lifecycle"], target["suggested_target_path"], ai["confidence"],
                      ai["family_code"] if review_type == "target_path" else None,
                      ai["category_code"] if review_type == "target_path" else None,
                      ai["privacy_advice"] if review_type == "privacy_classification" else None,
                      ai["privacy_advice"] if review_type == "privacy_classification" else None,
                      "scrum-106-human-accepted-ai-v1" if review_type == "privacy_classification" else None,
                      ai["lifecycle"] if review_type == "lifecycle" else None,
                      reviewer, ai["ai_proposal_id"]))
                created = cur.fetchone()
                if created:
                    created = dict(zip((column.name for column in cur.description), created))
                    event_ids.append(str(created["id"]))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"AI acceptance unavailable: {type(exc).__name__}: {exc}"
        ) from exc
    return {"status": "accepted", "job_id": job_uuid, "review_event_ids": event_ids,
            "human_confirmation": True, "file_mutations": False, "model_updates": False}


@app.post("/api/v1/workset/ai-runs")
def create_workset_ai_run(payload: dict[str, Any] = Body(...)):
    if not review_writes_enabled() or not llm_enabled():
        raise HTTPException(status_code=403, detail="local workset AI is disabled")
    try:
        idempotency_key = str(uuid.UUID(str(payload["idempotency_key"])))
        file_ids = [int(value) for value in payload["file_ids"]]
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="valid idempotency key and file IDs required") from exc
    if not 1 <= len(file_ids) <= LLM_MAX_DOCUMENTS or len(set(file_ids)) != len(file_ids):
        raise HTTPException(status_code=422, detail="select between 1 and 5 unique documents")
    filters = payload.get("filter_snapshot") or {}
    if not isinstance(filters, dict) or len(json.dumps(filters)) > 4000:
        raise HTTPException(status_code=422, detail="invalid filter snapshot")
    endpoint = os.getenv("CORE_LLM_ENDPOINT", "http://127.0.0.1:11434/v1")
    model = os.getenv("CORE_LLM_MODEL", "qwen3.6:latest")
    try:
        provider = OpenAICompatibleLocalProvider(
            endpoint, timeout_seconds=int(os.getenv("CORE_LLM_TIMEOUT_SECONDS", "600")),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=f"invalid local LLM configuration: {exc}") from exc
    prompt = json.loads((Path(__file__).parents[1] / "project/prompts/scrum-101-workset-llm-v2.json").read_text("utf-8"))
    try:
        with db_connect() as conn:
            if not query_one(conn, "SELECT to_regclass('public.workset_ai_runs') IS NOT NULL AS available")["available"]:
                raise HTTPException(status_code=503, detail="workset AI migration is not applied")
            existing = query_all(conn, "SELECT id, created_at FROM public.workset_ai_runs WHERE idempotency_key=%s", (idempotency_key,))
            if existing:
                proposals = query_all(conn, "SELECT * FROM public.workset_ai_proposals WHERE run_id=%s ORDER BY file_id", (existing[0]["id"],))
                return {"status": "already_stored", "run_id": str(existing[0]["id"]),
                        "created_at": iso(existing[0]["created_at"]),
                        "proposals": [public_ai_proposal(item) for item in proposals],
                        "file_mutations": False, "model_updates": False}
            rows = query_all(
                conn,
                WORKSET_SELECT + """
                    WHERE w.file_id=ANY(%s)
                    AND w.workset_status IN ('active', 'inactive')
                """,
                (file_ids,),
            )
            if {int(row["file_id"]) for row in rows} != set(file_ids):
                raise HTTPException(status_code=409, detail="one or more files are no longer classifiable workset candidates")
            examples = query_all(conn, """
                SELECT e.id AS review_id,e.file_id,f.filename,e.corrected_category_code AS category_code,
                       e.corrected_document_family_code AS family_code,e.created_at
                FROM public.document_review_events e JOIN public.files f ON f.id=e.file_id
                WHERE e.review_type='target_path' AND e.decision='accepted'
                  AND e.corrected_category_code IS NOT NULL AND e.corrected_document_family_code IS NOT NULL
                ORDER BY e.created_at DESC LIMIT 100
            """)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"AI selection unavailable: {type(exc).__name__}") from exc
    started, results = time.monotonic(), []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for row in sorted(rows, key=lambda item: file_ids.index(int(item["file_id"]))):
        selected_examples = relevant_review_examples(row, examples)
        try:
            context = extract_bounded_context(str(row["path"]))
            if context["status"] != "ready":
                proposal = llm_abstention(int(row["file_id"]), context["reason"])
            else:
                system, user = build_llm_prompt({**row, "core_category": row.get("category"),
                    "core_family": row.get("document_family")}, context, selected_examples, prompt["system_prompt"])
                generated = provider.generate(GenerationRequest(model, system, user))
                proposal = validate_llm_proposal(generated["content"], int(row["file_id"]))
                for key in usage:
                    usage[key] += int(generated.get("usage", {}).get(key) or 0)
        except Exception as exc:
            context = {"status": "error", "reason": type(exc).__name__, "text": ""}
            proposal = llm_abstention(int(row["file_id"]), f"local_processing_error:{type(exc).__name__}")
        results.append({**proposal, "filename": str(row["filename"]),
            "content_sha256": str(row["content_sha256"]),
            "example_review_ids": [str(item["review_id"]) for item in selected_examples],
            "extraction_metadata": {key: value for key, value in context.items() if key != "text"}})
    run_status = "completed_with_errors" if any(item["status"] == "abstained" for item in results) else "completed"
    duration = round(time.monotonic() - started, 3)
    try:
        with db_connect() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO public.workset_ai_runs
                (idempotency_key,channel,status,selected_file_ids,selection_snapshot,provider_id,model_id,
                 prompt_version,schema_version,document_count,proposal_count,error_count,prompt_tokens,
                 completion_tokens,total_tokens,duration_seconds)
                VALUES (%s,'workset_portal',%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id,created_at""", (idempotency_key,run_status,file_ids,
                json.dumps({"file_ids": file_ids,"filters": filters},ensure_ascii=False),provider.provider_id,
                model,LLM_PROMPT_VERSION,LLM_SCHEMA_VERSION,len(results),sum(x["status"]=="ready" for x in results),
                sum(x["status"]=="abstained" for x in results),usage["prompt_tokens"],usage["completion_tokens"],
                usage["total_tokens"],duration))
            run_id, created_at = cur.fetchone()
            for item in results:
                cur.execute("""INSERT INTO public.workset_ai_proposals
                    (run_id,file_id,content_sha256,status,category_code,family_code,lifecycle,privacy_advice,
                     confidence,relation_kind,related_file_ids,reason,example_review_ids,extraction_metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::bigint[],%s,%s::uuid[],%s::jsonb) RETURNING id""",
                    (run_id,item["file_id"],item["content_sha256"],item["status"],item["category_code"],
                     item["family_code"],item["lifecycle"],item["privacy_advice"],item["confidence"],
                     item["relation_kind"],item["related_file_ids"],item["reason"],item["example_review_ids"],
                     json.dumps(item["extraction_metadata"],ensure_ascii=False)))
                item["id"] = str(cur.fetchone()[0])
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"AI proposal storage unavailable: {type(exc).__name__}") from exc
    return {"status":run_status,"run_id":str(run_id),"created_at":iso(created_at),"model_id":model,
            "prompt_version":LLM_PROMPT_VERSION,"document_count":len(results),
            "proposals":[public_ai_proposal(item) for item in results],"raw_text_stored":False,
            "file_mutations":False,"model_updates":False}


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
                            target_path_input_kind, target_path_suggestion_decision, batch_id,
                            proposal_evidence
                        ) VALUES (%s,%s,'workset_portal','target_path',%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                  'accepted',%s,%s,%s,%s,%s,%s,%s,'no_suggestion',%s,%s::jsonb)
                        ON CONFLICT (idempotency_key) DO NOTHING
                    """, (
                        target_key, CONTRACT_VERSION, item["file_id"], row["content_group_id"],
                        row["content_sha256"], original["category_code"],
                        original["document_family_code"], original["zone_code"],
                        original["suggested_target_path"], original["proposal_confidence"],
                        original["proposal_reason_code"], item["family"], item["category"], reviewer,
                        supersedes.get("target_path"), item["target_path"], item["target_path_raw"],
                        item["target_path_input_kind"], batch_id,
                        json.dumps(item["similarity_evidence"], ensure_ascii=False),
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
        invalidate_target_path_reference_cache()
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
    if review_type not in {"target_path", "privacy_classification", "lifecycle"}:
        raise HTTPException(status_code=422, detail="invalid review type")
    privacy_classification = str(payload.get("privacy_classification") or "") or None
    if review_type == "privacy_classification" and privacy_classification not in {"low", "medium", "high"}:
        raise HTTPException(status_code=422, detail="invalid privacy classification")
    corrected_lifecycle = str(payload.get("corrected_lifecycle") or "") or None
    if review_type == "lifecycle" and corrected_lifecycle not in {"active", "archive", "needs_review"}:
        raise HTTPException(status_code=422, detail="invalid lifecycle decision")
    active_months = payload.get("active_months")
    if active_months in (None, ""):
        active_months = None
    else:
        try:
            active_months = int(active_months)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="active months must be a whole number") from exc
        if corrected_lifecycle != "active" or not 1 <= active_months <= 120:
            raise HTTPException(status_code=422, detail="active months must be 1 through 120 for an active decision")
    family = str(payload.get("corrected_document_family_code") or "") or None
    category = str(payload.get("corrected_category_code") or "") or None
    notes = str(payload.get("review_notes") or "") or None
    proposed_category = str(payload.get("proposed_category_label") or "").strip() or None
    proposed_family = str(payload.get("proposed_family_label") or "").strip() or None
    proposed_path_input = str(payload.get("proposed_target_path") or "").strip() or None
    proposed_path_raw = str(payload.get("proposed_target_path_original") or "").strip() or proposed_path_input
    raw_similarity_evidence = payload.get("similarity_evidence")
    ai_proposal_id = str(payload.get("ai_proposal_id") or "").strip() or None
    path_suggestion = str(payload.get("target_path_suggestion") or "").strip() or None
    path_suggestion_decision = str(payload.get("target_path_suggestion_decision") or "no_suggestion")
    proposed_filename_raw = str(payload.get("proposed_filename") or "").strip() or None
    if path_suggestion_decision not in {"accepted", "dismissed", "new_path", "no_suggestion"}:
        raise HTTPException(status_code=422, detail="invalid target path suggestion decision")
    normalized_path = None
    proposed_path = None
    if family and not re.fullmatch(r"[a-z0-9_'-]{1,80}", family):
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
            if review_type == "target_path":
                base_taxonomy = taxonomy()
                effective_taxonomy = base_taxonomy
                valid_categories = {item["code"] for item in base_taxonomy["categories"]}
                valid_families = {item["code"] for item in base_taxonomy["families"]}
                if category not in valid_categories or family not in valid_families:
                    effective_taxonomy = effective_review_taxonomy(conn)
                    valid_categories = {item["code"] for item in effective_taxonomy["categories"]}
                    valid_families = {item["code"] for item in effective_taxonomy["families"]}
                if decision == "accepted":
                    if category not in valid_categories:
                        raise HTTPException(status_code=422, detail="invalid category code")
                    if family not in valid_families:
                        raise HTTPException(status_code=422, detail="invalid document family code")
                else:
                    if category is not None and category not in valid_categories:
                        raise HTTPException(status_code=422, detail="invalid category code")
                    if family is not None and family not in valid_families:
                        raise HTTPException(status_code=422, detail="invalid document family code")
            matches = query_all(
                conn, WORKSET_SELECT + " WHERE w.file_id = %s", (file_id,),
            )
            if not matches:
                raise HTTPException(status_code=409, detail="file is no longer a workset candidate")
            row = matches[0]
            if (
                review_type == "target_path"
                and row.get("physical_location_kind") == "deletion_quarantine"
                and proposed_path_input
                and proposed_path_input.casefold().startswith(
                    "/volume1/data/persoonlijk/quarantaine/"
                )
            ):
                raise HTTPException(
                    status_code=422,
                    detail="quarantine is the current physical location, not a classification target",
                )
            filename_proposal = None
            if proposed_filename_raw:
                if review_type != "target_path":
                    raise HTTPException(status_code=422, detail="filename proposals require a target-path review")
                try:
                    filename_proposal = normalize_proposed_filename(
                        proposed_filename_raw, current_filename=str(row["filename"]),
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
            if ai_proposal_id:
                try:
                    ai_proposal_id = str(uuid.UUID(ai_proposal_id))
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail="invalid AI proposal id") from exc
                ai_match = query_all(conn, """
                    SELECT id FROM public.v_latest_workset_ai_proposal
                    WHERE id=%s AND file_id=%s
                """, (ai_proposal_id, file_id))
                if review_type != "target_path" or not ai_match:
                    raise HTTPException(status_code=409, detail="AI proposal is stale")
            similarity_evidence = validated_similarity_evidence(
                conn, raw_similarity_evidence, category, family,
            ) if review_type == "target_path" else {}
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
                privacy = effective_privacy_proposal(row)
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
            if review_type == "lifecycle":
                calculated = {
                    "active": "active", "inactive": "archive", "needs_review": "needs_review",
                }.get(str(row.get("workset_status")), "needs_review")
                active_until = (
                    datetime.now(timezone.utc) + timedelta(days=30 * active_months)
                    if active_months else None
                )
                latest = query_all(
                    conn,
                    "SELECT id FROM public.v_latest_document_review WHERE file_id = %s AND review_type = 'lifecycle'",
                    (file_id,),
                )
                supersedes_event_id = latest[0]["id"] if latest else None
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO public.document_review_events (
                            idempotency_key, review_contract_version, channel, review_type,
                            file_id, content_group_id, content_sha256,
                            proposal_lifecycle, proposal_confidence, proposal_reason_code,
                            decision, corrected_lifecycle, lifecycle_active_until,
                            review_notes, reviewer, supersedes_event_id
                        ) VALUES (%s,'document-lifecycle-review-v1','workset_portal','lifecycle',
                                  %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (idempotency_key) DO NOTHING
                        RETURNING id, created_at, file_id, decision
                    """, (
                        idempotency_key, row["file_id"], row["content_group_id"],
                        row["content_sha256"], calculated, row.get("activity_confidence") or "low",
                        row.get("reason_code") or "manual_lifecycle_review", decision,
                        corrected_lifecycle, active_until, notes,
                        os.getenv("CORE_REVIEWER", "hugo"), supersedes_event_id,
                    ))
                    created = cur.fetchone()
                    if not created:
                        cur.execute(
                            "SELECT id, created_at, file_id, decision FROM public.document_review_events WHERE idempotency_key = %s",
                            (idempotency_key,),
                        )
                        created = cur.fetchone()
                return {
                    "status": "stored", "review_id": str(created[0]), "created_at": iso(created[1]),
                    "review_type": review_type, "decision": decision,
                    "corrected_lifecycle": corrected_lifecycle,
                    "lifecycle_active_until": iso(active_until),
                    "learning_evidence": True, "workset_status_unchanged": True,
                    "file_mutations": False, "model_updates": False,
                }
            effective_lifecycle = effective_lifecycle_for_file(conn, row)
            proposal_row = {
                **row,
                "latest_corrected_lifecycle": effective_lifecycle.get(
                    "restore_lifecycle", effective_lifecycle["effective_lifecycle"]
                ),
                "latest_lifecycle_active_until": None,
            }
            proposal = enrich_workset_row(proposal_row).get("target_proposal")
            if not proposal:
                raise HTTPException(status_code=409, detail="file is no longer an active workset candidate")
            selected_proposal = propose_target({
                **row, "accepted_category": category,
                "accepted_category_label": next(
                    (item["label"] for item in effective_taxonomy["categories"] if item["code"] == category), category,
                ),
                "accepted_document_family": family,
                "accepted_document_family_label": next(
                    (item["label"] for item in effective_taxonomy["families"] if item["code"] == family), family,
                ),
                "accepted_lifecycle": effective_lifecycle.get(
                    "restore_lifecycle", effective_lifecycle["effective_lifecycle"]
                ),
            })
            if filename_proposal:
                base_target = proposed_path or selected_proposal["suggested_target_path"]
                proposed_path = target_with_filename(base_target, str(filename_proposal["normalized"]))
                if not proposed_path_raw:
                    proposed_path_raw = proposed_path
            conflict_details = target_path_conflicts(conn, file_id, proposed_path) if filename_proposal and proposed_path else {
                "active_file_ids": [], "accepted_review_event_ids": [],
            }
            has_target_conflict = any(conflict_details.values())
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
                        target_path_suggestion, target_path_suggestion_decision, proposal_evidence,
                        ai_proposal_id, source_filename, proposed_filename_raw, proposed_filename,
                        filename_normalization_reasons, target_path_conflict, target_path_conflict_details
                    ) VALUES (%s,%s,'workset_portal','target_path',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb)
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
                    json.dumps(similarity_evidence, ensure_ascii=False),
                    ai_proposal_id,
                    str(row["filename"]) if filename_proposal else None,
                    proposed_filename_raw,
                    str(filename_proposal["normalized"]) if filename_proposal else None,
                    json.dumps(filename_proposal["reason_codes"] if filename_proposal else []),
                    has_target_conflict if filename_proposal else None,
                    json.dumps(conflict_details if filename_proposal else {}),
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
                "accepted_lifecycle": effective_lifecycle["effective_lifecycle"],
            })
        invalidate_target_path_reference_cache()
        return {
            "status": "stored", "review_id": str(created[0]), "created_at": iso(created[1]),
            "decision": decision, "corrected_document_family_code": family,
            "corrected_category_code": category,
            "proposed_category_label": proposed_category,
            "proposed_family_label": proposed_family,
            "proposed_target_path": proposed_path,
            "proposed_target_path_raw": proposed_path_raw,
            "source_filename": str(row["filename"]) if filename_proposal else None,
            "proposed_filename_raw": proposed_filename_raw,
            "proposed_filename": filename_proposal["normalized"] if filename_proposal else None,
            "filename_normalization_reasons": filename_proposal["reason_codes"] if filename_proposal else [],
            "target_path_conflict": has_target_conflict if filename_proposal else False,
            "target_path_conflict_details": conflict_details if filename_proposal else {},
            "target_path_input_kind": normalized_path["input_kind"] if normalized_path else None,
            "target_path_suggestion": path_suggestion,
            "target_path_suggestion_decision": path_suggestion_decision,
            "target_path_normalized": bool(normalized_path and normalized_path["changed"]),
            "similarity_evidence_stored": bool(similarity_evidence),
            "ai_proposal_id": ai_proposal_id,
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
