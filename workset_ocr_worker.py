"""Resource-aware, single-job OCR worker; never modifies source documents."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
import redis
from core.runtime.capacity import worker_resources as host_resources

from core.integrity.ocr_duplicate_similarity import (
    ANALYZER_VERSION, compare_ocr_artifacts, group_key, metadata_json,
)


POLL_SECONDS = int(os.getenv("CORE_OCR_POLL_SECONDS", "10"))
CPU_LIMIT_PERCENT = float(os.getenv("CORE_OCR_MAX_CPU_PERCENT", "60"))
MIN_AVAILABLE_MIB = int(os.getenv("CORE_OCR_MIN_AVAILABLE_MIB", "2048"))
MAX_STREAM_LAG = int(os.getenv("CORE_OCR_MAX_STREAM_LAG", "1000"))
MAX_PAGES = int(os.getenv("CORE_OCR_MAX_PAGES", "100"))
LANGUAGES = os.getenv("CORE_OCR_LANGUAGES", "nld+eng")
OUTPUT_ROOT = Path(os.getenv("CORE_OCR_OUTPUT_ROOT", "/volume1/docker/core-runtime/ocr"))
MAX_ACTIVE_DB_SESSIONS = max(1, int(os.getenv("CORE_OCR_MAX_ACTIVE_DB_SESSIONS", "4")))
MAINTENANCE_MODE = os.getenv("CORE_MAINTENANCE_MODE", "false").lower() == "true"


def db_connect():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"), port=os.getenv("DB_PORT", "5432"),
        user=os.environ["DB_USER"], password=os.environ["DB_PASS"],
        dbname=os.environ["DB_NAME"], cursor_factory=psycopg2.extras.RealDictCursor,
    )




def stream_lag(client: redis.Redis) -> int:
    total = 0
    for stream in ("scan_stream", "scan_stream_realtime"):
        try:
            total += sum(int(group.get("lag") or 0) for group in client.xinfo_groups(stream))
        except redis.ResponseError:
            continue
    return total


def service_gate(client: redis.Redis) -> str | None:
    if MAINTENANCE_MODE:
        return "maintenance_mode"
    try:
        if not client.ping():
            return "redis_unavailable"
    except Exception:
        return "redis_unavailable"
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT
            count(*) FILTER (WHERE state='active' AND pid<>pg_backend_pid()) AS active_sessions,
            EXISTS (
                SELECT 1 FROM public.v_controlled_execution_batch_progress
                WHERE batch_status IN ('approved','queued','started','rollback_pending')
            ) AS controlled_execution_active
            FROM pg_stat_activity WHERE datname=current_database()
        """)
        pressure = cur.fetchone()
    if pressure["controlled_execution_active"]:
        return "controlled_execution_priority"
    if int(pressure["active_sessions"] or 0) > MAX_ACTIVE_DB_SESSIONS:
        return "postgres_busy"
    return None


def claim_job() -> dict[str, Any] | None:
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT j.*, COALESCE(location.current_path,f.path) AS path,
                   f.extension, f.content_sha256 AS current_content_sha256
            FROM public.workset_ocr_jobs j JOIN public.files f ON f.id=j.file_id
            LEFT JOIN public.v_workset_current_physical_location location ON location.file_id=f.id
            WHERE j.status='pending' AND f.deleted_at IS NULL
            ORDER BY j.priority DESC,j.requested_at,j.id
            FOR UPDATE SKIP LOCKED LIMIT 1
        """)
        job = cur.fetchone()
        if not job:
            return None
        cur.execute("""
            UPDATE public.workset_ocr_jobs
            SET status='running',waiting_reason=NULL,started_at=now(),finished_at=NULL,
                attempt_count=attempt_count+1,updated_at=now() WHERE id=%s
        """, (job["id"],))
        return dict(job)


def set_waiting_reason(reason: str | None) -> None:
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE public.workset_ocr_jobs SET waiting_reason=%s,updated_at=now()
            WHERE status='pending' AND waiting_reason IS DISTINCT FROM %s
        """, (reason, reason))


