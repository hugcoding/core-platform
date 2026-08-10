#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import warnings
from pathlib import Path

import psycopg2
import psycopg2.extras

from core.metadata.date_evidence import SUPPORTED_EXTENSIONS, extract_date_evidence
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore", message=r"Call to '__init__'.*retry_on_timeout", category=DeprecationWarning
    )
    from metadata_worker import persist_date_evidence


def validated_source(value: str) -> Path:
    source = Path(value)
    normalized = os.path.normpath(str(source))
    if not os.path.isabs(normalized) or not normalized.startswith("/volume1/"):
        raise argparse.ArgumentTypeError("source must be an absolute path below /volume1")
    if normalized in {"/volume1/data", "/volume1"}:
        raise argparse.ArgumentTypeError("source is too broad for a date-evidence backfill")
    return Path(normalized)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="date-evidence-backfill")
    result.add_argument(
        "--source",
        type=validated_source,
        default=Path("/volume1/data/import/cloud/onedrive/current/Documenten"),
    )
    result.add_argument("--limit", type=int)
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    return result


def database_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT")),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASS"),
        dbname=os.getenv("DB_NAME"),
    )


def select_files(cur, source: Path, limit: int | None):
    query = """
        SELECT id, path, extension, content_sha256, size_bytes
        FROM files
        WHERE deleted_at IS NULL
          AND path LIKE %s
          AND extension = ANY(%s)
          AND size_bytes > 0
          AND content_sha256 IS NOT NULL
        ORDER BY id
    """
    params: list[object] = [str(source).rstrip("/") + "/%", sorted(SUPPORTED_EXTENSIONS)]
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        query += " LIMIT %s"
        params.append(limit)
    cur.execute(query, tuple(params))
    return cur.fetchall()


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    conn = database_connection()
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    files = select_files(cur, args.source, args.limit)
    summary = {
        "status": "apply" if args.apply else "dry_run",
        "source": str(args.source), "files": len(files),
        "files_with_evidence": 0, "observations": 0, "inserted": 0, "errors": 0,
        "database_writes": bool(args.apply), "file_mutations": False,
    }
    try:
        for row in files:
            try:
                if args.apply:
                    inserted = persist_date_evidence(
                        cur, file_id=row["id"], path=row["path"],
                        extension=row["extension"], content_sha256=row["content_sha256"],
                        size_bytes=row["size_bytes"], strict_extraction=True,
                    )
                    summary["inserted"] += inserted
                    if inserted:
                        summary["files_with_evidence"] += 1
                else:
                    evidence = extract_date_evidence(
                        Path(row["path"]), extension=row["extension"]
                    )
                    summary["observations"] += len(evidence)
                    if evidence:
                        summary["files_with_evidence"] += 1
            except Exception as exc:
                summary["errors"] += 1
                print(json.dumps({
                    "file_id": row["id"], "path": row["path"],
                    "status": "error", "error": f"{type(exc).__name__}: {exc}",
                }, ensure_ascii=False))
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
