#!/usr/bin/env python3
"""Generate a read-only golden-record proposal for exact document duplicates."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from core.integrity.golden_record import (
    ALGORITHM_VERSION, comparison_confidence, rank_candidates, selection_metadata,
)
from core.exports.csv_format import write_dict_rows

from tools.runtime.migration_inventory import run_query, shutil_which


QUERY = r"""
SELECT
    f.id AS file_id,
    f.path,
    f.filename,
    LOWER(COALESCE(f.extension, '')) AS extension,
    f.size_bytes,
    f.content_sha256,
    f.mime_type,
    f.created_at,
    f.updated_at,
    cg.golden_file_id AS existing_golden_file_id,
    cg.algorithm_version AS existing_algorithm_version
FROM files f
LEFT JOIN content_groups cg
  ON cg.content_sha256 = f.content_sha256
 AND cg.size_bytes IS NOT DISTINCT FROM f.size_bytes
WHERE f.deleted_at IS NULL
  AND (f.path = :'source' OR f.path LIKE :'source_prefix')
  AND f.content_sha256 IS NOT NULL
  AND f.content_sha256 <> ''
  AND f.size_bytes > 0
  AND LOWER(COALESCE(f.extension, '')) IN
      ('doc', 'docx', 'odt', 'rtf', 'txt', 'md', 'pdf',
       'xls', 'xlsx', 'ods', 'csv', 'ppt', 'pptx', 'odp')
ORDER BY f.content_sha256, f.size_bytes, f.path, f.id;
"""

EMPTY_QUERY = r"""
SELECT
    id AS file_id, path, filename, LOWER(COALESCE(extension, '')) AS extension,
    size_bytes, content_sha256, mime_type, created_at, updated_at,
    'empty_file' AS review_category,
    'excluded_from_golden_selection' AS selection_status
FROM files
WHERE deleted_at IS NULL
  AND (path = :'source' OR path LIKE :'source_prefix')
  AND size_bytes = 0