def recognize_pdf(path: Path) -> tuple[str, int, str]:
    from core.finance.privacy import deny_generic_access
    deny_generic_access(path)
    if path.suffix.casefold() != ".pdf":
        raise ValueError("unsupported_extension")
    with tempfile.TemporaryDirectory(prefix="core-ocr-") as directory:
        prefix = Path(directory) / "page"
        subprocess.run(
            ["pdftoppm", "-r", "200", "-png", "-f", "1", "-l", str(MAX_PAGES), str(path), str(prefix)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        images = sorted(Path(directory).glob("page-*.png"))
        if not images:
            raise ValueError("pdf_has_no_renderable_pages")
        pages = []
        for image in images:
            completed = subprocess.run(
                ["tesseract", str(image), "stdout", "-l", LANGUAGES],
                check=True, capture_output=True, text=True,
            )
            pages.append(completed.stdout.strip())
        text = "\n\n".join(value for value in pages if value).strip()
        if not text:
            raise ValueError("ocr_produced_no_text")
        version = subprocess.run(
            ["tesseract", "--version"], check=True, capture_output=True, text=True,
        ).stdout.splitlines()[0]
        return text, len(images), version


def persist_artifact(content_sha256: str, text: str) -> tuple[Path, str]:
    if len(content_sha256) != 64 or any(character not in "0123456789abcdef" for character in content_sha256):
        raise ValueError("invalid_content_sha256")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT_ROOT / f"{content_sha256}.txt.gz"
    temporary = target.with_suffix(".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8") as handle:
        handle.write(text)
    temporary.replace(target)
    return target, hashlib.sha256(text.encode("utf-8")).hexdigest()


def process_job(job: dict[str, Any]) -> None:
    if str(job["current_content_sha256"]) != str(job["content_sha256"]):
        with db_connect() as conn, conn.cursor() as cur:
            cur.execute("""
                UPDATE public.workset_ocr_jobs SET status='cancelled',error_code='stale_file',
                    finished_at=now(),updated_at=now() WHERE id=%s
            """, (job["id"],))
        return
    path = Path(str(job["path"]))
    text, pages, engine_version = recognize_pdf(path)
    artifact, text_sha256 = persist_artifact(str(job["content_sha256"]), text)
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE public.workset_ocr_jobs
            SET status='ready',engine_version=%s,pages=%s,characters=%s,text_sha256=%s,
                artifact_path=%s,finished_at=now(),updated_at=now() WHERE id=%s
        """, (engine_version, pages, len(text), text_sha256, str(artifact), job["id"]))


def discover_ocr_near_duplicates(limit: int = 3) -> int:
    """Compare a bounded number of same-identity PDFs with ready OCR evidence."""
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute("""
          WITH ready AS (
            SELECT DISTINCT ON (j.file_id)
              j.file_id,j.content_sha256,j.artifact_path,j.pages,j.characters,
              f.filename,public.core_normalized_document_identity(f.filename) AS identity
            FROM public.workset_ocr_jobs j
            JOIN public.files f ON f.id=j.file_id
            WHERE j.status='ready' AND f.deleted_at IS NULL
              AND lower(coalesce(f.extension,''))='pdf'
              AND f.content_sha256=j.content_sha256
              AND j.artifact_path IS NOT NULL
            ORDER BY j.file_id,j.finished_at DESC,j.id DESC
          )
          SELECT l.file_id AS left_file_id,l.content_sha256 AS left_hash,
                 l.artifact_path AS left_artifact,l.pages AS left_pages,
                 l.characters AS left_characters,l.filename AS left_filename,
                 r.file_id AS right_file_id,r.content_sha256 AS right_hash,
                 r.artifact_path AS right_artifact,r.pages AS right_pages,
                 r.characters AS right_characters,r.filename AS right_filename,
                 l.identity
          FROM ready l JOIN ready r ON r.identity=l.identity AND r.file_id>l.file_id
          WHERE l.identity<>'' AND l.content_sha256<>r.content_sha256
            AND NOT EXISTS (
              SELECT 1 FROM public.ocr_similarity_comparisons c
              WHERE c.left_file_id=l.file_id AND c.right_file_id=r.file_id
                AND c.left_content_sha256=l.content_sha256
                AND c.right_content_sha256=r.content_sha256
                AND c.analyzer_version=%s
            )
          ORDER BY l.file_id,r.file_id LIMIT %s
        """, (ANALYZER_VERSION, limit))
        pairs = list(cur.fetchall())
        inserted = 0
        for pair in pairs:
            metrics = compare_ocr_artifacts(
                Path(str(pair["left_artifact"])), Path(str(pair["right_artifact"])),
            )
            cur.execute("""
              INSERT INTO public.ocr_similarity_comparisons (
                left_file_id,right_file_id,left_content_sha256,right_content_sha256,
                normalized_identity,qualifies,metrics,analyzer_version
              ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
              ON CONFLICT (left_file_id,right_file_id,left_content_sha256,
                           right_content_sha256,analyzer_version) DO NOTHING
            """, (pair["left_file_id"], pair["right_file_id"], pair["left_hash"],
                  pair["right_hash"], pair["identity"], metrics["qualifies"],
                  json.dumps(metrics), ANALYZER_VERSION))
            if not metrics["qualifies"]:
                continue
            key = group_key(str(pair["identity"]), str(pair["left_hash"]), str(pair["right_hash"]))
            for side, peer in (("left", "right"), ("right", "left")):
                signature = "signed" in str(pair[f"{side}_filename"]).casefold()
                cur.execute("""
                  INSERT INTO public.pdf_content_similarity_evidence (
                    file_id,content_sha256,normalized_text_sha256,page_text_sha256,page_count,
                    normalized_text_characters,metadata_snapshot,pdf_document_id,
                    signature_present,extraction_warnings,analyzer_version
                  ) VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb,'[]'::jsonb,%s,'[]'::jsonb,%s)
                  ON CONFLICT (file_id,content_sha256,analyzer_version) DO NOTHING
                """, (pair[f"{side}_file_id"], pair[f"{side}_hash"], key,
                      json.dumps([key]), max(1, int(pair[f"{side}_pages"] or 1)),
                      max(1, int(pair[f"{side}_characters"] or 1)),
                      metadata_json(str(pair["identity"]), int(pair[f"{peer}_file_id"]), metrics),
                      signature, ANALYZER_VERSION))
                inserted += cur.rowcount
        return inserted


def fail(job: dict[str, Any], exc: Exception) -> None:
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE public.workset_ocr_jobs SET status='failed',error_code=%s,
                finished_at=now(),updated_at=now() WHERE id=%s
        """, (str(exc)[:120] or type(exc).__name__, job["id"]))


def main() -> int:
    client = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), decode_responses=True)
    while True:
        try:
            reason = service_gate(client)
            resources=host_resources()
            if reason is None and not resources.get("capacity_available",1):
                reason="capacity_unavailable"
            if reason is None and resources["cpu_load_percent"] > CPU_LIMIT_PERCENT:
                reason = "waiting_for_cpu"
            elif reason is None and resources["available_memory_mib"] < MIN_AVAILABLE_MIB:
                reason = "waiting_for_memory"
            elif reason is None and stream_lag(client) > MAX_STREAM_LAG:
                reason = "core_pipeline_priority"
            client.set("workset_ocr_worker:heartbeat", datetime.now(timezone.utc).isoformat(), ex=90)
            client.set("workset_ocr_worker:heartbeat:status", reason or "idle", ex=90)
            set_waiting_reason(reason)
            if reason:
                time.sleep(POLL_SECONDS)
                continue
            job = claim_job()
            if not job:
                discover_ocr_near_duplicates()
                time.sleep(POLL_SECONDS)
                continue
            try:
                client.set("workset_ocr_worker:heartbeat:status", "processing", ex=90)
                process_job(job)
            except Exception as exc:
                fail(job, exc)
        except Exception:
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
