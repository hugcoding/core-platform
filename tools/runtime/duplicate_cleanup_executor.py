#!/usr/bin/env python3
"""Plan and execute reversible exact-duplicate moves to CORE quarantine."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.cleanup.duplicate_executor import (
    MigrationSafetyError,
    inspect_preconditions,
    move_verified,
    resume_verified_move,
    rollback_verified,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = "duplicate-cleanup-quarantine-v1"
DATA_ROOT = "/volume1/data/"
QUARANTINE_ROOT = "/volume1/data/.core/quarantaine/duplicaten/"


def pg(value: object) -> str:
    if value is None:
        return "NULL"
    return "'{}'".format(str(value).replace("'", "''"))


def psql(sql: str, *, rows: bool = False) -> List[Dict[str, str]]:
    docker = os.getenv("DOCKER_BIN", "docker")
    if docker == "docker" and Path("/usr/local/bin/docker").exists():
        docker = "/usr/local/bin/docker"
    command = [docker, "exec", "-i", os.getenv("POSTGRES_CONTAINER", "postgres"),
               "psql", "-v", "ON_ERROR_STOP=1", "-U", os.getenv("DB_USER", "hugo"),
               "-d", os.getenv("DB_NAME", "nasdb_test"), "-c", sql]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
    return list(csv.DictReader(io.StringIO(result.stdout))) if rows else []


def copy_rows(query: str) -> List[Dict[str, str]]:
    return psql("COPY ({}) TO STDOUT WITH CSV HEADER;".format(query), rows=True)


CANDIDATES = """
SELECT h.review_event_id, h.content_group_id, h.content_sha256,
       h.selected_file_id AS leader_file_id, h.redundant_file_id,
       h.selected_path AS leader_path, h.redundant_path AS source_path,
       h.quarantine_path AS target_path, cg.size_bytes,
       r.policy_id, r.policy_code, r.policy_version, r.policy_snapshot,
       previous.current_status AS previous_cleanup_status
