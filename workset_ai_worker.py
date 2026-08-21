"""SCRUM-106 resource-aware worker for individual, local workset AI jobs."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
import redis

from core.semantic.rag import GenerationRequest, OpenAICompatibleLocalProvider
from core.semantic.workset_llm import (
    PROMPT_VERSION, SCHEMA_VERSION, abstention, build_prompt,
    extract_bounded_context, validate_proposal,
)


POLL_SECONDS = int(os.getenv("CORE_AI_POLL_SECONDS", "10"))
CPU_LIMIT_PERCENT = float(os.getenv("CORE_AI_MAX_CPU_PERCENT", "70"))
MIN_AVAILABLE_MIB = int(os.getenv("CORE_AI_MIN_AVAILABLE_MIB", "3072"))
MAX_STREAM_LAG = int(os.getenv("CORE_AI_MAX_STREAM_LAG", "1000"))
MODEL = os.getenv("CORE_LLM_MODEL", "qwen3.6:latest")
ENDPOINT = os.getenv("CORE_LLM_ENDPOINT", "http://192.168.68.107:11434/v1")
PROMPT_PATH = Path("project/prompts/scrum-101-workset-llm-v2.json")


def db_connect():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"), port=os.getenv("DB_PORT", "5432"),
        user=os.environ["DB_USER"], password=os.environ["DB_PASS"],
        dbname=os.environ["DB_NAME"], cursor_factory=psycopg2.extras.RealDictCursor,
    )


def host_resources(proc_root: Path = Path("/host/proc")) -> dict[str, float]:
    load_1m = float((proc_root / "loadavg").read_text().split()[0])
    cpu_count = max(1, sum(
        line.startswith("processor")
        for line in (proc_root / "cpuinfo").read_text().splitlines()
    ))

    memory = {}
    for line in (proc_root / "meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        memory[key] = int(value.strip().split()[0])

    # Some Synology kernels do not expose MemAvailable.
    # Fall back to memory that can reasonably be reclaimed.
    if "MemAvailable" in memory:
        available_memory_kib = memory["MemAvailable"]
    else:
        available_memory_kib = (
            memory.get("MemFree", 0)
            + memory.get("Buffers", 0)
            + memory.get("Cached", 0)
            + memory.get("SReclaimable", 0)
        )
        available_memory_kib = min(
            available_memory_kib,
            memory.get("MemTotal", available_memory_kib),
        )

    return {
        "cpu_load_percent": round(load_1m / cpu_count * 100, 2),
        "available_memory_mib": round(available_memory_kib / 1024, 1),
    }


def stream_lag(client: redis.Redis) -> int:
    total = 0
    for stream in ("scan_stream", "scan_stream_realtime"):
        try:
            total += sum(int(group.get("lag") or 0) for group in client.xinfo_groups(stream))
        except redis.ResponseError:
            continue
    return total


def resource_gate(
    resources: dict[str, float],
    lag: int,
    job: dict[str, Any] | None = None,
) -> str | None:
    # Een expliciet aangevraagde AI-job mag gewone CPU-druk passeren.
    # Zonder pending job blijft de normale CPU-beveiliging actief.
    if job is None and resources["cpu_load_percent"] > CPU_LIMIT_PERCENT:
        return "waiting_for_cpu"

    # Geheugen blijft altijd een harde veiligheidsgrens.
    if resources["available_memory_mib"] < MIN_AVAILABLE_MIB:
        return "waiting_for_memory"

    # De primaire CORE-pipeline houdt altijd voorrang.
    if lag > MAX_STREAM_LAG:
        return "core_pipeline_priority"

    return None


def set_pending_reason(reason: str | None) -> None:
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE public.workset_ai_jobs SET waiting_reason=%s, updated_at=now()
            WHERE status='pending' AND waiting_reason IS DISTINCT FROM %s
        """, (reason, reason))


