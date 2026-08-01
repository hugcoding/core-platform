#!/usr/bin/env python3
"""Create a read-only OneDrive baseline and exact-duplicate review for SCRUM-76."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.exports.csv_format import write_dict_rows
from core.integrity.golden_record import ALGORITHM_VERSION, rank_candidates, selection_metadata
from tools.runtime.migration_inventory import run_query, shutil_which


ASSESSMENT_VERSION = "onedrive-baseline-v1"
DEFAULT_SOURCE = "/volume1/data/import/cloud/onedrive/current"

BASELINE_QUERY = r"""
SELECT
    f.id AS file_id,
    f.path,
    f.filename,
    LOWER(COALESCE(f.extension, '')) AS extension,
    f.size_bytes,
    f.content_sha256,
    f.mime_type,
    f.modified_at_fs,
    f.created_at,
    f.updated_at,
    TRUE AS is_baseline
FROM files f
WHERE f.deleted_at IS NULL
  AND (f.path = :'source' OR f.path LIKE :'source_prefix')
ORDER BY f.path, f.id;
"""

QUERY = r"""
WITH baseline AS (
    SELECT
        f.id,
        f.content_sha256,
        f.size_bytes
    FROM files f
    WHERE f.deleted_at IS NULL
      AND (f.path = :'source' OR f.path LIKE :'source_prefix')
),
baseline_keys AS (
    SELECT DISTINCT content_sha256, size_bytes
    FROM baseline
    WHERE content_sha256 IS NOT NULL AND content_sha256 <> ''
),
matched AS (
    SELECT
        f.id AS file_id,
        f.path,
        f.filename,
        LOWER(COALESCE(f.extension, '')) AS extension,
        f.size_bytes,
        f.content_sha256,
        f.mime_type,
        f.modified_at_fs,
        f.created_at,
        f.updated_at,
        ((f.path = :'source' OR f.path LIKE :'source_prefix')) AS is_baseline,
        cg.id AS content_group_id,
        cg.golden_file_id AS existing_golden_file_id,
        cg.confidence AS existing_group_confidence,
        cg.selection_status AS existing_selection_status
    FROM files f
    JOIN baseline_keys bk
      ON bk.content_sha256 = f.content_sha256
     AND bk.size_bytes IS NOT DISTINCT FROM f.size_bytes
    LEFT JOIN content_groups cg
      ON cg.content_sha256 = f.content_sha256
     AND cg.size_bytes IS NOT DISTINCT FROM f.size_bytes
    WHERE f.deleted_at IS NULL
),
unhashed AS (
    SELECT
        f.id AS file_id,
        f.path,
        f.filename,
        LOWER(COALESCE(f.extension, '')) AS extension,
        f.size_bytes,
        f.content_sha256,
        f.mime_type,
        f.modified_at_fs,
        f.created_at,
        f.updated_at,
        TRUE AS is_baseline,
        NULL::uuid AS content_group_id,
        NULL::integer AS existing_golden_file_id,
        NULL::text AS existing_group_confidence,
        NULL::text AS existing_selection_status
    FROM files f
    JOIN baseline b ON b.id = f.id
    WHERE f.content_sha256 IS NULL OR f.content_sha256 = ''
)
SELECT * FROM matched
UNION ALL
SELECT * FROM unhashed
ORDER BY content_sha256 NULLS LAST, size_bytes, path, file_id;
"""


MANIFEST_FIELDS = [
    "assessment_version", "content_group_id", "content_sha256", "size_bytes",
    "baseline_copy_count", "historical_copy_count", "total_active_copy_count",
    "canonical_file_id", "canonical_path", "canonical_source_zone", "canonical_basis",
    "selection_score", "score_margin", "confidence", "selection_status",
    "relationship", "proposed_action", "maximum_reclaimable_bytes_upper_bound",
    "historical_reclaimable_bytes_upper_bound", "baseline_internal_reclaimable_bytes_upper_bound",
    "baseline_sources", "historical_sources", "selection_reasons",
    "baseline_protected", "execution_authorized", "review_reason",
]

REVIEW_FIELDS = [
    "content_group_id", "content_sha256", "size_bytes", "baseline_copy_count",
    "historical_copy_count", "total_active_copy_count", "canonical_file_id",
    "canonical_path", "canonical_source_zone", "confidence", "relationship",
    "proposed_action", "historical_reclaimable_bytes_upper_bound",
    "baseline_internal_reclaimable_bytes_upper_bound", "maximum_reclaimable_bytes_upper_bound",
    "review_reason", "baseline_protected", "execution_authorized",
]

ACTIVITY_FIELDS = [
    "assessment_version", "file_id", "path", "filename", "size_bytes",
    "content_sha256", "activity_status", "activity_basis_date",
    "activity_basis_source", "activity_basis_confidence", "active_cutoff",
    "activity_reason", "baseline_protected", "execution_authorized",
]


def _integer(value: str | int | None) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _boolean(value: object) -> bool:
    return str(value).casefold() in {"true", "t", "1", "yes"}


def _sources(rows: list[dict[str, str]]) -> str:
    return json.dumps(
        [
            {
                "file_id": row["file_id"],
                "path": row["path"],
                "created_at": row.get("created_at", ""),
                "updated_at": row.get("updated_at", ""),
            }
            for row in sorted(rows, key=lambda item: (item["path"].casefold(), _integer(item["file_id"])))
        ],
        ensure_ascii=False,
    )


def _select_canonical(rows: list[dict[str, str]]) -> tuple[dict, str, str, str, int]:
    existing_id = next((row.get("existing_golden_file_id") for row in rows if row.get("existing_golden_file_id")), "")
    ranked = rank_candidates(rows)
    confidence, status, margin = selection_metadata(ranked)
    if existing_id:
        selected = next((row for row in ranked if row["file_id"] == existing_id), None)
        if selected is not None:
            persisted_confidence = selected.get("existing_group_confidence") or confidence
            persisted_status = selected.get("existing_selection_status") or status
            return selected, "existing_content_group", persisted_confidence, persisted_status, margin
    return ranked[0], f"deterministic_{ALGORITHM_VERSION}", confidence, status, margin


def assess_group(rows: list[dict[str, str]]) -> dict[str, str]:
    baseline = [row for row in rows if _boolean(row.get("is_baseline"))]
    historical = [row for row in rows if not _boolean(row.get("is_baseline"))]
    sample = rows[0]
    size = _integer(sample.get("size_bytes"))
    hashed = bool(sample.get("content_sha256"))

    if size == 0:
        selected = baseline[0]
        confidence, status, margin = "low", "excluded_empty_file", 0
        canonical_basis = "unavailable"
        relationship = "empty_file"
        action = "review_empty_file"
        reason = "Empty content remains inventoried but is ineligible for golden-record selection."
        selection_reasons = []
    elif not hashed:
        selected = baseline[0]
        confidence, status, margin = "low", "blocked_missing_full_hash", 0
        canonical_basis = "unavailable"
        relationship = "unassessed"
        action = "blocked_missing_full_hash"
        reason = "Full SHA-256 is required before exact matching or space-recovery review."
        selection_reasons: list[str] = []
    else:
        selected, canonical_basis, confidence, status, margin = _select_canonical(rows)
        selection_reasons = selected["selection_reasons"]
        if historical and len(baseline) > 1:
            relationship = "exact_duplicate_all_zones"
            action = "review_exact_duplicates_all_zones"
            reason = "Exact content occurs multiple times in the protected baseline and historical NAS sources."
        elif historical:
            relationship = "exact_duplicate_historical"
            action = "review_historical_exact_duplicates"
            reason = "Exact content exists in the protected baseline and at least one historical NAS source."
        elif len(baseline) > 1:
            relationship = "exact_duplicate_within_baseline"
            action = "review_onedrive_exact_duplicates"
            reason = "Exact content occurs multiple times inside the protected OneDrive baseline."
        else:
            relationship = "baseline_only"
            action = "retain_baseline"
            reason = "No other active CORE file has the same full SHA-256 and size."

    total_count = len(rows)
    maximum_reclaimable = size * max(total_count - 1, 0) if hashed else 0
    historical_reclaimable = size * len(historical) if hashed and baseline else 0
    baseline_reclaimable = size * max(len(baseline) - 1, 0) if hashed else 0
    return {
        "assessment_version": ASSESSMENT_VERSION,
        "content_group_id": sample.get("content_group_id", ""),
        "content_sha256": sample.get("content_sha256", ""),
        "size_bytes": str(size),
        "baseline_copy_count": str(len(baseline)),
        "historical_copy_count": str(len(historical)),
        "total_active_copy_count": str(total_count),
        "canonical_file_id": selected["file_id"],
        "canonical_path": selected["path"],
        "canonical_source_zone": "onedrive_baseline" if _boolean(selected.get("is_baseline")) else "historical_nas",
        "canonical_basis": canonical_basis,
        "selection_score": str(selected.get("selection_score", "")),
        "score_margin": str(margin),
        "confidence": confidence,
        "selection_status": status,
        "relationship": relationship,
        "proposed_action": action,
        "maximum_reclaimable_bytes_upper_bound": str(maximum_reclaimable),
        "historical_reclaimable_bytes_upper_bound": str(historical_reclaimable),
        "baseline_internal_reclaimable_bytes_upper_bound": str(baseline_reclaimable),
        "baseline_sources": _sources(baseline),
        "historical_sources": _sources(historical),
        "selection_reasons": json.dumps(selection_reasons, ensure_ascii=False),
        "baseline_protected": "true",
        "execution_authorized": "false",
        "review_reason": reason,
    }


def build_assessment(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (
            row.get("content_sha256") or f"UNHASHED:{row['file_id']}",
            row.get("size_bytes", ""),
        )
        groups[key].append(row)
    return [assess_group(group) for _, group in sorted(groups.items())]


def _cutoff(as_of: datetime, active_years: int) -> datetime:
    try:
        return as_of.replace(year=as_of.year - active_years)
    except ValueError:  # 29 February
        return as_of.replace(year=as_of.year - active_years, day=28)


def build_activity(rows: list[dict[str, str]], as_of: datetime, active_years: int) -> list[dict[str, str]]:
    """Classify baseline relevance independently from duplicate matching."""
    cutoff = _cutoff(as_of, active_years)
    results = []
    for row in rows:
        raw_mtime = row.get("modified_at_fs")
        basis_date = ""
        try:
            modified = datetime.fromtimestamp(int(raw_mtime or ""), tz=timezone.utc)
        except (TypeError, ValueError, OSError, OverflowError):
            modified = None
        if modified is None:
            status = "needs_temporal_review"
            reason = "Filesystem modification time is missing or invalid."
        elif modified > as_of:
            basis_date = modified.isoformat()
            status = "needs_temporal_review"
            reason = "Filesystem modification time is later than the assessment date."
        elif modified >= cutoff:
            basis_date = modified.isoformat()
            status = "active_candidate"
            reason = f"Filesystem modification time is within the last {active_years} years."
        else:
            basis_date = modified.isoformat()
            status = "legacy_review_candidate"
            reason = f"Filesystem modification time is older than the {active_years}-year active window."
        results.append({
            "assessment_version": ASSESSMENT_VERSION,
            "file_id": row.get("file_id", ""),
            "path": row.get("path", ""),
            "filename": row.get("filename", ""),
            "size_bytes": str(_integer(row.get("size_bytes"))),
            "content_sha256": row.get("content_sha256", ""),
            "activity_status": status,
            "activity_basis_date": basis_date,
            "activity_basis_source": "filesystem_mtime",
            "activity_basis_confidence": "low",
            "active_cutoff": cutoff.date().isoformat(),
            "activity_reason": reason,
            "baseline_protected": "true",
            "execution_authorized": "false",
        })
    return results


def summary_metrics(rows: list[dict[str, str]], assessment: list[dict[str, str]]) -> dict[str, int]:
    baseline_rows = [row for row in rows if _boolean(row.get("is_baseline"))]
    actions = Counter(row["proposed_action"] for row in assessment)
    return {
        "baseline_files": len(baseline_rows),
        "baseline_bytes": sum(_integer(row.get("size_bytes")) for row in baseline_rows),
        "hashed_baseline_files": sum(bool(row.get("content_sha256")) for row in baseline_rows),
        "unhashed_baseline_files": sum(not bool(row.get("content_sha256")) for row in baseline_rows),
        "content_groups": len(assessment),
        "baseline_only_groups": actions["retain_baseline"],
        "historical_duplicate_groups": actions["review_historical_exact_duplicates"],
        "all_zone_duplicate_groups": actions["review_exact_duplicates_all_zones"],
        "baseline_duplicate_groups": actions["review_onedrive_exact_duplicates"],
        "blocked_groups": actions["blocked_missing_full_hash"],
        "historical_reclaimable_bytes_upper_bound": sum(
            _integer(row["historical_reclaimable_bytes_upper_bound"]) for row in assessment
        ),
        "baseline_internal_reclaimable_bytes_upper_bound": sum(
            _integer(row["baseline_internal_reclaimable_bytes_upper_bound"]) for row in assessment
        ),
        "maximum_reclaimable_bytes_upper_bound": sum(
            _integer(row["maximum_reclaimable_bytes_upper_bound"]) for row in assessment
        ),
    }


def _gib(value: int) -> str:
    return f"{value / (1024 ** 3):.2f} GiB"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a read-only OneDrive baseline and duplicate review.")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="Absolute OneDrive baseline path below /volume1")
    parser.add_argument("--baseline-at", help="ISO timestamp of the completed Cloud Sync baseline")
    parser.add_argument("--snapshot-ref", default="", help="Optional protective snapshot reference")
    parser.add_argument("--as-of", help="Assessment date/time (ISO 8601; default: now)")
    parser.add_argument("--active-years", type=int, default=2, help="Recent activity window in years")
    parser.add_argument("--skip-exact-matching", action="store_true", help="Only assess baseline activity dates")
    parser.add_argument("--dry-run", action="store_true", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.source.rstrip("/")
    if not source.startswith("/volume1/") or source == "/volume1/data":
        print("Source must be an absolute path below /volume1 and may not be /volume1/data.", file=sys.stderr)
        return 2
    if args.active_years < 1:
        print("Active years must be at least 1.", file=sys.stderr)
        return 2
    try:
        as_of = datetime.fromisoformat(args.as_of) if args.as_of else datetime.now().astimezone()
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        as_of = as_of.astimezone(timezone.utc)
    except ValueError:
        print("As-of must be a valid ISO 8601 date or timestamp.", file=sys.stderr)
        return 2

    docker = os.getenv("DOCKER_BIN", "docker")
    if docker == "docker" and not shutil_which(docker) and Path("/usr/local/bin/docker").exists():
        docker = "/usr/local/bin/docker"
    command = [
        docker, "exec", os.getenv("POSTGRES_CONTAINER", "postgres"), "psql",
        "-U", os.getenv("DB_USER", "hugo"), "-d", os.getenv("DB_NAME", "nasdb_test"),
    ]
    try:
        baseline_rows = list(csv.DictReader(io.StringIO(run_query(command, BASELINE_QUERY, source))))
        rows = baseline_rows if args.skip_exact_matching else list(
            csv.DictReader(io.StringIO(run_query(command, QUERY, source)))
        )
    except KeyboardInterrupt:
        print("\nOneDrive baseline assessment cancelled; nothing was changed.", file=sys.stderr)
        return 130
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"OneDrive baseline assessment failed: {exc}", file=sys.stderr)
        return 1
    if not baseline_rows:
        print("OneDrive baseline assessment failed: no active CORE files found below source.", file=sys.stderr)
        return 1

    activity = build_activity(baseline_rows, as_of, args.active_years)
    assessment = [] if args.skip_exact_matching else build_assessment(rows)
    metrics = summary_metrics(rows, assessment)
    generated_at = datetime.now().astimezone()
    timestamp = generated_at.strftime("%Y%m%d-%H%M%S")
    export_dir = PROJECT_ROOT / "project" / "exports" / "migration-inventory"
    export_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = export_dir / f"onedrive-baseline-{timestamp}.csv"
    review_path = export_dir / f"onedrive-duplicate-review-{timestamp}.csv"
    activity_path = export_dir / f"onedrive-activity-{timestamp}.csv"
    report_path = export_dir / f"onedrive-baseline-{timestamp}.md"
    review = [row for row in assessment if row["proposed_action"] != "retain_baseline"]
    write_dict_rows(manifest_path, assessment, MANIFEST_FIELDS)
    write_dict_rows(activity_path, activity, ACTIVITY_FIELDS)
    write_dict_rows(
        review_path,
        ({field: row.get(field, "") for field in REVIEW_FIELDS} for row in review),
        REVIEW_FIELDS,
    )

    report = [
        "# SCRUM-76 OneDrive baseline and duplicate assessment", "",
        f"- Generated: `{generated_at.isoformat()}`",
        f"- Source: `{source}`",
        f"- Baseline completed at: `{args.baseline_at or 'not supplied'}`",
        f"- Protective snapshot: `{args.snapshot_ref or 'not supplied'}`",
        f"- Assessment version: `{ASSESSMENT_VERSION}`",
        "- Mode: **read-only dry-run**", "",
        "## Activity selection", "",
        f"- Assessment date: **{as_of.date().isoformat()}**",
        f"- Active cutoff: **{_cutoff(as_of, args.active_years).date().isoformat()}**",
        f"- Active candidates: **{sum(row['activity_status'] == 'active_candidate' for row in activity)}**",
        f"- Legacy review candidates: **{sum(row['activity_status'] == 'legacy_review_candidate' for row in activity)}**",
        f"- Temporal review required: **{sum(row['activity_status'] == 'needs_temporal_review' for row in activity)}**",
        "- Basis: filesystem modification time (low confidence); CORE observation timestamps are not used as user activity.",
        "- Activity selection is independent from exact duplicate matching.", "",
        "## Baseline", "",
        f"- Physical baseline files in CORE: **{metrics['baseline_files']}**",
        f"- Baseline size: **{_gib(metrics['baseline_bytes'])}**",
        f"- Full SHA-256 available: **{metrics['hashed_baseline_files']}**",
        f"- Blocked without full SHA-256: **{metrics['unhashed_baseline_files']}**",
        f"- Logical exact-content groups: **{metrics['content_groups']}**", "",
        "## Exact matching", "",
        f"- Performed: **{'no' if args.skip_exact_matching else 'yes'}**",
        f"- Baseline-only groups: **{metrics['baseline_only_groups']}**",
        f"- Groups matching historical NAS copies: **{metrics['historical_duplicate_groups']}**",
        f"- Duplicate groups across baseline and historical zones: **{metrics['all_zone_duplicate_groups']}**",
        f"- Duplicate groups only inside the baseline: **{metrics['baseline_duplicate_groups']}**",
        f"- Blocked groups: **{metrics['blocked_groups']}**", "",
        "## Potential physical space recovery (upper bounds)", "",
        f"- Historical NAS copies: **{_gib(metrics['historical_reclaimable_bytes_upper_bound'])}**",
        f"- Duplicate copies inside baseline: **{_gib(metrics['baseline_internal_reclaimable_bytes_upper_bound'])}**",
        f"- Maximum with one physical copy retained per exact group: **{_gib(metrics['maximum_reclaimable_bytes_upper_bound'])}**", "",
        "These figures are upper bounds, not deletion approval. Filesystem metadata, retention, sensitivity,",
        "version history, fallback, and restore evidence still require review.", "",
        "## Safety", "",
        "- The OneDrive baseline is protected and no baseline file is proposed for automatic deletion.",
        "- Full SHA-256 plus size is the only exact-duplicate proof used by this assessment.",
        "- Similar names, timestamps, partial hashes, and classifications never authorize deletion.",
        "- `execution_authorized` is false for every row.",
        "- No file, directory, database row, snapshot, backup, or Cloud Sync setting was changed.", "",
        "## Outputs", "",
        f"- Full manifest: `{manifest_path.name}`",
        f"- Activity selection: `{activity_path.name}`",
        f"- Compact review: `{review_path.name}`",
    ]
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    (export_dir / "onedrive-baseline-latest.md").write_text(
        report_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    print("SCRUM-76 read-only OneDrive baseline assessment complete")
    print(f"Report: {report_path.relative_to(PROJECT_ROOT)}")
    print(f"Manifest: {manifest_path.relative_to(PROJECT_ROOT)}")
    print(f"Activity selection: {activity_path.relative_to(PROJECT_ROOT)}")
    print(f"Compact review: {review_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
