#!/usr/bin/env python3
"""Backfill append-only PDF content-similarity evidence."""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.integrity.pdf_content_similarity import SCHEMA_VERSION, analyze_pdf


def psql(sql: str, *, input_text: str | None = None) -> str:
    command = ["docker", "exec", "-i", os.getenv("POSTGRES_CONTAINER", "postgres"), "psql",
               "-v", "ON_ERROR_STOP=1", "-U", os.getenv("DB_USER", "hugo"),
               "-d", os.getenv("DB_NAME", "nasdb_test"), "-At", "-c", sql]
    return subprocess.run(command, input=input_text, text=True, capture_output=True, check=True).stdout


def sql_text(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def candidates(file_ids: list[int], limit: int) -> list[dict[str, str]]:
    where = "AND f.id = ANY(ARRAY[" + ",".join(map(str, file_ids)) + "]::bigint[])" if file_ids else ""
    query = f"""COPY (
      SELECT f.id AS file_id, f.path, f.content_sha256
      FROM public.files f
      WHERE f.deleted_at IS NULL AND lower(coalesce(f.extension,'')) = 'pdf'
        AND f.content_sha256 IS NOT NULL {where}
        AND NOT EXISTS (
          SELECT 1 FROM public.pdf_content_similarity_evidence e
          WHERE e.file_id = f.id AND e.content_sha256 = f.content_sha256
            AND e.analyzer_version = {sql_text(SCHEMA_VERSION)}
        )
      ORDER BY f.id LIMIT {int(limit)}
    ) TO STDOUT WITH CSV HEADER"""
    return list(csv.DictReader(io.StringIO(psql(query))))


def insert_sql(file_id: int, evidence: dict) -> str:
    document_id = evidence["document_id"]
    if not isinstance(document_id, list):
        document_id = [] if document_id is None else [document_id]
    return f"""INSERT INTO public.pdf_content_similarity_evidence (
      file_id, content_sha256, normalized_text_sha256, page_text_sha256, page_count,
      normalized_text_characters, metadata_snapshot, pdf_document_id, signature_present,
      extraction_warnings, analyzer_version
    ) VALUES ({file_id},{sql_text(evidence['content_sha256'])},{sql_text(evidence['normalized_text_sha256'])},
      {sql_text(json.dumps(evidence['page_text_sha256']))}::jsonb,{evidence['page_count']},
      {evidence['normalized_text_characters']},{sql_text(json.dumps(evidence['metadata']))}::jsonb,
      {sql_text(json.dumps(document_id))}::jsonb,{str(evidence['has_digital_signature']).lower()},
      {sql_text(json.dumps(evidence['extraction_warnings']))}::jsonb,{sql_text(SCHEMA_VERSION)})
    ON CONFLICT (file_id, content_sha256, analyzer_version) DO NOTHING;"""


def analyze_with_available_runtime(path: Path) -> dict:
    """Prefer local Python; fall back to the read-only dashboard container."""
    try:
        return analyze_pdf(path)
    except ModuleNotFoundError as exc:
        if exc.name != "pypdf":
            raise
        command = ["docker", "compose", "exec", "-T", "dashboard", "python", "-m",
                   "core.integrity.pdf_content_similarity", str(path)]
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
        return json.loads(completed.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file-id", type=int, action="append", default=[])
    parser.add_argument("--limit", type=int, default=500)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    analyzed, eligible, skipped, statements = 0, 0, [], []
    for row in candidates(args.file_id, args.limit):
        path = Path(row["path"])
        try:
            evidence = analyze_with_available_runtime(path)
            analyzed += 1
            if evidence["content_sha256"] != row["content_sha256"]:
                skipped.append({"file_id": int(row["file_id"]), "reason": "content_hash_changed"}); continue
            if not evidence["has_extractable_text"] or evidence["extraction_warnings"]:
                skipped.append({"file_id": int(row["file_id"]), "reason": "unsafe_or_no_text"}); continue
            statements.append(insert_sql(int(row["file_id"]), evidence)); eligible += 1
        except Exception as exc:
            skipped.append({"file_id": int(row["file_id"]), "reason": type(exc).__name__})
    if args.apply and statements:
        psql("BEGIN;" + "".join(statements) + "COMMIT;")
    print(json.dumps({"status": "applied" if args.apply else "dry_run", "analyzed": analyzed,
                      "evidence_eligible": eligible, "skipped": skipped,
                      "raw_text_stored": False, "file_mutations": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
