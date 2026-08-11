#!/usr/bin/env python3
"""Read-only SCRUM-96 target-path evaluation."""
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

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.exports.csv_format import write_dict_rows
from core.organization.target_path import mark_collisions, propose_target, select_representative
from tools.runtime.migration_inventory import run_query, shutil_which

QUERY = r"""
SELECT w.file_id, w.content_group_id, w.path, w.filename, w.extension,
       w.size_bytes, w.content_sha256, w.last_qualifying_activity_at,
       w.activity_basis_source, w.activity_confidence, w.workset_status,
       c.category AS accepted_category,
       c.document_family AS accepted_document_family,
       c.lifecycle AS accepted_lifecycle
FROM public.v_active_document_workset w
LEFT JOIN public.v_current_file_classification c ON c.file_id = w.file_id
WHERE w.workset_status = 'active'
ORDER BY w.last_qualifying_activity_at DESC NULLS LAST, w.path, w.file_id;
"""

FIELDS = ["file_id", "content_group_id", "path", "filename", "extension", "size_bytes",
          "content_sha256", "last_qualifying_activity_at", "activity_basis_source",
          "activity_confidence", "workset_status", "accepted_category",
          "accepted_document_family", "accepted_lifecycle", "zone_code", "zone_label", "category_code",
          "category_label", "folder_label", "suggested_target_path", "proposal_reason_code",
          "proposal_confidence", "collision_status", "contract_version", "contract_checksum",
          "database_writes", "file_mutations"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the canonical Dutch target-path contract.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", required=True, action="store_true")
    args = parser.parse_args(argv)
    docker = os.getenv("DOCKER_BIN", "docker")
    if docker == "docker" and not shutil_which(docker) and Path("/usr/local/bin/docker").exists():
        docker = "/usr/local/bin/docker"
    command = [docker, "exec", os.getenv("POSTGRES_CONTAINER", "postgres"), "psql",
               "-U", os.getenv("DB_USER", "hugo"), "-d", os.getenv("DB_NAME", "nasdb_test")]
    try:
        # The shared helper requires a source argument for optional SQL token
        # rendering. This query is already scoped by the workset view and has
        # no source tokens, so an empty value is intentional.
        source = list(csv.DictReader(io.StringIO(run_query(command, QUERY, ""))))
        rows = mark_collisions([propose_target(row) for row in select_representative(source, args.limit)])
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as exc:
        print(f"Target-path pilot failed: {exc}", file=sys.stderr)
        return 1
    generated = datetime.now().astimezone()
    stamp = generated.strftime("%Y%m%d-%H%M%S")
    output = ROOT / "project/exports/active-workset"
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / f"canonical-target-path-{stamp}.csv"
    json_path = output / f"canonical-target-path-{stamp}.json"
    md_path = output / f"canonical-target-path-{stamp}.md"
    write_dict_rows(csv_path, rows, FIELDS)
    summary = {
        "selected": len(rows),
        "accepted_classification": sum(r["proposal_reason_code"] == "accepted_human_classification" for r in rows),
        "rule_based": sum(r["proposal_reason_code"] == "deterministic_keyword_rule" for r in rows),
        "needs_review": sum(r["category_code"] == "needs_review" for r in rows),
        "collisions": sum(r["collision_status"] != "none" for r in rows),
    }
    payload = {"schema_version": "canonical-target-path-evaluation-v1", "generated_at": generated.isoformat(),
               "mode": "read_only_dry_run", "summary": summary, "files": rows,
               "safety": {"database_writes": False, "file_mutations": False}}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# SCRUM-96 canoniek Nederlands doelpadcontract", "", "- Modus: **read-only dry-run**",
             f"- Geselecteerde actieve golden records: **{len(rows)}**",
             f"- Menselijk geaccepteerde classificatie: **{summary['accepted_classification']}**",
             f"- Deterministische regels: **{summary['rule_based']}**",
             f"- Te beoordelen: **{summary['needs_review']}**", f"- Botsingen: **{summary['collisions']}**", "",
             "| Bestand | Voorstel | Reden | Confidence |", "|---|---|---|---|"]
    for row in rows:
        lines.append(f"| {str(row['filename']).replace('|', '&#124;')} | `{row['suggested_target_path']}` | "
                     f"{row['proposal_reason_code']} | {row['proposal_confidence']} |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for latest, source_path in (("canonical-target-path-latest.json", json_path),
                                ("canonical-target-path-latest.md", md_path)):
        (output / latest).write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
    print("SCRUM-96 read-only target-path evaluation complete")
    print(f"Report: {md_path.relative_to(ROOT)}")
    print(f"Review: {csv_path.relative_to(ROOT)}")
    print(f"JSON: {json_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
