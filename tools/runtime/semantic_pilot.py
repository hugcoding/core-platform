#!/usr/bin/env python3
"""Build a read-only local semantic pilot manifest from recent OneDrive golden records."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.exports.csv_format import write_dict_rows
from core.semantic.pilot_selection import build_manifest, parse_timestamp, select_candidates
from tools.runtime.migration_inventory import run_query, shutil_which

DEFAULT_SOURCE = "/volume1/data/import/cloud/onedrive/current"
QUERY = r"""
SELECT f.id AS file_id, f.path, f.filename,
       LOWER(COALESCE(f.extension, '')) AS extension,
       f.size_bytes, f.content_sha256, f.modified_at_fs,
       cg.id AS content_group_id, cg.golden_file_id
FROM files f
LEFT JOIN content_groups cg ON cg.golden_file_id = f.id
WHERE f.deleted_at IS NULL
  AND (f.path = :'source' OR f.path LIKE :'source_prefix')
ORDER BY f.path, f.id;
"""
REVIEW_FIELDS = [
    "file_id", "content_group_id", "path", "extension", "size_bytes",
    "modified_at_fs", "pilot_category", "selection_status", "selection_reason",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare a read-only OneDrive golden semantic pilot.")
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--cutoff", required=True, help="Inclusive ISO timestamp for filesystem modification")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.source.rstrip("/")
    if not source.startswith("/volume1/") or source == "/volume1/data":
        print("Source must be an absolute path below /volume1 and may not be /volume1/data.", file=sys.stderr)
        return 2
    if not 1 <= args.limit <= 500:
        print("Limit must be between 1 and 500.", file=sys.stderr)
        return 2
    try:
        cutoff = parse_timestamp(args.cutoff)
    except ValueError:
        print("Cutoff must be a valid ISO 8601 timestamp.", file=sys.stderr)
        return 2

    docker = os.getenv("DOCKER_BIN", "docker")
    if docker == "docker" and not shutil_which(docker) and Path("/usr/local/bin/docker").exists():
        docker = "/usr/local/bin/docker"
    command = [docker, "exec", os.getenv("POSTGRES_CONTAINER", "postgres"), "psql",
               "-U", os.getenv("DB_USER", "hugo"), "-d", os.getenv("DB_NAME", "nasdb_test")]
    try:
        rows = list(csv.DictReader(io.StringIO(run_query(command, QUERY, source))))
    except KeyboardInterrupt:
        print("\nSemantic pilot cancelled; nothing was changed.", file=sys.stderr)
        return 130
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Semantic pilot failed: {exc}", file=sys.stderr)
        return 1
    if not rows:
        print("Semantic pilot failed: no active CORE files found below source.", file=sys.stderr)
        return 1

    selected, excluded = select_candidates(rows, cutoff=cutoff, limit=args.limit)
    generated_at = datetime.now(timezone.utc)
    timestamp = generated_at.astimezone().strftime("%Y%m%d-%H%M%S")
    export_dir = PROJECT_ROOT / "project" / "exports" / "semantic-pilot"
    export_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = export_dir / f"onedrive-golden-pilot-{timestamp}.json"
    review_path = export_dir / f"onedrive-golden-pilot-review-{timestamp}.csv"
    report_path = export_dir / f"onedrive-golden-pilot-{timestamp}.md"
    manifest_path.write_text(json.dumps(build_manifest(selected, source=source, cutoff=cutoff, generated_at=generated_at), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_dict_rows(review_path, ({field: row.get(field, "") for field in REVIEW_FIELDS} for row in [*selected, *excluded]), REVIEW_FIELDS)
    reasons = Counter(row["selection_reason"] for row in excluded)
    categories = Counter(row["pilot_category"] for row in selected)
    report = [
        "# SCRUM-59 OneDrive golden semantic pilot", "",
        f"- Generated: `{generated_at.isoformat()}`", f"- Source: `{source}`",
        f"- Recent cutoff: `{cutoff.isoformat()}`", f"- Selected golden records: **{len(selected)}**",
        f"- Pilot limit: **{args.limit}**", "- Mode: **read-only, local-only dry-run**",
        "- Embeddings: **disabled**", "- External AI: **disabled**", "- Database writes: **disabled**", "",
        "## Selected categories", "",
        *[f"- `{category}`: **{categories.get(category, 0)}**" for category in ("study", "work", "administration", "general")], "",
        "## Exclusions", "",
        *[f"- `{reason}`: **{count}**" for reason, count in sorted(reasons.items())], "",
        "Mutation time only limits the recent pilot corpus; it never influences golden-record selection.",
        "Sensitive paths are conservatively excluded by category. Unsupported formats are counted before missing hashes.",
        "The manifest contains metadata but no extracted text.",
        "No files, directories, database rows, vectors, or external services were changed.", "",
        "## Outputs", "", f"- Manifest: `{manifest_path.name}`", f"- Review: `{review_path.name}`",
    ]
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    (export_dir / "onedrive-golden-pilot-latest.md").write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")
    print("SCRUM-59 read-only semantic pilot manifest complete")
    print(f"Report: {report_path.relative_to(PROJECT_ROOT)}")
    print(f"Manifest: {manifest_path.relative_to(PROJECT_ROOT)}")
    print(f"Review: {review_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
