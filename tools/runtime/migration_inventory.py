#!/usr/bin/env python3
"""Generate a read-only SCRUM-61 migration inventory from PostgreSQL."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


CLASSIFICATION_CTE = r"""
WITH source_files AS (
    SELECT
        f.*,
        LOWER(COALESCE(f.extension, '')) AS ext,
        CASE
            WHEN f.path ~* '(^|/)(@eaDir|#recycle|\$RECYCLE\.BIN|__pycache__|node_modules|\.git|\.cache|cache|tmp|temp)(/|$)'
                 OR LOWER(COALESCE(f.extension, '')) IN
                    ('tmp', 'temp', 'crdownload', 'part', 'pyc', 'pyo', 'swp', 'lock')
                THEN 'system_or_temporary'
            WHEN LOWER(COALESCE(f.extension, '')) IN
                    ('key', 'pem', 'p12', 'pfx', 'ovpn', 'kdbx')
                THEN 'secret'
            WHEN LOWER(COALESCE(f.extension, '')) IN
                    ('exe', 'msi', 'dll', 'sys', 'com', 'bat', 'cmd', 'iso', 'img',
                     'vdi', 'vmdk', 'ova', 'dmp', 'dump')
                THEN 'software_or_system_artifact'
            WHEN LOWER(COALESCE(f.extension, '')) IN
                    ('doc', 'docx', 'odt', 'rtf', 'txt', 'md', 'pdf',
                     'xls', 'xlsx', 'ods', 'csv', 'ppt', 'pptx', 'odp')
                THEN 'personal_document_candidate'
            WHEN LOWER(COALESCE(f.extension, '')) IN
                    ('jpg', 'jpeg', 'png', 'gif', 'bmp', 'tif', 'tiff', 'heic',
                     'mp3', 'wav', 'flac', 'm4a', 'mp4', 'mkv', 'avi', 'mov', 'mts')
                THEN 'personal_media_candidate'
            WHEN LOWER(COALESCE(f.extension, '')) IN
                    ('zip', '7z', 'rar', 'tar', 'gz', 'bz2', 'xz')
                THEN 'archive_review'
            ELSE 'unknown'
        END AS category,
        CASE
            WHEN f.path ~* '(^|/)(salaris|belasting|financi[eë]n|bank|paspoort|identiteit|medisch|zorg|personeel|sollicitat|cv)(/|$)'
              OR f.filename ~* '(salaris|jaaropgave|belasting|aanslag|paspoort|identiteit|medisch|bank|rekening|curriculum|sollicitat)'
                THEN 'sensitive'
            ELSE 'normal'
        END AS sensitivity
    FROM files f
    WHERE f.deleted_at IS NULL
      AND (f.path = :'source' OR f.path LIKE :'source_prefix')
),
classified AS (
    SELECT
        sf.*,
        CASE
            WHEN sf.category IN ('system_or_temporary', 'secret', 'software_or_system_artifact')
                THEN 'excluded'
            WHEN sf.hash_content IS NULL OR sf.hash_content = ''
                THEN 'review_required'
            WHEN sf.category IN ('personal_document_candidate', 'personal_media_candidate')
                THEN 'candidate'
            ELSE 'review_required'
        END AS migration_action,
        CASE
            WHEN sf.hash_content IS NULL OR sf.hash_content = ''
                THEN 'UNHASHED:' || sf.id::text
            ELSE sf.hash_content || ':' || COALESCE(sf.size_bytes::text, 'NULL')
        END AS content_key
    FROM source_files sf
)
"""


DETAIL_QUERY = CLASSIFICATION_CTE + r"""
, grouped AS (
    SELECT
        content_key,
        MIN(hash_content) AS hash_content,
        MIN(size_bytes) AS size_bytes,
        CASE
            WHEN BOOL_OR(category = 'system_or_temporary') THEN 'system_or_temporary'
            WHEN BOOL_OR(category = 'secret') THEN 'secret'
            WHEN BOOL_OR(category = 'software_or_system_artifact') THEN 'software_or_system_artifact'
            WHEN BOOL_OR(category = 'personal_document_candidate') THEN 'personal_document_candidate'
            WHEN BOOL_OR(category = 'personal_media_candidate') THEN 'personal_media_candidate'
            WHEN BOOL_OR(category = 'archive_review') THEN 'archive_review'
            ELSE 'unknown'
        END AS category,
        CASE WHEN BOOL_OR(sensitivity = 'sensitive') THEN 'sensitive' ELSE 'normal' END AS sensitivity,
        CASE
            WHEN BOOL_OR(migration_action = 'excluded') THEN 'excluded'
            WHEN BOOL_OR(migration_action = 'review_required') THEN 'review_required'
            ELSE 'candidate'
        END AS migration_action,
        COUNT(*) AS source_copy_count,
        (ARRAY_AGG(id ORDER BY LENGTH(path), path, id))[1] AS representative_file_id,
        (ARRAY_AGG(path ORDER BY LENGTH(path), path, id))[1] AS representative_path,
        ARRAY_TO_JSON(ARRAY_AGG(path ORDER BY path))::text AS source_paths
    FROM classified
    GROUP BY content_key
)
SELECT
    g.representative_file_id,
    g.hash_content,
    g.size_bytes,
    g.category,
    g.sensitivity,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM files target
            WHERE target.deleted_at IS NULL
              AND target.hash_content = g.hash_content
              AND target.size_bytes IS NOT DISTINCT FROM g.size_bytes
              AND (target.path = '/volume1/data' OR target.path LIKE '/volume1/data/%')
        ) THEN 'already_in_target'
        ELSE g.migration_action
    END AS migration_action,
    g.source_copy_count,
    (
        SELECT COUNT(*) FROM files all_files
        WHERE all_files.deleted_at IS NULL
          AND all_files.hash_content = g.hash_content
          AND all_files.size_bytes IS NOT DISTINCT FROM g.size_bytes
    ) AS active_copy_count,
    g.representative_path,
    g.source_paths,
    CASE
        WHEN g.hash_content IS NULL OR g.hash_content = '' THEN 'content hash missing'
        WHEN g.migration_action = 'excluded' THEN 'matched conservative exclusion rule'
        WHEN g.sensitivity = 'sensitive' THEN 'candidate; separate semantic-access policy required'
        WHEN g.source_copy_count > 1 THEN 'exact duplicate content within source'
        ELSE 'hashed candidate requiring review'
    END AS decision_reason
