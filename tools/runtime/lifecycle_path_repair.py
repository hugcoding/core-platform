#!/usr/bin/env python3
"""Append-only alignment of stored target paths with the effective lifecycle."""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE_CANDIDATES = """
    SELECT v.*, e.id AS supersedes_event_id
    FROM public.v_document_workset_path_review v
    LEFT JOIN public.v_latest_document_review e
      ON e.file_id = v.file_id AND e.review_type = 'target_path'
    WHERE v.path_requires_lifecycle_correction
      AND v.lifecycle_aligned_proposed_path IS NOT NULL
"""


def psql_copy(sql: str) -> list[dict[str, str]]:
    docker = os.getenv("DOCKER_BIN", "docker")
    if docker == "docker" and Path("/usr/local/bin/docker").exists():
        docker = "/usr/local/bin/docker"
    command = [
        docker, "exec", "-i", os.getenv("POSTGRES_CONTAINER", "postgres"),
        "psql", "-v", "ON_ERROR_STOP=1", "-U", os.getenv("DB_USER", "hugo"),
        "-d", os.getenv("DB_NAME", "nasdb_test"), "-c", sql,
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
    return list(csv.DictReader(io.StringIO(completed.stdout)))


def candidate_query() -> str:
    return """COPY (
        SELECT file_id, filename, effective_workset_status,
               stored_proposed_path, lifecycle_aligned_proposed_path,
               supersedes_event_id
        FROM ({}) candidates
        ORDER BY effective_workset_status, filename, file_id
    ) TO STDOUT WITH CSV HEADER;""".format(BASE_CANDIDATES)


def apply_query() -> str:
    return """COPY (
        WITH candidates AS ({}),
        inserted AS (
            INSERT INTO public.document_review_events (
                id, idempotency_key, review_contract_version, channel, review_type,
                file_id, content_group_id, content_sha256,
                proposal_category_code, proposal_document_family_code,
                proposal_lifecycle, proposal_target_path, proposal_confidence,
                proposal_reason_code, decision, corrected_document_family_code,
                review_notes, reviewer, supersedes_event_id, created_at,
                proposed_target_path, proposed_target_path_raw, target_path_input_kind
            )
            SELECT
                gen_random_uuid(),
                'lifecycle-path-alignment-v1:' || c.file_id || ':' ||
                    c.content_sha256 || ':' || c.effective_lifecycle,
                'lifecycle-path-alignment-v1', 'workset_portal', 'target_path',
                c.file_id, c.content_group_id, c.content_sha256,
                COALESCE(c.corrected_category_code, c.accepted_category),
                COALESCE(c.corrected_document_family_code, c.accepted_document_family),
                c.effective_lifecycle, c.stored_proposed_path, 'high',
                'lifecycle_zone_alignment_v1', 'accepted',
                COALESCE(c.corrected_document_family_code, c.accepted_document_family),
                '[CORE] Doelpadzone append-only uitgelijnd met effectieve lifecycle.',
                'core-lifecycle-path-repair', c.supersedes_event_id, clock_timestamp(),
                c.lifecycle_aligned_proposed_path, c.lifecycle_aligned_proposed_path,
                'full_path'
            FROM candidates c
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, file_id, proposed_target_path, supersedes_event_id, created_at
        )
        SELECT i.file_id, f.filename, i.proposed_target_path AS corrected_path,
               i.id AS correction_event_id, i.supersedes_event_id, i.created_at
        FROM inserted i
        JOIN public.files f ON f.id = i.file_id
        ORDER BY f.filename, i.file_id
    ) TO STDOUT WITH CSV HEADER;""".format(BASE_CANDIDATES)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="lifecycle-path-repair")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        before = psql_copy(candidate_query())
        inserted = psql_copy(apply_query()) if args.apply and before else []
        remaining = psql_copy(candidate_query()) if args.apply else before
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        print("Lifecycle path repair failed: {}".format(detail))
        return 1

    generated = datetime.now().astimezone()
    payload = {
        "schema_version": "append-only-lifecycle-path-alignment-v1",
        "generated_at": generated.isoformat(),
        "mode": "apply" if args.apply else "dry_run",
        "candidates_before": len(before),
        "events_inserted": len(inserted),
        "candidates_remaining": len(remaining),
        "candidates": before,
        "inserted_events": inserted,
        "safety": {
            "database_writes": bool(args.apply), "append_only": True,
            "existing_events_updated": False, "file_mutations": False,
        },
    }
    output = ROOT / "project/exports/review-learning"
    output.mkdir(parents=True, exist_ok=True)
    stamp = generated.strftime("%Y%m%d-%H%M%S")
    report = output / "lifecycle-path-repair-{}.json".format(stamp)
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "lifecycle-path-repair-latest.json").write_text(
        report.read_text(encoding="utf-8"), encoding="utf-8",
    )
    print(json.dumps({
        "status": "applied" if args.apply else "dry_run",
        "candidates": len(before), "events_inserted": len(inserted),
        "candidates_remaining": len(remaining),
        "report": str(report.relative_to(ROOT)),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