FROM public.v_exact_duplicate_review_handoff h
JOIN public.exact_duplicate_review_events r ON r.id = h.review_event_id
JOIN public.content_groups cg ON cg.id = h.content_group_id
LEFT JOIN LATERAL (
    SELECT status.current_status
    FROM public.duplicate_cleanup_plan_items item
    JOIN public.v_duplicate_cleanup_item_status status ON status.id = item.id
    WHERE item.redundant_file_id = h.redundant_file_id
    ORDER BY item.created_at DESC, item.id DESC LIMIT 1
) previous ON true
WHERE h.eligible_for_executor
ORDER BY h.review_event_id, h.redundant_file_id
"""


def event(plan_id: str, event_type: str, actor: str, key: str,
          item_id: Optional[str] = None, details: Optional[dict] = None) -> None:
    payload = json.dumps(details or {}, ensure_ascii=False, separators=(",", ":"))
    psql("""INSERT INTO public.duplicate_cleanup_events
      (plan_id,item_id,event_type,idempotency_key,actor,details)
      VALUES ({},{},{},{},{},{}::jsonb) ON CONFLICT (idempotency_key) DO NOTHING;""".format(
        pg(plan_id), pg(item_id), pg(event_type), pg(key), pg(actor), pg(payload)))


def inspect_candidates(limit: int) -> Tuple[List[dict], List[dict]]:
    eligible, blocked = [], []
    for raw in copy_rows("SELECT * FROM ({}) q LIMIT {}".format(CANDIDATES, limit * 20)):
        item = dict(raw)
        item["size_bytes"] = int(item["size_bytes"])
        reason = None
        if not item["leader_path"].startswith(DATA_ROOT) or not item["source_path"].startswith(DATA_ROOT):
            reason = "copy_outside_volume1_data_scope"
        elif item["source_path"].startswith(QUARANTINE_ROOT):
            reason = "already_in_duplicate_quarantine"
        elif item.get("previous_cleanup_status") not in (None, "", "rolled_back"):
            reason = "already_in_cleanup_plan:{}".format(item["previous_cleanup_status"])
        if reason:
            item["blocked_reason"] = reason
            blocked.append(item)
            continue
        if len(eligible) >= limit:
            continue
        try:
            checked = inspect_preconditions(item)
            item["mtime_ns"] = checked.mtime_ns
            eligible.append(item)
        except (MigrationSafetyError, OSError) as exc:
            item["blocked_reason"] = str(exc)
            blocked.append(item)
    return eligible, blocked


def export_report(payload: dict) -> Path:
    out = ROOT / "project/exports/duplicate-cleanup"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    path = out / "duplicate-cleanup-{}-{}.json".format(payload["action"], stamp)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    latest = out / "duplicate-cleanup-{}-latest.json".format(payload["action"])
    latest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def plan(args: argparse.Namespace) -> int:
    eligible, blocked = inspect_candidates(args.limit)
    payload = {
        "schema_version": CONTRACT, "action": "plan",
        "mode": "create" if args.create_plan else "dry_run",
        "eligible": eligible, "blocked": blocked,
        "potential_savings_bytes": sum(item["size_bytes"] for item in eligible),
        "file_mutations": False, "physical_purge_supported": False,
        "database_writes": bool(args.create_plan),
    }
    if args.create_plan:
        if not eligible:
            raise MigrationSafetyError("no_eligible_items")
        canonical = json.dumps(eligible, sort_keys=True, separators=(",", ":"))
        plan_key = hashlib.sha256(canonical.encode()).hexdigest()
        existing = copy_rows("SELECT id FROM public.duplicate_cleanup_plans WHERE plan_key={}".format(pg(plan_key)))
        if existing:
            payload["plan_id"] = existing[0]["id"]
            payload["mode"] = "existing_plan"
        else:
            plan_id = str(uuid.uuid4())
            item_values, event_values = [], []
            for sequence, item in enumerate(eligible, 1):
                item_id = str(uuid.uuid4())
                item["item_id"] = item_id
                item_values.append("({},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{})".format(
                    pg(item_id), pg(plan_id), sequence, pg(item["review_event_id"]),
                    pg(item["content_group_id"]), item["leader_file_id"], item["redundant_file_id"],
                    pg(item["content_sha256"]), item["size_bytes"], pg(item["leader_path"]),
                    pg(item["source_path"]), pg(item["target_path"]), item["mtime_ns"],
                    pg(item["policy_id"]), pg(item["policy_code"]), pg(item["policy_version"]),
                    pg(item["policy_snapshot"]), "NOW()"))
                details = json.dumps({"leader_path": item["leader_path"], "source_path": item["source_path"],
                                      "quarantine_path": item["target_path"], "physical_purge": False},
                                     ensure_ascii=False, separators=(",", ":"))
                event_values.append("({},{},'planned',{},{},{}::jsonb)".format(
                    pg(plan_id), pg(item_id), pg("{}:{}:planned".format(plan_id, item_id)),
                    pg(args.actor), pg(details)))
            sql = """BEGIN;
            INSERT INTO public.duplicate_cleanup_plans
              (id,plan_key,contract_version,max_batch_size,item_count,created_by)
            VALUES ({},{},{},{},{},{});
            INSERT INTO public.duplicate_cleanup_plan_items
              (id,plan_id,sequence_no,review_event_id,content_group_id,leader_file_id,
               redundant_file_id,content_sha256,size_bytes,leader_path,source_path,
               quarantine_path,mtime_ns,policy_id,policy_code,policy_version,policy_snapshot,created_at)
            VALUES {};
            INSERT INTO public.duplicate_cleanup_events
              (plan_id,item_id,event_type,idempotency_key,actor,details)
            VALUES {};
            COMMIT;""".format(pg(plan_id), pg(plan_key), pg(CONTRACT), args.limit,
                               len(eligible), pg(args.actor), ",".join(item_values),
                               ",".join(event_values))
            psql(sql)
            payload["plan_id"] = plan_id
    report = export_report(payload)
    print(json.dumps({"status": payload["mode"], "eligible": len(eligible),
                      "blocked": len(blocked), "potential_savings_bytes": payload["potential_savings_bytes"],
                      "plan_id": payload.get("plan_id"), "report": str(report.relative_to(ROOT)),
                      "physical_purge_supported": False}, ensure_ascii=False))
    return 0


def require_confirmation(value: str, expected: str) -> None:
    if value != expected:
        raise MigrationSafetyError("explicit_confirmation_required:{}".format(expected))


def plan_items(plan_id: str) -> List[Dict[str, str]]:
    return copy_rows("""SELECT i.*, i.quarantine_path AS target_path, s.current_status
      FROM public.duplicate_cleanup_plan_items i
      JOIN public.v_duplicate_cleanup_item_status s ON s.id=i.id
      WHERE i.plan_id={} ORDER BY i.sequence_no""".format(pg(plan_id)))


def approve(args: argparse.Namespace) -> int:
    require_confirmation(args.confirm, args.plan_id)
    rows = copy_rows("SELECT count(*) AS count FROM public.duplicate_cleanup_plan_items WHERE plan_id={}".format(pg(args.plan_id)))
    if not rows or int(rows[0]["count"]) < 1:
        raise MigrationSafetyError("plan_not_found_or_empty")
    detail = pg(json.dumps({"explicit_confirmation": True, "physical_purge": False}, separators=(",", ":")))
    psql("""BEGIN;
      INSERT INTO public.duplicate_cleanup_events
        (plan_id,item_id,event_type,idempotency_key,actor,details)
      VALUES ({},NULL,'approved',{},{},{}::jsonb) ON CONFLICT (idempotency_key) DO NOTHING;
      INSERT INTO public.duplicate_cleanup_events
        (plan_id,item_id,event_type,idempotency_key,actor,details)
      SELECT i.plan_id,i.id,'approved',i.plan_id || ':' || i.id || ':approved',{},{}::jsonb
      FROM public.duplicate_cleanup_plan_items i WHERE i.plan_id={}
      ON CONFLICT (idempotency_key) DO NOTHING;
      COMMIT;""".format(pg(args.plan_id), pg("{}:approved".format(args.plan_id)), pg(args.actor),
                         detail, pg(args.actor), detail, pg(args.plan_id)))
    print(json.dumps({"status": "approved", "plan_id": args.plan_id, "physical_purge": False}))
    return 0


def is_approved(plan_id: str) -> bool:
    rows = copy_rows("SELECT EXISTS(SELECT 1 FROM public.duplicate_cleanup_events WHERE plan_id={} AND item_id IS NULL AND event_type='approved') AS ok".format(pg(plan_id)))
    return bool(rows and rows[0]["ok"] == "t")


def correlate(plan_id: str, item: dict, actor: str) -> bool:
    rows = copy_rows("""SELECT id, event_type FROM public.v_file_events_effective WHERE file_id={}
      AND event_type='MOVED' AND old_path={} AND new_path={}
      AND created_at >= (SELECT created_at FROM public.duplicate_cleanup_plans WHERE id={})
      ORDER BY created_at DESC LIMIT 1""".format(item["redundant_file_id"], pg(item["source_path"]),
                                                  pg(item["target_path"]), pg(plan_id)))
    if not rows:
        rows = copy_rows("""SELECT fe.id, fe.event_type
          FROM public.v_file_events_effective fe
          WHERE fe.file_id={}
            AND fe.event_type='DELETED'
            AND fe.old_path={}
            AND fe.created_at >= (
              SELECT created_at FROM public.duplicate_cleanup_plans WHERE id={}
            )
            AND EXISTS (
              SELECT 1 FROM public.duplicate_cleanup_events verified
              WHERE verified.plan_id={}
                AND verified.item_id={}
                AND verified.event_type='verified'
                AND verified.details->>'content_sha256'={}
                AND verified.details->>'target_path'={}
                AND verified.details->>'source_path'={}
                AND verified.details->>'physical_purge'='false'
                AND verified.details->>'recovery_available'='true'
                AND verified.details->>'qualifies_for_activation'='false'
            )
          ORDER BY fe.created_at DESC LIMIT 1""".format(
              item["redundant_file_id"], pg(item["source_path"]), pg(plan_id), pg(plan_id),
              pg(item["id"]), pg(str(item["content_sha256"]).lower()), pg(item["target_path"]),
              pg(item["source_path"]),
          ))
    if not rows:
        return False
    event_type = rows[0]["event_type"]
    correlation_kind = (
        "effective_moved_event" if event_type == "MOVED"
        else "verified_move_to_excluded_quarantine"
    )
    event(plan_id, "event_correlated", actor,
          "{}:{}:correlated:{}".format(plan_id, item["id"], rows[0]["id"]), item["id"],
          {"file_event_id": rows[0]["id"], "file_event_type": event_type,
           "correlation_kind": correlation_kind, "source": "core_duplicate_quarantine",
           "content_sha256": str(item["content_sha256"]).lower(),
           "source_path": item["source_path"], "target_path": item["target_path"],
           "qualifies_for_activation": False, "physical_purge": False,
           "recovery_available": True})
    return True


def execute(args: argparse.Namespace) -> int:
    require_confirmation(args.confirm, args.plan_id)
    if not is_approved(args.plan_id):
        raise MigrationSafetyError("plan_not_approved")
    quarantined = 0
    for item in plan_items(args.plan_id):
        if item["current_status"] not in ("approved", "quarantine_pending", "quarantined"):
            continue
        try:
            event(args.plan_id, "quarantine_pending", args.actor,
                  "{}:{}:quarantine-pending".format(args.plan_id, item["id"]), item["id"])
            result = resume_verified_move(item) if item["current_status"] in (
                "quarantine_pending", "quarantined"
            ) else move_verified(item)
            event(args.plan_id, "quarantined", args.actor,
                  "{}:{}:quarantined".format(args.plan_id, item["id"]), item["id"], result)
            event(args.plan_id, "verified", args.actor,
                  "{}:{}:verified".format(args.plan_id, item["id"]), item["id"],
                  dict(result, physical_purge=False, recovery_available=True,
                       qualifies_for_activation=False, source="core_duplicate_quarantine"))
            correlate(args.plan_id, item, args.actor)
            quarantined += 1
        except (MigrationSafetyError, OSError) as exc:
            event(args.plan_id, "failed", args.actor,
                  "{}:{}:failed:{}".format(args.plan_id, item["id"], uuid.uuid4()), item["id"],
                  {"reason": str(exc), "physical_purge": False})
            raise
    print(json.dumps({"status": "executed", "plan_id": args.plan_id,
                      "verified_quarantine_moves": quarantined, "physical_purge": False}))
    return 0


def reconcile(args: argparse.Namespace) -> int:
    correlated = sum(correlate(args.plan_id, item, args.actor) for item in plan_items(args.plan_id)
                     if item["current_status"] in ("verified", "event_correlated"))
    print(json.dumps({"status": "reconciled", "plan_id": args.plan_id, "correlated": correlated}))
    return 0


def rollback(args: argparse.Namespace) -> int:
    require_confirmation(args.confirm, args.plan_id)
    restored = 0
    for item in reversed(plan_items(args.plan_id)):
        if item["current_status"] not in ("verified", "event_correlated", "rollback_pending", "failed"):
            continue
        event(args.plan_id, "rollback_pending", args.actor,
              "{}:{}:rollback-pending".format(args.plan_id, item["id"]), item["id"])
        result = rollback_verified(item)
        event(args.plan_id, "rolled_back", args.actor,
              "{}:{}:rolled-back".format(args.plan_id, item["id"]), item["id"], result)
        restored += 1
    print(json.dumps({"status": "rolled_back", "plan_id": args.plan_id, "restored": restored}))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="duplicate-cleanup-executor")
    sub = result.add_subparsers(dest="action", required=True)
    make = sub.add_parser("plan")
    mode = make.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--create-plan", action="store_true")
    make.add_argument("--limit", type=int, default=10)
    make.add_argument("--actor", default="core-cli")
    for name in ("approve", "execute", "rollback"):
        command = sub.add_parser(name)
        command.add_argument("plan_id")
        command.add_argument("--confirm", required=True)
        command.add_argument("--actor", default="core-cli")
    sync = sub.add_parser("reconcile")
    sync.add_argument("plan_id")
    sync.add_argument("--actor", default="core-cli")
    return result


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if getattr(args, "limit", 1) < 1 or getattr(args, "limit", 1) > 100:
        print("limit must be between 1 and 100", file=sys.stderr)
        return 2
    try:
        return {"plan": plan, "approve": approve, "execute": execute,
                "reconcile": reconcile, "rollback": rollback}[args.action](args)
    except (MigrationSafetyError, subprocess.CalledProcessError, OSError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        print("Duplicate cleanup failed: {}".format(detail), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
