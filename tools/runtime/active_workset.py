#!/usr/bin/env python3
"""Read-only active-workset-v1 pilot for SCRUM-89."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.exports.csv_format import write_dict_rows
from core.workset.active_workset import (
    evaluate_rows, select_review, subtract_months, summary, validate_policy,
)
from tools.runtime.migration_inventory import run_query, shutil_which


DEFAULT_POLICY = PROJECT_ROOT / "project/policies/active-workset-v1.json"
EXPORT_FIELDS = [
    "schema_version", "policy_version", "candidate_file_id", "source_file_id", "golden_file_id",
    "content_group_id", "content_sha256", "source_path", "golden_path",
    "filename", "extension", "size_bytes", "source_copy_count",
    "duplicate_represented_by_golden", "core_first_observed_at",
    "source_modified_at", "temporal_source_created_at", "temporal_created_confidence",
    "temporal_created_source_type", "temporal_source_modified_at",
    "temporal_modified_confidence", "temporal_modified_source_type",
    "temporal_evidence_count", "created_has_conflict", "modified_has_conflict",
    "activity_at", "activity_basis_source", "within_activity_window",
    "activity_window_months", "workset_status", "reason", "confidence",
    "missing_evidence", "database_writes", "file_mutations",
]
REVIEW_FIELDS = EXPORT_FIELDS + ["review_reason", "review_status", "review_notes"]

QUERY = r"""
SELECT
    f.id AS source_file_id,
    f.path AS source_path,
    f.filename,
    lower(coalesce(f.extension, '')) AS extension,
    f.size_bytes,
    f.content_sha256,
    f.modified_at_fs,
    f.created_at AS core_created_at,
    cg.id AS content_group_id,
    gf.id AS golden_file_id,
    gf.path AS golden_path,
    gf.filename AS golden_filename,
    lower(coalesce(gf.extension, '')) AS golden_extension,
    gf.size_bytes AS golden_size_bytes,
    tp.source_created_at AS temporal_source_created_at,
    tp.created_confidence,
    tp.created_source_type,
    tp.source_modified_at AS temporal_source_modified_at,
    tp.modified_confidence,
    tp.modified_source_type,
    tp.evidence_count,
    tp.created_has_conflict,
    tp.modified_has_conflict
FROM files f
LEFT JOIN content_groups cg
  ON cg.content_sha256 = f.content_sha256
 AND cg.size_bytes IS NOT DISTINCT FROM f.size_bytes
LEFT JOIN files gf ON gf.id = cg.golden_file_id AND gf.deleted_at IS NULL
LEFT JOIN v_file_temporal_profile tp ON tp.file_id = gf.id
WHERE f.deleted_at IS NULL
  AND (f.path = :'source' OR f.path LIKE :'source_prefix')
  AND lower(coalesce(f.extension, '')) IN ('docx', 'xlsx')
