#!/usr/bin/env python3
"""Read-only SCRUM-89 temporal canonical selection v2 impact report."""

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
from core.metadata.temporal_canonical import assess_rows, summarize
from tools.runtime.migration_inventory import run_query, shutil_which


QUERY = r"""
SELECT
    w.file_id,
    w.content_group_id,
    w.filename,
    w.extension,
    w.path,
    w.filesystem_modified_at,
    w.workset_status AS v1_workset_status,
    w.reason_code AS v1_reason_code,
    w.created_has_conflict,
    w.modified_has_conflict,
    w.activity_window_months,
    w.policy_version,
    w.policy_checksum,
    tp.source_created_at AS v1_created_at,
    tp.created_evidence_id AS v1_created_evidence_id,
    tp.source_modified_at AS v1_modified_at,
    tp.modified_evidence_id AS v1_modified_evidence_id,
    e.id AS evidence_id,
    e.date_type AS evidence_date_type,
    e.source_type AS evidence_source_type,
    e.confidence AS evidence_confidence,
    e.value_at AS evidence_value_at,
    e.local_value AS evidence_local_value,
    e.timezone_status AS evidence_timezone_status,
    e.raw_value AS evidence_raw_value
FROM public.v_active_document_workset w
LEFT JOIN public.v_file_temporal_profile tp ON tp.file_id = w.file_id
LEFT JOIN public.file_date_evidence e ON (
    (e.evidence_scope = 'content' AND e.content_sha256 = w.content_sha256)
    OR (e.evidence_scope = 'file' AND e.file_id = w.file_id)
)
ORDER BY w.file_id, e.date_type, e.source_type, e.id;
"""

FIELDS = [
    "schema_version", "selection_rule_version", "file_id", "content_group_id",
    "filename", "extension", "path", "filesystem_modified_at", "v1_created_at",
    "v1_created_evidence_id", "v2_canonical_created_at",
    "created_changed", "created_evidence_id", "created_source_type", "created_confidence",
    "created_timezone_status", "created_precision", "created_same_day_precision_preferred",
    "created_selection_reason", "v1_modified_at",
    "v1_modified_evidence_id",
    "earliest_observed_created_at", "latest_observed_created_at",
    "v2_canonical_modified_at", "modified_changed", "modified_evidence_id",
    "modified_source_type", "modified_confidence", "modified_timezone_status",
    "modified_precision", "modified_same_day_precision_preferred",
    "modified_selection_reason", "earliest_observed_modified_at",
    "latest_observed_modified_at", "credible_evidence_count", "credible_evidence_ids",
    "excluded_evidence_count", "excluded_evidence", "material_temporal_conflict",
    "lifecycle_conflict_effect", "chronology_issue", "v1_workset_status", "v1_reason_code",
    "v2_workset_status",
    "lifecycle_changed", "v2_lifecycle_reason", "canonical_activity_at",
    "activity_cutoff_at", "activity_window_months", "policy_version", "policy_checksum",
    "database_writes", "file_mutations",
]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="temporal-canonical-impact")
    result.add_argument("--as-of", help="Reproducible ISO-8601 assessment timestamp")
    result.add_argument("--limit", type=int)
    result.add_argument("--dry-run", action="store_true", required=True)
    return result