ORDER BY path, id;
"""

MANIFEST_FIELDS = [
    "content_sha256", "size_bytes", "copy_count", "golden_file_id",
    "golden_path", "golden_score", "score_margin", "confidence",
    "golden_selection_confidence", "golden_comparison_confidence", "review_reason",
    "eligibility_status", "exact_match_basis",
    "content_integrity_status", "selection_quality_scope", "provenance_quality_score",
    "existing_golden_file_id", "existing_algorithm_version", "selection_change",
    "selection_status", "selection_reasons", "alternative_sources",
    "proposed_target_path", "target_classification_status",
]
EMPTY_FIELDS = [
    "file_id", "path", "filename", "extension", "size_bytes",
    "content_sha256", "mime_type", "created_at", "updated_at",
    "review_category", "selection_status",
]

def candidate_score(row: dict[str, str]) -> tuple[int, list[str]]:
    ranked = rank_candidates([{**row, "file_id": row.get("file_id", "0")}])
    return ranked[0]["selection_score"], ranked[0]["selection_reasons"]


def choose_golden(group: list[dict[str, str]]) -> dict[str, str]:
    ranked = rank_candidates(group)
    best = ranked[0]
    confidence, status, margin = selection_metadata(ranked)

    alternatives = [
        {
            "file_id": item["file_id"],
            "path": item["path"],
            "score": item["selection_score"],
            "provenance_quality_score": item["provenance_quality_score"],
            "selection_reasons": item["selection_reasons"],
        }
        for item in ranked[1:]
    ]
    existing_golden = next(
        (row.get("existing_golden_file_id") for row in group if row.get("existing_golden_file_id")),
        "",
    )
    existing_version = next(
        (row.get("existing_algorithm_version") for row in group if row.get("existing_algorithm_version")),
        "",
    )
    assessed_ids = {str(row["file_id"]) for row in group}
    selection_change = (
        "new_proposal" if not existing_golden
        else "persisted_golden_outside_assessment_scope"
        if str(existing_golden) not in assessed_ids
        else "unchanged" if str(existing_golden) == str(best["file_id"])
        else "golden_change_review"
    )
    comparison = comparison_confidence(confidence, status)
    review_reason = (
        "persisted_golden_would_change" if selection_change == "golden_change_review"
        else "persisted_golden_outside_assessment_scope"
        if selection_change == "persisted_golden_outside_assessment_scope"
        else "deterministic_tiebreak_between_exact_copies" if comparison == "low"
        else "provenance_margin_requires_review" if comparison == "medium"
        else "no_persisted_golden" if selection_change == "new_proposal"
        else "not_required"
    )
    return {
        "content_sha256": best["content_sha256"],
        "size_bytes": best["size_bytes"],
        "copy_count": str(len(group)),
        "golden_file_id": best["file_id"],
        "golden_path": best["path"],
        "golden_score": str(best["selection_score"]),
        "score_margin": str(margin),
        "confidence": confidence,
        "golden_selection_confidence": confidence,
        "golden_comparison_confidence": comparison,
        "review_reason": review_reason,
        "eligibility_status": best["eligibility_status"],
        "exact_match_basis": best["exact_match_basis"],
        "content_integrity_status": best["content_integrity_status"],
        "selection_quality_scope": best["selection_quality_scope"],
        "provenance_quality_score": str(best["provenance_quality_score"]),
        "existing_golden_file_id": str(existing_golden),
        "existing_algorithm_version": str(existing_version),
        "selection_change": selection_change,
        "selection_status": status,
        "selection_reasons": json.dumps(best["selection_reasons"], ensure_ascii=False),
        "alternative_sources": json.dumps(alternatives, ensure_ascii=False),
        "proposed_target_path": "",
        "target_classification_status": "pending_content_classification",
    }


def build_manifest(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row["content_sha256"], row["size_bytes"])].append(row)
    return [choose_golden(group) for _, group in sorted(groups.items())]


def needs_review(row: dict[str, str]) -> bool:
    return (
        row["golden_comparison_confidence"] in {"medium", "low"}
        or row["selection_change"] != "unchanged"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a read-only golden-record proposal.")
    parser.add_argument("--source", required=True, help="Absolute source path below /volume1")
    parser.add_argument("--dry-run", action="store_true", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.source.rstrip("/")
    if not source.startswith("/volume1/") or source == "/volume1/data":
        print("Source must be below /volume1 and may not be /volume1/data.", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parents[2]
    docker = os.getenv("DOCKER_BIN", "docker")
    if docker == "docker" and not shutil_which(docker) and Path("/usr/local/bin/docker").exists():
        docker = "/usr/local/bin/docker"
    command = [
        docker,
        "exec",
        os.getenv("POSTGRES_CONTAINER", "postgres"),
        "psql",
        "-U",
        os.getenv("DB_USER", "hugo"),
        "-d",
        os.getenv("DB_NAME", "nasdb_test"),
    ]
    try:
        rows = list(csv.DictReader(io.StringIO(run_query(command, QUERY, source))))
        empty_rows = list(csv.DictReader(io.StringIO(run_query(command, EMPTY_QUERY, source))))
    except KeyboardInterrupt:
        print("\nGolden-record proposal cancelled; nothing was changed.", file=sys.stderr)
        return 130
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Golden-record proposal failed: {exc}", file=sys.stderr)
        return 1
    if not rows and not empty_rows:
        print("Golden-record proposal failed: no eligible or empty files found.", file=sys.stderr)
        return 1

    manifest = build_manifest(rows)
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    export_dir = root / "project" / "exports" / "migration-inventory"
    export_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = export_dir / f"golden-records-{timestamp}.csv"
    review_path = export_dir / f"golden-record-review-{timestamp}.csv"
    empty_path = export_dir / f"golden-record-empty-files-{timestamp}.csv"
    report_path = export_dir / f"golden-records-{timestamp}.md"

    write_dict_rows(manifest_path, manifest, MANIFEST_FIELDS)
    review = [row for row in manifest if needs_review(row)]
    write_dict_rows(review_path, review, MANIFEST_FIELDS)
    write_dict_rows(empty_path, empty_rows, EMPTY_FIELDS)
    duplicate_groups = sum(row["copy_count"] != "1" for row in manifest)
    report = [
        "# SCRUM-61 golden-recordvoorstel",
        "",
        f"- Gegenereerd: `{datetime.now().astimezone().isoformat()}`",
        f"- Bron: `{source}`",
        f"- Golden-algoritme: `{ALGORITHM_VERSION}`",
        "- Modus: **alleen-lezen dry-run**",
        f"- Unieke inhoudsgroepen: **{len(manifest)}**",
        f"- Groepen met meerdere bronbestanden: **{duplicate_groups}**",
        f"- Golden records met lage zekerheid: **{sum(row['confidence'] == 'low' for row in manifest)}**",
        f"- Medium-confidence duplicaatkeuzes: **{sum(row['golden_comparison_confidence'] == 'medium' for row in manifest)}**",
        f"- Single-source groepen (vergelijkingsconfidence n.v.t.): **{sum(row['golden_comparison_confidence'] == 'not_applicable' for row in manifest)}**",
        f"- Bestaande golden-keuzes die zouden wijzigen: **{sum(row['selection_change'] == 'golden_change_review' for row in manifest)}**",
        f"- Persisted golden records buiten de gekozen bronscope: **{sum(row['selection_change'] == 'persisted_golden_outside_assessment_scope' for row in manifest)}**",
        f"- Lege bestanden buiten golden-selectie: **{len(empty_rows)}**",
        "",
        "Er zijn geen bestanden, mappen of databaserecords gewijzigd.",
        "Iedere inhoudsgroep heeft precies één deterministisch golden record.",
        "Doelpaden blijven leeg totdat inhoudsgestuurde classificatie is uitgevoerd.",
        "Exact-matchbewijs en golden-selection-confidence zijn afzonderlijke velden.",
        "De score vergelijkt alleen provenancekwaliteit; CORE-observatietijden tellen niet mee.",
        "Lege bestanden blijven geinventariseerd en staan apart in de empty-file-review.",
    ]
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("SCRUM-61 read-only golden-record proposal complete")
    print(f"Report: {report_path.relative_to(root)}")
    print(f"Manifest: {manifest_path.relative_to(root)}")
    print(f"Review: {review_path.relative_to(root)}")
    print(f"Empty files: {empty_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
