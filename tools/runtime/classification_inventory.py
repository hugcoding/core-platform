#!/usr/bin/env python3
"""Create a read-only content-classification inventory from persisted golden records."""

from __future__ import annotations

import argparse
import csv
import io
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from core.exports.csv_format import write_dict_rows
from tools.runtime.migration_inventory import run_query, shutil_which


QUERY = r"""
SELECT
    g.id AS content_group_id,
    g.content_sha256,
    g.size_bytes,
    g.golden_file_id,
    f.filename,
    f.extension,
    f.mime_type,
    f.path AS golden_path,
    g.confidence AS golden_confidence,
    g.selection_status AS golden_selection_status,
    g.algorithm_version AS golden_algorithm_version,
    COUNT(m.file_id) AS physical_copy_count,
    JSON_AGG(
        JSON_BUILD_OBJECT(
            'file_id', member_file.id,
            'path', member_file.path,
            'filesystem_mtime_epoch', member_file.modified_at_fs,
            'core_first_seen_at', member_file.created_at,
            'core_updated_at', member_file.updated_at
        )
        ORDER BY m.selection_rank
    )::text AS member_time_evidence
FROM content_groups g
JOIN files f ON f.id = g.golden_file_id
JOIN content_group_members m ON m.content_group_id = g.id
JOIN files member_file ON member_file.id = m.file_id
WHERE f.deleted_at IS NULL
  AND (f.path = :'source' OR f.path LIKE :'source_prefix')
GROUP BY
    g.id, g.content_sha256, g.size_bytes, g.golden_file_id,
    f.filename, f.extension, f.mime_type, f.path,
    g.confidence, g.selection_status, g.algorithm_version
ORDER BY f.path, g.id;
"""

ROUTES = {
    "docx": "python-docx", "pdf": "pypdf", "txt": "plain-text",
    "md": "plain-text", "csv": "plain-text", "xlsx": "openpyxl",
    "pptx": "python-pptx", "odt": "odf", "ods": "odf", "odp": "odf",
    "rtf": "rtf", "doc": "legacy-office-conversion",
    "xls": "legacy-office-conversion", "ppt": "legacy-office-conversion",
}


def classify_route(row: dict[str, str]) -> tuple[str, str]:
    route = ROUTES.get((row.get("extension") or "").casefold(), "manual-review")
    if route == "legacy-office-conversion":
        return route, "conversion_required"
    if route == "manual-review":
        return route, "unsupported"
    return route, "ready_for_local_extraction"


def build_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result = []
    for row in rows:
        route, status = classify_route(row)
        result.append(
            {
                **row,
                "extraction_route": route,
                "extraction_status": status,
                "processing_scope": "local_only_no_embeddings",
                "content_category": "pending_content_extraction",
                "category_confidence": "",
                "category_reasons": "",
                "proposed_target_path": "",
            }
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a golden-record classification inventory.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--dry-run", action="store_true", required=True)
    args = parser.parse_args(argv)
    source = args.source.rstrip("/")
    if not source.startswith("/volume1/") or source == "/volume1/data":
        print("Source must be below /volume1 and may not be /volume1/data.", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parents[2]
    docker = os.getenv("DOCKER_BIN", "docker")
    if docker == "docker" and not shutil_which(docker) and Path("/usr/local/bin/docker").exists():
        docker = "/usr/local/bin/docker"
    command = [
        docker, "exec", os.getenv("POSTGRES_CONTAINER", "postgres"), "psql",
        "-U", os.getenv("DB_USER", "hugo"), "-d", os.getenv("DB_NAME", "nasdb_test"),
    ]
    try:
        database_rows = list(csv.DictReader(io.StringIO(run_query(command, QUERY, source))))
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Classification inventory failed: {exc}", file=sys.stderr)
        return 1
    if not database_rows:
        print("Classification inventory failed: no persisted golden records found.", file=sys.stderr)
        return 1

    inventory = build_rows(database_rows)
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    export_dir = root / "project" / "exports" / "migration-inventory"
    export_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = export_dir / f"classification-inventory-{timestamp}.csv"
    report_path = export_dir / f"classification-inventory-{timestamp}.md"
    write_dict_rows(manifest_path, inventory, list(inventory[0]))
    routes = Counter(row["extraction_route"] for row in inventory)
    statuses = Counter(row["extraction_status"] for row in inventory)
    report = [
        "# SCRUM-61 inhoudsclassificatie-inventaris", "",
        f"- Gegenereerd: `{datetime.now().astimezone().isoformat()}`",
        f"- Bron: `{source}`", "- Modus: **alleen-lezen dry-run**",
        f"- Golden records: **{len(inventory)}**",
        f"- Direct lokaal extraheerbaar: **{statuses['ready_for_local_extraction']}**",
        f"- Conversie vereist: **{statuses['conversion_required']}**",
        f"- Niet ondersteund/handmatige review: **{statuses['unsupported']}**",
        "", "## Extractieroutes", "", "| Route | Bestanden |", "|---|---:|",
    ]
    report.extend(f"| `{route}` | {count} |" for route, count in sorted(routes.items()))
    report.extend([
        "", "Alle categorieën en doelpaden blijven pending totdat inhoud is geëxtraheerd.",
        "Embeddings en externe AI-verwerking zijn uitgeschakeld.",
        "Er zijn geen bestanden, mappen of databaserecords gewijzigd.",
    ])
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("SCRUM-61 read-only classification inventory complete")
    print(f"Report: {report_path.relative_to(root)}")
    print(f"Manifest: {manifest_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