def claim_job() -> dict[str, Any] | None:
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM public.workset_ai_jobs
            WHERE status='pending'
            ORDER BY priority DESC, requested_at, id
            FOR UPDATE SKIP LOCKED LIMIT 1
        """)
        job = cur.fetchone()
        if not job:
            return None
        cur.execute("""
            UPDATE public.workset_ai_jobs
            SET status='running', waiting_reason=NULL, started_at=now(), finished_at=NULL,
                attempt_count=attempt_count+1, updated_at=now()
            WHERE id=%s
        """, (job["id"],))
        return dict(job)
    
def peek_job() -> dict[str, Any] | None:
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM public.workset_ai_jobs
            WHERE status='pending'
            ORDER BY priority DESC, requested_at, id
            LIMIT 1
        """)
        job = cur.fetchone()
        return dict(job) if job else None

def relevant_examples(cur, filename: str, file_id: int) -> list[dict[str, Any]]:
    cur.execute("""
        SELECT e.id AS review_id,e.file_id,f.filename,
               e.corrected_category_code AS category_code,
               e.corrected_document_family_code AS family_code,e.created_at
        FROM public.document_review_events e JOIN public.files f ON f.id=e.file_id
        WHERE e.review_type='target_path' AND e.decision='accepted'
          AND e.corrected_category_code IS NOT NULL
          AND e.corrected_document_family_code IS NOT NULL AND e.file_id<>%s
        ORDER BY e.created_at DESC LIMIT 100
    """, (file_id,))
    terms = {part for part in filename.casefold().replace("_", " ").split() if len(part) > 2}
    rows = [dict(row) for row in cur.fetchall()]
    rows.sort(key=lambda row: (-len(terms.intersection({
        part for part in str(row["filename"]).casefold().replace("_", " ").split() if len(part) > 2
    })), str(row["created_at"]), int(row["file_id"])))
    return rows[:3]


def existing_ocr_evidence(cur, file_id: int, content_sha256: str) -> dict[str, Any] | None:
    """Return current content-bound OCR evidence before opening the document again."""
    cur.execute("""
        SELECT sd.run_id, sd.file_id AS evidence_file_id, sd.status,
               sd.pages, sd.updated_at
        FROM public.semantic_documents sd
        WHERE sd.content_sha256=%s AND sd.status='needs_ocr'
        ORDER BY (sd.file_id=%s) DESC, sd.updated_at DESC, sd.run_id DESC
        LIMIT 1
    """, (content_sha256, file_id))
    evidence = cur.fetchone()
    return dict(evidence) if evidence else None