ORDER BY cg.id NULLS LAST, f.modified_at_fs DESC NULLS LAST, f.path, f.id;
"""


def parse_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def parse_as_of(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a read-only active-workset-v1 pilot.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--as-of", help="Reproducible ISO-8601 assessment timestamp")
    parser.add_argument("--dry-run", action="store_true", required=True)
    return parser


def _markdown_table(rows: list[dict[str, object]]) -> list[str]:
    lines = [
        "| Status | Type | Bestand | Bronreden | Confidence | Reviewreden |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        filename = str(row["filename"]).replace("|", "\\|")
        lines.append(
            f"| {row['workset_status']} | {str(row['extension']).upper()} | "
            f"{filename} | {row['reason']} | {row['confidence']} | {row['review_reason']} |"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        policy = validate_policy(json.loads(Path(args.policy).read_text(encoding="utf-8")))
        as_of = parse_as_of(args.as_of)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Active-workset policy invalid: {exc}", file=sys.stderr)
        return 2

    docker = os.getenv("DOCKER_BIN", "docker")
    if docker == "docker" and not shutil_which(docker) and Path("/usr/local/bin/docker").exists():
        docker = "/usr/local/bin/docker"
    command = [
        docker, "exec", os.getenv("POSTGRES_CONTAINER", "postgres"), "psql",
        "-U", os.getenv("DB_USER", "hugo"), "-d", os.getenv("DB_NAME", "nasdb_test"),
    ]
    try:
        rows = parse_csv(run_query(command, QUERY, policy["source"]))
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Active-workset pilot failed: {exc}", file=sys.stderr)
        return 1

    evaluated = evaluate_rows(rows, policy=policy, as_of=as_of)
    review = [
        {**row, "review_status": "pending", "review_notes": ""}
        for row in select_review(evaluated, policy)
    ]
    metrics = summary(evaluated)
    cutoff = subtract_months(as_of, policy["activity_window_months"])
    generated_at = datetime.now().astimezone()
    timestamp = generated_at.strftime("%Y%m%d-%H%M%S")
    export_dir = PROJECT_ROOT / "project/exports/active-workset"
    export_dir.mkdir(parents=True, exist_ok=True)
    csv_path = export_dir / f"active-workset-v1-{timestamp}.csv"
    review_path = export_dir / f"active-workset-v1-review-{timestamp}.csv"
    json_path = export_dir / f"active-workset-v1-{timestamp}.json"
    md_path = export_dir / f"active-workset-v1-{timestamp}.md"
    write_dict_rows(csv_path, evaluated, EXPORT_FIELDS)
    write_dict_rows(review_path, review, REVIEW_FIELDS)
    payload = {
        "schema_version": "active-workset-pilot-v1",
        "generated_at": generated_at.isoformat(),
        "as_of": as_of.isoformat(),
        "cutoff": cutoff.isoformat(),
        "mode": "read_only_dry_run",
        "policy": policy,
        "summary": metrics,
        "files": evaluated,
        "review_selection": review,
        "safety": {"database_writes": False, "file_mutations": False},
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report = [
        "# SCRUM-89 active-workset-v1 pilot", "",
        f"- Generated: `{generated_at.isoformat()}`",
        f"- Source: `{policy['source']}`",
        f"- Extensions: `{', '.join(policy['extensions'])}`",
        f"- Policy: `{policy['policy_version']}`",
        f"- Activity window: **{policy['activity_window_months']} months**",
        f"- Cutoff: `{cutoff.isoformat()}`",
        "- Mode: **read-only dry-run**", "- Database writes: **false**",
        "- File mutations: **false**", "",
        "## Summary", "",
        f"- Content groups: **{metrics['content_groups']}**",
        f"- Active candidates: **{metrics['active_candidates']}**",
        f"- Inactive: **{metrics['inactive']}**",
        f"- Needs review: **{metrics['needs_review']}**",
        f"- Groepen met meerdere bronkopieen of een extern golden record: **{metrics['duplicate_groups']}**",
        f"- Compact review rows: **{len(review)}**", "",
        "## Tijdsbewijs", "",
        "De pilot combineert filesystem-mutatietijd met de beste bron-created en bron-modified",
        "evidence uit `v_file_temporal_profile`. Alleen het actuele persisted golden record is",
        "kandidaat. Conflicterende temporal evidence wordt niet automatisch beslist maar krijgt",
        "`needs_review`. CORE record creation telt niet mee als bronaanmaakdatum.", "",
        "## Compact review", "",
        *_markdown_table(review), "",
    ]
    md_path.write_text("\n".join(report), encoding="utf-8")
    (export_dir / "active-workset-v1-latest.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    (export_dir / "active-workset-v1-latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    print("SCRUM-89 read-only active-workset-v1 pilot complete")
    print(f"Report: {md_path.relative_to(PROJECT_ROOT)}")
    print(f"Details: {csv_path.relative_to(PROJECT_ROOT)}")
    print(f"Review: {review_path.relative_to(PROJECT_ROOT)}")
    print(f"JSON: {json_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
