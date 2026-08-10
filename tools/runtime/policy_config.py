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

from core.policies.registry import build_seed_plan, render_seed_sql


DEFAULT_SOURCE = ROOT / "project/policies/active-document-workset-v1.json"


def apply_sql(sql: str) -> None:
    command = [
        os.getenv("DOCKER_BIN", "docker"), "exec", "-i",
        os.getenv("POSTGRES_CONTAINER", "postgres"), "psql",
        "-v", "ON_ERROR_STOP=1", "-U", os.getenv("DB_USER", "hugo"),
        "-d", os.getenv("DB_NAME", "nasdb_test"),
    ]
    subprocess.run(command, input=sql, text=True, check=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and seed versioned CORE policies.")
    commands = parser.add_subparsers(dest="command", required=True)
    seed = commands.add_parser("seed", help="Seed one immutable policy snapshot")
    seed.add_argument("--source", default=str(DEFAULT_SOURCE))
    seed.add_argument("--environment", required=True,
                      choices=("development", "acceptance", "production"))
    mode = seed.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    source = Path(args.source).resolve()
    if not source.is_file():
        parser.error(f"policy source not found: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
        plan = build_seed_plan(payload, environment=args.environment)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    sql = render_seed_sql(plan)
    export_dir = ROOT / "project/exports/policies"
    export_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    target = export_dir / f"policy-seed-{plan['policy_code']}-{args.environment}-{stamp}.json"
    target.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.apply:
        apply_sql(sql)
    print(json.dumps({
        "status": "applied" if args.apply else "dry_run",
        "policy_id": plan["id"],
        "policy_code": plan["policy_code"],
        "policy_version": plan["policy_version"],
        "environment": plan["environment"],
        "configuration_checksum": plan["configuration_checksum"],
        "database_writes": bool(args.apply),
        "file_mutations": False,
        "plan": str(target.relative_to(ROOT)),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
