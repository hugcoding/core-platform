#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.semantic.similarity import render_document_similarity_sql, render_query_similarity_sql


def psql(sql: str) -> list[dict]:
    command = [
        "docker", "exec", "-i", os.getenv("POSTGRES_CONTAINER", "postgres"),
        "psql", "-v", "ON_ERROR_STOP=1", "-X", "-A", "-t",
        "-U", os.getenv("DB_USER", "hugo"), "-d", os.getenv("DB_NAME", "nasdb_test"),
    ]
    completed = subprocess.run(command, input=sql, capture_output=True, text=True)
    if completed.returncode:
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        raise SystemExit(completed.returncode)
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def query_vector(query: str) -> list[float]:
    image = os.getenv("SEMANTIC_BENCHMARK_IMAGE", "core-semantic-embedding-benchmark:local")
    command = [
        "docker", "run", "--rm", "-i", "--network", "none", "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=1g",
        "--volume", f"{ROOT / 'project/models'}:/models:ro",
        image, "python", "-m", "core.semantic.query_embedding",
        "--model-path", "/models/multilingual-e5-small",
    ]
    completed = subprocess.run(command, input=query, capture_output=True, text=True)
    if completed.returncode:
        if completed.stdout:
            print(completed.stdout, file=sys.stderr, end="")
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        raise SystemExit(completed.returncode)
    return json.loads(completed.stdout.strip().splitlines()[-1])["vector"]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Read-only semantic retrieval from ACC embeddings.")
    sub = result.add_subparsers(dest="mode", required=True)
    query = sub.add_parser("query")
    query.add_argument("query")
    document = sub.add_parser("document")
    document.add_argument("file_id", type=int)
    for command in (query, document):
        command.add_argument("--limit", type=int, default=10)
        command.add_argument("--threshold", type=float, default=0.0)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.mode == "query":
        sql = render_query_similarity_sql(query_vector(args.query), limit=args.limit, threshold=args.threshold)
    else:
        sql = render_document_similarity_sql(args.file_id, limit=args.limit, threshold=args.threshold)
    rows = psql(sql)
    print(json.dumps({
        "schema_version": "semantic-similarity-results-v1",
        "mode": args.mode,
        "read_only": True,
        "result_count": len(rows),
        "results": rows,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
