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

from core.integrity.golden_record import rank_candidates, selection_metadata
from core.exports.csv_format import write_dict_rows

from tools.runtime.migration_inventory import run_query, shutil_which


QUERY = r"""
SELECT
    id AS file_id,
    path,
    filename,
    LOWER(COALESCE(extension, '')) AS extension,
    size_bytes,
    content_sha256,
    mime_type,
    created_at,
    updated_at
FROM files
WHERE deleted_at IS NULL
  AND (path = :'source' OR path LIKE :'source_prefix')
  AND content_sha256 IS NOT NULL
  AND content_sha256 <> ''
  AND LOWER(COALESCE(extension, '')) IN
      ('doc', 'docx', 'odt', 'rtf', 'txt', 'md', 'pdf',
       'xls', 'xlsx', 'ods', 'csv', 'ppt', 'pptx', 'odp')
ORDER BY content_sha256, size_bytes, path, id;
"""

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
        }
        for item in ranked[1:]
    ]
    return {
        "content_sha256": best["content_sha256"],
        "size_bytes": best["size_bytes"],
        "copy_count": str(len(group)),
        "golden_file_id": best["file_id"],
        "golden_path": best["path"],
        "golden_score": str(best["selection_score"]),
        "score_margin": str(margin),
        "confidence": confidence,
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
    except KeyboardInterrupt:
        print("\nGolden-record proposal cancelled; nothing was changed.", file=sys.stderr)
        return 130
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Golden-record proposal failed: {exc}", file=sys.stderr)
        return 1
    if not rows:
        print("Golden-record proposal failed: no hashed documents found.", file=sys.stderr)
        return 1

    manifest = build_manifest(rows)
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    export_dir = root / "project" / "exports" / "migration-inventory"
    export_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = export_dir / f"golden-records-{timestamp}.csv"
    review_path = export_dir / f"golden-record-review-{timestamp}.csv"
    report_path = export_dir / f"golden-records-{timestamp}.md"

    def write(path: Path, selected: list[dict[str, str]]) -> None:
        write_dict_rows(path, selected, list(manifest[0]))

    write(manifest_path, manifest)
    review = [row for row in manifest if row["confidence"] == "low"]
    write(review_path, review)
    duplicate_groups = sum(row["copy_count"] != "1" for row in manifest)
    report = [
        "# SCRUM-61 golden-recordvoorstel",
        "",
        f"- Gegenereerd: `{datetime.now().astimezone().isoformat()}`",
        f"- Bron: `{source}`",
        "- Modus: **alleen-lezen dry-run**",
        f"- Unieke inhoudsgroepen: **{len(manifest)}**",
        f"- Groepen met meerdere bronbestanden: **{duplicate_groups}**",
        f"- Golden records met lage zekerheid: **{len(review)}**",
        "",
        "Er zijn geen bestanden, mappen of databaserecords gewijzigd.",
        "Iedere inhoudsgroep heeft precies één deterministisch golden record.",
        "Doelpaden blijven leeg totdat inhoudsgestuurde classificatie is uitgevoerd.",
    ]
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("SCRUM-61 read-only golden-record proposal complete")
    print(f"Report: {report_path.relative_to(root)}")
    print(f"Manifest: {manifest_path.relative_to(root)}")
    print(f"Review: {review_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
