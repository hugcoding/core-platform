#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.semantic.embedding_storage import render_apply_sql


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or persist local E5 embeddings in ACC.")
    parser.add_argument("manifest")
    parser.add_argument("--max-chunks", type=int, default=32)
    parser.add_argument("--batch-size", type=int, default=4)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    manifest = Path(args.manifest).resolve()
    if not manifest.is_file():
        parser.error(f"manifest not found: {manifest}")
    image = os.getenv("SEMANTIC_BENCHMARK_IMAGE", "core-semantic-embedding-benchmark:local")
    command = [
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=1g",
        "--volume", "/volume1:/volume1:ro",
        "--volume", f"{manifest}:/pilot/manifest.json:ro",
        "--volume", f"{ROOT / 'project/models'}:/models:ro",
        image, "python", "-m", "core.semantic.embedding_persist",
        "--manifest", "/pilot/manifest.json", "--model-path", "/models/multilingual-e5-small",
        "--max-chunks", str(args.max_chunks), "--batch-size", str(args.batch_size),
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if completed.returncode:
        if completed.stdout:
            print(completed.stdout, file=sys.stderr, end="")
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        return completed.returncode
    plan = json.loads(completed.stdout.strip().splitlines()[-1])
    export_dir = ROOT / "project/exports/semantic-pilot"
    export_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    plan_path = export_dir / f"semantic-embedding-acc-plan-{stamp}.json"
    # The plan contains derived vectors but never raw text.
    plan_path.write_text(json.dumps(plan, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.apply:
        psql = [
            "docker", "exec", "-i", os.getenv("POSTGRES_CONTAINER", "postgres"), "psql",
            "-v", "ON_ERROR_STOP=1", "-U", os.getenv("DB_USER", "hugo"),
            "-d", os.getenv("DB_NAME", "nasdb_test"),
        ]
        subprocess.run(psql, input=render_apply_sql(plan), text=True, check=True)
    print(json.dumps({
        "status": "applied" if args.apply else "dry_run",
        "embedding_run_id": plan["embedding_run_id"],
        "semantic_run_id": plan["semantic_run_id"],
        "documents": plan["document_count"],
        "chunks": plan["chunk_count"],
        "errors": plan["error_count"],
        "batch_size": plan["batch_size"],
        "model_id": plan["model_id"],
        "vectors_stored": bool(args.apply),
        "raw_text_stored": False,
        "plan": str(plan_path.relative_to(ROOT)),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