FROM grouped g
ORDER BY
    CASE g.migration_action WHEN 'candidate' THEN 1 WHEN 'review_required' THEN 2 ELSE 3 END,
    g.category,
    g.representative_path;
"""


SUMMARY_QUERY = CLASSIFICATION_CTE + r"""
SELECT
    category,
    migration_action,
    sensitivity,
    COUNT(*) AS file_count,
    COUNT(DISTINCT content_key) AS content_groups,
    COALESCE(SUM(size_bytes), 0)::bigint AS total_bytes
FROM classified
GROUP BY category, migration_action, sensitivity
ORDER BY migration_action, category, sensitivity;
"""


def parse_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_query(command: list[str], query: str, source: str) -> str:
    source_prefix = source.rstrip("/") + "/%"
    rendered_query = query.replace(":'source_prefix'", sql_literal(source_prefix))
    rendered_query = rendered_query.replace(":'source'", sql_literal(source))
    result = subprocess.run(
        command
        + [
            "-v",
            "ON_ERROR_STOP=1",
            "--csv",
            "-c",
            rendered_query,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a read-only migration inventory.")
    parser.add_argument("--source", required=True, help="Absolute source path below /volume1")
    parser.add_argument("--dry-run", action="store_true", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.source.rstrip("/")
    if not source.startswith("/volume1/") or source == "/volume1/data":
        print("Source must be an absolute path below /volume1 and may not be /volume1/data.", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parents[2]
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    export_dir = root / "project" / "exports" / "migration-inventory"
    export_dir.mkdir(parents=True, exist_ok=True)

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
        detail_text = run_query(command, DETAIL_QUERY, source)
        summary_text = run_query(command, SUMMARY_QUERY, source)
    except subprocess.CalledProcessError as exc:
        print("Migration inventory failed.", file=sys.stderr)
        if exc.stderr:
            print(exc.stderr.strip(), file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"Migration inventory failed: {exc}", file=sys.stderr)
        return 1

    detail_path = export_dir / f"manifest-{timestamp}.csv"
    summary_path = export_dir / f"summary-{timestamp}.csv"
    report_path = export_dir / f"migration-inventory-{timestamp}.md"
    detail_path.write_text(detail_text, encoding="utf-8")
    summary_path.write_text(summary_text, encoding="utf-8")

    details = parse_csv(detail_text)
    summary = parse_csv(summary_text)
    actions: dict[str, int] = {}
    for row in details:
        action = row["migration_action"]
        actions[action] = actions.get(action, 0) + 1

    report = [
        "# SCRUM-61 migration inventory",
        "",
        f"- Generated: `{datetime.now().astimezone().isoformat()}`",
        f"- Source: `{source}`",
        "- Target: `/volume1/data`",
        "- Mode: **read-only dry-run**",
        f"- Content groups: **{len(details)}**",
        f"- Candidate groups: **{actions.get('candidate', 0)}**",
        f"- Review-required groups: **{actions.get('review_required', 0)}**",
        f"- Excluded groups: **{actions.get('excluded', 0)}**",
        f"- Already in target: **{actions.get('already_in_target', 0)}**",
        "",
        "No files or database records were changed. `candidate` is not approval to copy or delete.",
        "",
        "## Classification summary",
        "",
        "| Category | Action | Sensitivity | Files | Content groups | Bytes |",
        "|---|---|---|---:|---:|---:|",
    ]
    for row in summary:
        report.append(
            f"| {row['category']} | {row['migration_action']} | {row['sensitivity']} "
            f"| {row['file_count']} | {row['content_groups']} | {row['total_bytes']} |"
        )
    report.extend(
        [
            "",
            "## Outputs",
            "",
            f"- Manifest: `{detail_path.name}`",
            f"- Summary: `{summary_path.name}`",
            "",
            "The manifest chooses one representative per exact content group. All source paths remain listed for review.",
        ]
    )
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    (export_dir / "latest.md").write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")

    print("SCRUM-61 read-only migration inventory complete")
    print(f"Report: {report_path.relative_to(root)}")
    print(f"Manifest: {detail_path.relative_to(root)}")
    print(f"Summary: {summary_path.relative_to(root)}")
    return 0


def shutil_which(command: str) -> str | None:
    from shutil import which

    return which(command)


if __name__ == "__main__":
    raise SystemExit(main())
