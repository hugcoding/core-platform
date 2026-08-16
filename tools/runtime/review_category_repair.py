#!/usr/bin/env python3
"""Append-only repair for accepted reviews with an unambiguous missing category."""
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
ELIGIBLE_FAMILIES = (
    "resumes", "motivation_letters", "vacancies", "interview_preparation",
)
FAMILY_SQL = ", ".join("'{}'".format(value) for value in ELIGIBLE_FAMILIES)
BASE_CANDIDATES = """
    SELECT e.*, f.filename
    FROM public.v_latest_document_review e
    JOIN public.files f ON f.id = e.file_id
    WHERE e.review_type = 'target_path'
      AND e.decision = 'accepted'
      AND e.corrected_category_code IS NULL
      AND e.corrected_document_family_code IN ({families})
""".format(families=FAMILY_SQL)


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
        SELECT file_id, filename, corrected_document_family_code AS family_code,
               'work_career'::text AS repaired_category_code, id AS supersedes_event_id
        FROM ({candidates}) candidates
        ORDER BY corrected_document_family_code, filename, file_id
    ) TO STDOUT WITH CSV HEADER;""".format(candidates=BASE_CANDIDATES)


def apply_query() -> str:
    return """COPY (
        WITH candidates AS ({candidates}),
        payloads AS (
            SELECT to_jsonb(e) || jsonb_build_object(
                'id', gen_random_uuid(),
                'idempotency_key', 'scrum-98-category-repair-v1:' || e.file_id || ':' || e.id,
                'corrected_category_code', 'work_career',
                'reviewer', 'core-category-repair',
                'supersedes_event_id', e.id,
                'created_at', clock_timestamp(),
                'review_notes', concat_ws(E'\\n', NULLIF(e.review_notes, ''),
                    '[CORE] Ontbrekende categorie append-only hersteld naar Werk & Loopbaan.')
            ) - 'filename' AS payload
            FROM candidates e
        ),
        inserted AS (
            INSERT INTO public.document_review_events
            SELECT (jsonb_populate_record(NULL::public.document_review_events, payload)).*
            FROM payloads
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, file_id, corrected_document_family_code,
                      corrected_category_code, supersedes_event_id, created_at
        )
        SELECT i.file_id, f.filename,
               i.corrected_document_family_code AS family_code,
               i.corrected_category_code AS repaired_category_code,
               i.id AS repair_event_id, i.supersedes_event_id, i.created_at
        FROM inserted i JOIN public.files f ON f.id = i.file_id
        ORDER BY i.corrected_document_family_code, f.filename, i.file_id
    ) TO STDOUT WITH CSV HEADER;""".format(candidates=BASE_CANDIDATES)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="review-category-repair")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        before = psql_copy(candidate_query())
        changed = psql_copy(apply_query()) if args.apply and before else []
        remaining = psql_copy(candidate_query()) if args.apply else before
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        print("Category repair failed: {}".format(detail))
        return 1

    generated = datetime.now().astimezone()
    payload = {
        "schema_version": "append-only-category-repair-v1",
        "generated_at": generated.isoformat(),
        "mode": "apply" if args.apply else "dry_run",
        "eligible_families": list(ELIGIBLE_FAMILIES),
        "target_category_code": "work_career",
        "candidates_before": len(before),
        "events_inserted": len(changed),
        "candidates_remaining": len(remaining),
        "candidates": before,
        "inserted_events": changed,
        "safety": {
            "append_only": True,
            "existing_events_updated": False,
            "file_mutations": False,
            "ambiguous_families_excluded": True,
        },
    }
    output = ROOT / "project/exports/review-learning"
    output.mkdir(parents=True, exist_ok=True)
    stamp = generated.strftime("%Y%m%d-%H%M%S")
    report = output / "review-category-repair-{}.json".format(stamp)
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "review-category-repair-latest.json").write_text(
        report.read_text(encoding="utf-8"), encoding="utf-8",
    )
    print(json.dumps({
        "status": "applied" if args.apply else "dry_run",
        "candidates": len(before), "events_inserted": len(changed),
        "candidates_remaining": len(remaining),
        "report": str(report.relative_to(ROOT)),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
