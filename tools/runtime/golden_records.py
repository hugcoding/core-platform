#!/usr/bin/env python3
"""Generate a read-only golden-record proposal for exact document duplicates."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path, PurePosixPath

from tools.runtime.migration_inventory import run_query, shutil_which


QUERY = r"""
SELECT
    id AS file_id,
    path,
    filename,
    LOWER(COALESCE(extension, '')) AS extension,
    size_bytes,
    hash_content,
    mime_type,
    created_at,
    updated_at
FROM files
WHERE deleted_at IS NULL
  AND (path = :'source' OR path LIKE :'source_prefix')
  AND hash_content IS NOT NULL
  AND hash_content <> ''
  AND LOWER(COALESCE(extension, '')) IN
      ('doc', 'docx', 'odt', 'rtf', 'txt', 'md', 'pdf',
       'xls', 'xlsx', 'ods', 'csv', 'ppt', 'pptx', 'odp')
ORDER BY hash_content, size_bytes, path, id;
"""

LOW_VALUE_PATH_PARTS = {
    "cache",
    "temp",
    "tmp",
    "tijdelijk",
    "cloudstation",
    "backup",
    "backups",
    "archief",
    "archive",
    "export",
    "exports",
}


def candidate_score(row: dict[str, str]) -> tuple[int, list[str]]:
    path = PurePosixPath(row["path"])
    evidence = f"/{'/'.join(path.parts)}/".casefold()
    name = path.name.casefold()
    score = 100
    reasons = ["full content hash available"]

    penalties = sorted(part for part in LOW_VALUE_PATH_PARTS if f"/{part}/" in evidence)
    if penalties:
        score -= 8 * len(penalties)
        reasons.append("legacy/path penalty: " + ", ".join(penalties))
    if re.search(r"(?:^|[\s_-])(kopie|copy|backup)(?:[\s_.()-]|$)", name):
        score -= 12
        reasons.append("copy-like filename penalty")
    if re.search(r"\(\d+\)(?=\.[^.]+$)", name):
        score -= 6
        reasons.append("numbered duplicate filename penalty")
    if name.startswith("~$") or name.endswith((".tmp", ".part")):
        score -= 30
        reasons.append("temporary filename penalty")
    if row.get("updated_at"):
        score += 2
        reasons.append("update timestamp available")
    if row.get("created_at"):
        score += 1
        reasons.append("creation timestamp available")
    return score, reasons


def choose_golden(group: list[dict[str, str]]) -> dict[str, str]:
    ranked = []
    for row in group:
        score, reasons = candidate_score(row)
        ranked.append((score, len(row["path"]), row["path"].casefold(), row, reasons))
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    best_score, _, _, best, best_reasons = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else None
    margin = best_score - second_score if second_score is not None else best_score
    if len(ranked) == 1:
        confidence, status = "high", "single_source"
    elif margin >= 8:
        confidence, status = "high", "golden_proposed"
    elif margin > 0:
        confidence, status = "medium", "golden_proposed"
    else:
        confidence, status = "low", "golden_record_review_required"

    alternatives = [
        {
            "file_id": item[3]["file_id"],
            "path": item[3]["path"],
            "score": item[0],
        }
        for item in ranked[1:]
    ]
    return {
        "hash_content": best["hash_content"],
        "size_bytes": best["size_bytes"],
        "copy_count": str(len(group)),
        "golden_file_id": best["file_id"],
        "golden_path": best["path"],
        "golden_score": str(best_score),
        "score_margin": str(margin),
        "confidence": confidence,
        "selection_status": status,
        "selection_reasons": json.dumps(best_reasons, ensure_ascii=False),
        "alternative_sources": json.dumps(alternatives, ensure_ascii=False),
        "proposed_target_path": "",
        "target_classification_status": "pending_content_classification",
    }


def build_manifest(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row["hash_content"], row["size_bytes"])].append(row)
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
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(manifest[0]))
            writer.writeheader()
            writer.writerows(selected)

    write(manifest_path, manifest)
    review = [row for row in manifest if row["selection_status"] == "golden_record_review_required"]
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
        f"- Handmatige golden-recordreview: **{len(review)}**",
        "",
        "Er zijn geen bestanden, mappen of databaserecords gewijzigd.",
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