def process_job(job: dict[str, Any]) -> None:
    prompt = json.loads(PROMPT_PATH.read_text("utf-8"))
    provider = OpenAICompatibleLocalProvider(
        ENDPOINT, timeout_seconds=int(os.getenv("CORE_LLM_TIMEOUT_SECONDS", "600")),
    )
    started = time.monotonic()
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT w.*, c.category, c.document_family
            FROM public.v_active_document_workset w
            LEFT JOIN public.v_current_file_classification c ON c.file_id=w.file_id
            WHERE w.file_id=%s
        """, (job["file_id"],))
        row = cur.fetchone()
        if not row or row["content_sha256"] != job["content_sha256"]:
            cur.execute("""
                UPDATE public.workset_ai_jobs SET status='cancelled', error_code='stale_file',
                    finished_at=now(), updated_at=now() WHERE id=%s
            """, (job["id"],))
            return
        # The queue stores the effective status, including a human lifecycle override.
        # Do not replace it with the older calculated status from the workset view.
        row["workset_status"] = job["workset_status_snapshot"]
        examples = relevant_examples(cur, row["filename"], row["file_id"])
        ocr_evidence = existing_ocr_evidence(
            cur, int(row["file_id"]), str(row["content_sha256"]),
        )

    context = ({
        "status": "ocr_recommended",
        "reason": "ocr_required_from_existing_evidence",
        "text": "",
        "pages": ocr_evidence.get("pages"),
        "ocr_recommended": True,
        "evidence_source": "semantic_documents",
        "evidence_run_id": str(ocr_evidence["run_id"]),
        "evidence_file_id": int(ocr_evidence["evidence_file_id"]),
        "evidence_updated_at": ocr_evidence["updated_at"].isoformat(),
    } if ocr_evidence else extract_bounded_context(str(row["path"])))
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if context["status"] != "ready":
        proposal = abstention(int(row["file_id"]), context["reason"])
    else:
        system, user = build_prompt(
            {**dict(row), "core_category": row.get("category"), "core_family": row.get("document_family")},
            context, examples, prompt["system_prompt"],
        )
        generated = provider.generate(GenerationRequest(MODEL, system, user))
        proposal = validate_proposal(generated["content"], int(row["file_id"]))
        usage.update({key: int(generated.get("usage", {}).get(key) or 0) for key in usage})

    run_status = "completed" if proposal["status"] == "ready" else "completed_with_errors"
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO public.workset_ai_runs
              (idempotency_key,channel,status,selected_file_ids,selection_snapshot,provider_id,
               model_id,prompt_version,schema_version,document_count,proposal_count,error_count,
               prompt_tokens,completion_tokens,total_tokens,duration_seconds)
            VALUES (%s,'workset_portal',%s,%s,%s::jsonb,%s,%s,%s,%s,1,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (str(job["idempotency_key"]), run_status, [row["file_id"]],
              json.dumps({"job_id": str(job["id"]), "file_id": row["file_id"]}),
              provider.provider_id, MODEL, PROMPT_VERSION, SCHEMA_VERSION,
              int(proposal["status"] == "ready"), int(proposal["status"] != "ready"),
              usage["prompt_tokens"], usage["completion_tokens"], usage["total_tokens"],
              round(time.monotonic() - started, 3)))
        run_id = cur.fetchone()["id"]
        cur.execute("""
            INSERT INTO public.workset_ai_proposals
              (run_id,file_id,content_sha256,status,category_code,family_code,lifecycle,
               privacy_advice,confidence,relation_kind,related_file_ids,reason,
               example_review_ids,extraction_metadata)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::bigint[],%s,%s::uuid[],%s::jsonb)
            RETURNING id
        """, (run_id, row["file_id"], row["content_sha256"], proposal["status"],
              proposal["category_code"], proposal["family_code"], proposal["lifecycle"],
              proposal["privacy_advice"], proposal["confidence"], proposal["relation_kind"],
              proposal["related_file_ids"], proposal["reason"],
              [str(item["review_id"]) for item in examples],
              json.dumps({key: value for key, value in context.items() if key != "text"})))
        proposal_id = cur.fetchone()["id"]
        cur.execute("""
            UPDATE public.workset_ai_jobs
            SET status=%s, run_id=%s, proposal_id=%s, finished_at=now(), updated_at=now()
            WHERE id=%s
        """, ("ready" if proposal["status"] == "ready" else "abstained",
              run_id, proposal_id, job["id"]))


def fail_or_retry(job: dict[str, Any], exc: Exception) -> None:
    provider_failure = type(exc).__name__ in {"TimeoutError", "URLError", "ConnectionRefusedError"}
    with db_connect() as conn, conn.cursor() as cur:
        if provider_failure and int(job.get("attempt_count") or 0) < 3:
            cur.execute("""
                UPDATE public.workset_ai_jobs SET status='pending', started_at=NULL,
                    waiting_reason='provider_unavailable', error_code=%s, updated_at=now()
                WHERE id=%s
            """, (type(exc).__name__, job["id"]))
        else:
            cur.execute("""
                UPDATE public.workset_ai_jobs SET status='failed', error_code=%s,
                    finished_at=now(), updated_at=now() WHERE id=%s
            """, (type(exc).__name__, job["id"]))


def main() -> int:
    client = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), decode_responses=True)
    while True:
        try:
            resources = host_resources()
            pending_job = peek_job()
            reason = resource_gate(resources, stream_lag(client), pending_job)
            client.set("workset_ai_worker:heartbeat", datetime.now(timezone.utc).isoformat(), ex=90)
            client.hset("workset_ai_worker:resources", mapping={
                **resources, "gate_reason": reason or "ready",
            })
            set_pending_reason(reason)
            if reason:
                time.sleep(POLL_SECONDS)
                continue
            job = claim_job()
            if not job:
                time.sleep(POLL_SECONDS)
                continue
            try:
                process_job(job)
            except Exception as exc:  # worker boundary; error code remains auditable
                fail_or_retry(job, exc)
        except Exception:
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
