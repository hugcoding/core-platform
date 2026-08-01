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

from core.semantic.acc_storage import build_plan, render_apply_sql


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Plan or apply semantic technical metadata in ACC.")
    result.add_argument("manifest")
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    manifest = Path(args.manifest).resolve()
    if not manifest.is_file():
        print(f"Manifest not found: {manifest}", file=sys.stderr)
        return 2
    image = os.getenv("SEMANTIC_PILOT_IMAGE", "core-semantic-pilot:local")
    subprocess.run(["docker", "build", "--file", "Dockerfile.semantic-pilot", "--tag", image, "."], cwd=ROOT, check=True)
    command = ["docker", "run", "--rm", "--network", "none", "--read-only",
               "--volume", "/volume1:/volume1:ro", "--volume", f"{manifest}:/pilot/manifest.json:ro",
               image, "python", "-m", "core.semantic.chunking", "--manifest", "/pilot/manifest.json"]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    results = []
    for line in completed.stdout.splitlines():
        payload = json.loads(line)
        if payload.get("status") != "summary":
            results.append(payload)
    plan = build_plan(manifest.read_bytes(), results)
    export_dir = ROOT / "project" / "exports" / "semantic-pilot"
    export_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    plan_path = export_dir / f"semantic-acc-plan-{stamp}.json"
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.apply:
        psql = ["docker", "exec", "-i", os.getenv("POSTGRES_CONTAINER", "postgres"), "psql",
                "-v", "ON_ERROR_STOP=1", "-U", os.getenv("DB_USER", "hugo"),
                "-d", os.getenv("DB_NAME", "nasdb_test")]
        subprocess.run(psql, input=render_apply_sql(plan), text=True, check=True)
    print(json.dumps({
        "status": "applied" if args.apply else "dry_run",
        "run_id": plan["run_id"], "documents": plan["document_count"],
        "chunks": plan["chunk_count"], "errors": plan["error_count"],
        "embeddings": 0, "raw_text_stored": False,
        "plan": str(plan_path.relative_to(ROOT)),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
