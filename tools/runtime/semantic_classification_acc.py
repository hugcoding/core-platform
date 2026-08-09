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

from core.semantic.classification_storage import (
    build_proposal_plan, build_review_plan, render_proposal_apply_sql, render_review_apply_sql,
)


def _apply(sql: str) -> None:
    command = ["docker", "exec", "-i", os.getenv("POSTGRES_CONTAINER", "postgres"), "psql",
               "-v", "ON_ERROR_STOP=1", "-U", os.getenv("DB_USER", "hugo"),
               "-d", os.getenv("DB_NAME", "nasdb_test")]
    subprocess.run(command, input=sql, text=True, check=True)


def _mode(parser: argparse.ArgumentParser) -> None:
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persist reviewed classification metadata in ACC.")
    commands = parser.add_subparsers(dest="command", required=True)
    proposals = commands.add_parser("proposals", help="Plan or store LLM classification proposals")
    proposals.add_argument("report")
    _mode(proposals)
    review = commands.add_parser("review", help="Plan or append one human review")
    review.add_argument("review")
    _mode(review)
    args = parser.parse_args(argv)

    source = Path(args.report if args.command == "proposals" else args.review).resolve()
    if not source.is_file():
        parser.error(f"input not found: {source}")
    payload = source.read_bytes()
    if args.command == "proposals":
        report = json.loads(payload)
        manifest = Path(str(report.get("manifest") or ""))
        if not manifest.is_absolute():
            manifest = ROOT / manifest
        if not manifest.is_file():
            parser.error(f"source manifest not found: {manifest}")
        plan = build_proposal_plan(payload, manifest.read_bytes())
        sql = render_proposal_apply_sql(plan)
        prefix, identity = "classification-acc-plan", plan["run_id"]
        summary = {"run_id": identity, "documents": plan["document_count"],
                   "proposals": plan["proposal_count"], "errors": plan["error_count"]}
    else:
        plan = build_review_plan(json.loads(payload))
        sql = render_review_apply_sql(plan)
        prefix, identity = "classification-review-plan", plan["id"]
        summary = {"review_id": identity, "proposal_id": plan["proposal_id"], "decision": plan["decision"]}

    export_dir = ROOT / "project/exports/semantic-pilot"
    export_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    target = export_dir / f"{prefix}-{stamp}.json"
    target.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.apply:
        _apply(sql)
    print(json.dumps({"status": "applied" if args.apply else "dry_run", **summary,
                      "database_writes": bool(args.apply), "file_mutations": False,
                      "raw_text_stored": False, "plan": str(target.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