def parse_as_of(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_csv(value: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(value)))


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        as_of = parse_as_of(args.as_of)
        docker = os.getenv("DOCKER_BIN", "docker")
        if docker == "docker" and not shutil_which(docker) and Path("/usr/local/bin/docker").exists():
            docker = "/usr/local/bin/docker"
        command = [
            docker, "exec", os.getenv("POSTGRES_CONTAINER", "postgres"), "psql",
            "-U", os.getenv("DB_USER", "hugo"), "-d", os.getenv("DB_NAME", "nasdb_test"),
        ]
        source_rows = parse_csv(run_query(command, QUERY, "/volume1/unused"))
        rows = assess_rows(source_rows, as_of=as_of, limit=args.limit)
    except (ValueError, subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Temporal canonical impact failed: {exc}", file=sys.stderr)
        return 1

    metrics = summarize(rows)
    review = [
        row for row in rows
        if row["created_changed"] or row["modified_changed"]
        or row["lifecycle_changed"] or row["material_temporal_conflict"]
        or row["excluded_evidence_count"] or row["chronology_issue"]
    ]
    generated_at = datetime.now().astimezone()
    timestamp = generated_at.strftime("%Y%m%d-%H%M%S")
    export_dir = PROJECT_ROOT / "project/exports/active-workset"
    export_dir.mkdir(parents=True, exist_ok=True)
    csv_path = export_dir / f"temporal-canonical-impact-{timestamp}.csv"
    review_path = export_dir / f"temporal-canonical-impact-review-{timestamp}.csv"
    json_path = export_dir / f"temporal-canonical-impact-{timestamp}.json"
    md_path = export_dir / f"temporal-canonical-impact-{timestamp}.md"
    write_dict_rows(csv_path, rows, FIELDS)
    write_dict_rows(review_path, review, FIELDS)
    payload = {
        "schema_version": "temporal-canonical-impact-report-v3",
        "generated_at": generated_at.isoformat(),
        "as_of": as_of.isoformat(),
        "mode": "read_only_dry_run",
        "summary": metrics,
        "documents": rows,
        "review_selection": review,
        "safety": {"database_writes": False, "file_mutations": False},
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# SCRUM-89 temporal canonical selection v2 impact", "",
        f"- Generated: `{generated_at.isoformat()}`",
        f"- Assessment time: `{as_of.isoformat()}`",
        "- Mode: **read-only dry-run**",
        "- Database writes: **false**",
        "- File mutations: **false**", "",
        "## Impact", "",
        f"- Documents assessed: **{metrics['documents']}**",
        f"- Canonical created changed: **{metrics['created_changed']}**",
        f"- Canonical modified changed: **{metrics['modified_changed']}**",
        f"- Created same-day precision preferred: **{metrics['created_same_day_precision_preferred']}**",
        f"- Modified same-day precision preferred: **{metrics['modified_same_day_precision_preferred']}**",
        f"- Lifecycle status changed: **{metrics['lifecycle_changed']}**",
        f"- Material temporal conflicts: **{metrics['material_conflicts']}**",
        f"- Decision-invariant conflicts: **{metrics['decision_invariant_conflicts']}**",
        f"- Decision-sensitive conflicts: **{metrics['decision_sensitive_conflicts']}**",
        f"- Created-after-modified issues: **{metrics['created_after_modified_issues']}**",
        f"- Timezone-ambiguous chronology: **{metrics['chronology_timezone_ambiguous']}**",
        f"- Excluded evidence observations: **{metrics['excluded_evidence']}**", "",
        "## Status comparison", "",
        "| Status | v1 | v2 impact |", "|---|---:|---:|",
    ]
    for status in sorted(set(metrics["v1_statuses"]) | set(metrics["v2_statuses"])):
        lines.append(
            f"| {status} | {metrics['v1_statuses'].get(status, 0)} | "
            f"{metrics['v2_statuses'].get(status, 0)} |"
        )
    lines.extend([
        "", "## Interpretation", "",
        "Created uses the earliest credible created evidence. Modified uses the latest",
        "credible modified evidence. Alternative and excluded evidence remains visible in",
        "the CSV/JSON. Only a decision-sensitive temporal conflict keeps lifecycle status",
        "at `needs_review`; this report does not activate that behavior.", "",
    ])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    for latest, source in (
        (export_dir / "temporal-canonical-impact-latest.json", json_path),
        (export_dir / "temporal-canonical-impact-latest.md", md_path),
    ):
        latest.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    print("SCRUM-89 temporal canonical selection v2 impact complete")
    print(f"Report: {md_path.relative_to(PROJECT_ROOT)}")
    print(f"Details: {csv_path.relative_to(PROJECT_ROOT)}")
    print(f"Review: {review_path.relative_to(PROJECT_ROOT)}")
    print(f"JSON: {json_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
