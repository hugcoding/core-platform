#!/usr/bin/env python3
"""Read-only candidate inventory for the unified SCRUM-116 queue."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from core.execution.queue import select_batch
from core.migration.personal_executor import sha256_file
from tools.runtime.duplicate_cleanup_executor import inspect_candidates as exact_candidates
from tools.runtime.personal_migration_executor import copy_rows, inspect_candidates as migration_candidates


def exact_items(limit: int) -> tuple[list[dict], list[dict]]:
    eligible, blocked = exact_candidates(limit)
    return [{**item, "file_id": item["redundant_file_id"], "action_type": "quarantine_exact_duplicate",
             "source_path": item["source_path"], "target_path": item["target_path"],
             "reviewed_at": item.get("reviewed_at", "")} for item in eligible], blocked


def similar_items() -> tuple[list[dict], list[dict]]:
    rows = copy_rows("""SELECT review_event_id, group_key, selected_file_id, redundant_file_id,
      leader_path, redundant_path AS source_path, quarantine_path AS target_path,
      redundant_content_sha256 AS content_sha256, redundant_size_bytes AS size_bytes,
      eligible_for_cleanup, nomination_reason
      FROM public.v_pdf_content_similarity_quarantine_handoff
      ORDER BY review_event_id, redundant_file_id""")
    eligible, blocked = [], []
    for row in rows:
        item = {**row, "file_id": row["redundant_file_id"], "action_type": "quarantine_content_similar"}
        path = Path(row["source_path"])
        reason = None
        if row["eligible_for_cleanup"] != "t": reason = "similarity_evidence_changed"
        elif not path.is_file() or path.is_symlink(): reason = "source_missing_or_not_regular_file"
        elif path.stat().st_size != int(row["size_bytes"]): reason = "source_size_changed"
        elif sha256_file(path) != row["content_sha256"]: reason = "source_hash_changed"
        if reason: item["blocked_reason"] = reason; blocked.append(item)
        else: eligible.append(item)
    return eligible, blocked


def migration_items(limit: int) -> tuple[list[dict], list[dict]]:
    eligible, blocked = migration_candidates(limit)
    output = []
    for item in eligible:
        lifecycle = item["effective_lifecycle"]
        action = ("quarantine_deletion_review" if lifecycle == "deletion_review" else
                  "migrate_active" if lifecycle == "active" else "migrate_inactive")
        output.append({**item, "action_type": action, "reviewed_at": item.get("target_path_reviewed_at", "")})
    return output, blocked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--dry-run", action="store_true", required=True)
    args = parser.parse_args(argv)
    exact, exact_blocked = exact_items(100)
    similar, similar_blocked = similar_items()
    migration, migration_blocked = migration_items(100)
    selected = select_batch([*exact, *similar, *migration], args.limit)
    print(json.dumps({"status": "dry_run", "ready_total_discovered": len({int(i["file_id"]) for i in [*exact,*similar,*migration]}),
      "selected": selected, "selected_count": len(selected),
      "ready_by_type": {kind: sum(i["action_type"] == kind for i in [*exact,*similar,*migration]) for kind in (
        "quarantine_exact_duplicate","quarantine_content_similar","quarantine_deletion_review","migrate_active","migrate_inactive")},
      "blocked_discovered": len(exact_blocked)+len(similar_blocked)+len(migration_blocked),
      "file_mutations": False, "database_writes": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__": raise SystemExit(main())
