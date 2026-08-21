"""Resource-aware, single-job OCR worker; never modifies source documents."""

from __future__ import annotations

import gzip
import hashlib
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


POLL_SECONDS = int(os.getenv("CORE_OCR_POLL_SECONDS", "10"))
CPU_LIMIT_PERCENT = float(os.getenv("CORE_OCR_MAX_CPU_PERCENT", "60"))
MIN_AVAILABLE_MIB = int(os.getenv("CORE_OCR_MIN_AVAILABLE_MIB", "2048"))
MAX_STREAM_LAG = int(os.getenv("CORE_OCR_MAX_STREAM_LAG", "1000"))
MAX_PAGES = int(os.getenv("CORE_OCR_MAX_PAGES", "100"))
LANGUAGES = os.getenv("CORE_OCR_LANGUAGES", "nld+eng")
OUTPUT_ROOT = Path(os.getenv("CORE_OCR_OUTPUT_ROOT", "/volume1/docker/core-runtime/ocr"))


def db_connect():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"), port=os.getenv("DB_PORT", "5432"),
        user=os.environ["DB_USER"], password=os.environ["DB_PASS"],
        dbname=os.environ["DB_NAME"], cursor_factory=psycopg2.extras.RealDictCursor,
    )


def available_memory_mib(proc_root: Path = Path("/host/proc")) -> float:
    values = {}
    for line in (proc_root / "meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        values[key] = int(value.strip().split()[0])
    available = values.get("MemAvailable")
    if available is None:
        available = sum(values.get(key, 0) for key in ("MemFree", "Buffers", "Cached", "SReclaimable"))
    return round(available / 1024, 1)


def cpu_load_percent(proc_root: Path = Path("/host/proc")) -> float:
    load_1m = float((proc_root / "loadavg").read_text().split()[0])
    cpu_count = max(1, sum(
        line.startswith("processor")
        for line in (proc_root / "cpuinfo").read_text().splitlines()
    ))
    return round(load_1m / cpu_count * 100, 2)


def stream_lag(client: redis.Redis) -> int:
    total = 0
    for stream in ("scan_stream", "scan_stream_realtime"):
        try:
            total += sum(int(group.get("lag") or 0) for group in client.xinfo_groups(stream))
        except redis.ResponseError:
            continue
    return total


def claim_job() -> dict[str, Any] | None:
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT j.*, f.path, f.extension, f.content_sha256 AS current_content_sha256
            FROM public.workset_ocr_jobs j JOIN public.files f ON f.id=j.file_id
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
            reason = None
            if cpu_load_percent() > CPU_LIMIT_PERCENT:
                reason = "waiting_for_cpu"
            elif available_memory_mib() < MIN_AVAILABLE_MIB:
                reason = "waiting_for_memory"
            elif stream_lag(client) > MAX_STREAM_LAG:
                reason = "core_pipeline_priority"
            client.set("workset_ocr_worker:heartbeat", datetime.now(timezone.utc).isoformat(), ex=90)
            set_waiting_reason(reason)
            if reason:
                time.sleep(POLL_SECONDS)
                continue
            job = claim_job()
            if not job:
                time.sleep(POLL_SECONDS)
                continue
            try:
                process_job(job)
            except Exception as exc:
                fail(job, exc)
        except Exception:
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
