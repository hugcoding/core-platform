#!/usr/bin/env python3
"""Plan, approve, execute, reconcile and roll back controlled personal moves."""
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

from core.migration.personal_executor import (
    MigrationSafetyError, inspect_preconditions, move_verified, rollback_verified,
    resume_verified_move,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = "personal-migration-executor-v2"
DELETION_QUARANTINE_ROOT = Path("/volume1/data/.core/quarantaine/verwijderreview")


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


NORMAL_CANDIDATES = """
SELECT v.file_id, v.content_group_id, v.content_sha256, v.source_path,
       v.lifecycle_aligned_proposed_path AS target_path, f.size_bytes,
       v.effective_lifecycle, v.lifecycle_reviewed_at, v.target_path_reviewed_at,
       (SELECT count(*) FROM public.content_group_members gm
        JOIN public.files mf ON mf.id = gm.file_id AND mf.deleted_at IS NULL
        WHERE gm.content_group_id = v.content_group_id) AS available_copies
       ,(SELECT count(*) FROM public.v_exact_duplicate_review_handoff h
         WHERE h.content_group_id = v.content_group_id
           AND h.selected_file_id = v.file_id
           AND h.eligible_for_executor) AS reviewed_redundant_copies,
       NULL::uuid AS deletion_nomination_id,
       2 AS candidate_priority,
       NULL::text AS previous_cleanup_status
FROM public.v_document_workset_path_review v
JOIN public.files f ON f.id = v.file_id AND f.deleted_at IS NULL
JOIN public.content_groups g ON g.id = v.content_group_id
 AND g.golden_file_id = v.file_id AND g.content_sha256 = v.content_sha256
WHERE v.effective_lifecycle IN ('active', 'archive')
  AND v.lifecycle_reviewed_at IS NOT NULL
  AND EXISTS (
      SELECT 1 FROM public.v_latest_document_review lr
      WHERE lr.file_id = v.file_id AND lr.review_type = 'lifecycle'
        AND lr.decision = 'accepted'
  )
  AND v.target_path_reviewed_at IS NOT NULL
  AND v.target_path_decision = 'accepted'
  AND v.lifecycle_aligned_proposed_path ~ '^/volume1/data/Persoonlijk/(Actief|Inactief)/'
  AND v.source_path LIKE '/volume1/data/%'
  AND NOT EXISTS (
      SELECT 1 FROM public.v_active_document_lifecycle_nominations nomination
      WHERE nomination.file_id = v.file_id AND nomination.nomination_type = 'deletion'
  )
"""

DELETION_CANDIDATES = """
SELECT nomination.file_id, nomination.content_group_id, nomination.content_sha256,
       file.path AS source_path,
       '/volume1/data/.core/quarantaine/verwijderreview/' || nomination.id::text || '/'
         || file.id::text || '-' || file.filename AS target_path,
       file.size_bytes, 'deletion_review'::text AS effective_lifecycle,
       nomination.created_at AS lifecycle_reviewed_at,
       nomination.created_at AS target_path_reviewed_at,
       (SELECT count(*) FROM public.content_group_members member
        JOIN public.files copy ON copy.id = member.file_id AND copy.deleted_at IS NULL
        WHERE member.content_group_id = nomination.content_group_id) AS available_copies,
       0::bigint AS reviewed_redundant_copies,
       nomination.id AS deletion_nomination_id,
       1 AS candidate_priority,
       previous_cleanup.current_status AS previous_cleanup_status
FROM public.v_active_document_lifecycle_nominations nomination
JOIN public.files file ON file.id = nomination.file_id AND file.deleted_at IS NULL
JOIN public.content_group_members member
  ON member.content_group_id = nomination.content_group_id AND member.file_id = file.id
LEFT JOIN LATERAL (
    SELECT status.current_status
    FROM public.duplicate_cleanup_plan_items cleanup
    JOIN public.v_duplicate_cleanup_item_status status ON status.id = cleanup.id
    WHERE cleanup.redundant_file_id = nomination.file_id
    ORDER BY cleanup.created_at DESC, cleanup.id DESC LIMIT 1
) previous_cleanup ON true
WHERE nomination.nomination_type = 'deletion'
  AND file.content_sha256 = nomination.content_sha256
  AND file.path LIKE '/volume1/data/%'
  AND file.path NOT LIKE '/volume1/data/.core/quarantaine/%'
"""

CANDIDATES = """SELECT * FROM (({}) UNION ALL ({})) candidates
ORDER BY candidate_priority, target_path_reviewed_at, file_id""".format(
    DELETION_CANDIDATES, NORMAL_CANDIDATES
)


def allowed_zones(item: dict) -> Optional[Tuple[Path, ...]]:
    if item.get("effective_lifecycle") == "deletion_review":
        return (DELETION_QUARANTINE_ROOT,)
    return None


def event(plan_id: str, event_type: str, actor: str, key: str,
          item_id: Optional[str] = None, details: Optional[dict] = None) -> None:
    payload = json.dumps(details or {}, ensure_ascii=False, separators=(",", ":"))
    psql("""INSERT INTO public.personal_migration_events
      (plan_id,item_id,event_type,idempotency_key,actor,details)
      VALUES ({},{},{},{},{},{}::jsonb) ON CONFLICT (idempotency_key) DO NOTHING;""".format(
        pg(plan_id), pg(item_id), pg(event_type), pg(key), pg(actor), pg(payload)))


def inspect_candidates(limit: int, minimum_free_bytes: int) -> Tuple[List[dict], List[dict]]:
    eligible, blocked = [], []
    for row in copy_rows("SELECT * FROM ({}) q LIMIT {}".format(CANDIDATES, limit * 5)):
        if len(eligible) >= limit:
            break
        item = dict(row)
        item["size_bytes"] = int(item["size_bytes"])
        available_copies = int(item["available_copies"])
        reviewed_redundant_copies = int(item["reviewed_redundant_copies"])
        if item.get("previous_cleanup_status") not in (None, "", "rolled_back"):
            item["blocked_reason"] = "already_in_duplicate_cleanup:{}".format(
                item["previous_cleanup_status"]
            )
            blocked.append(item)
            continue
        if item.get("deletion_nomination_id"):
            item["duplicate_resolution"] = "deletion_review"
        elif available_copies > 1:
            if reviewed_redundant_copies != available_copies - 1:
                item["blocked_reason"] = "duplicate_review_required"
                blocked.append(item)
                continue
            item["duplicate_resolution"] = "golden_only"
        else:
            item["duplicate_resolution"] = None
        try:
            checked = inspect_preconditions(
                item, minimum_free_bytes=minimum_free_bytes,
                allowed_zones=allowed_zones(item),
            )
            item["mtime_ns"] = checked.mtime_ns
            eligible.append(item)
        except (MigrationSafetyError, OSError) as exc:
            item["blocked_reason"] = str(exc)
            blocked.append(item)
    return eligible, blocked


def export_report(payload: dict) -> Path:
    out = ROOT / "project/exports/personal-migration"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    path = out / "personal-migration-{}-{}.json".format(payload["action"], stamp)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "personal-migration-{}-latest.json".format(payload["action"])).write_text(
        path.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def plan(args: argparse.Namespace) -> int:
    eligible, blocked = inspect_candidates(args.limit, args.minimum_free_bytes)
    payload = {"schema_version": CONTRACT, "action": "plan", "mode": "create" if args.create_plan else "dry_run",
               "eligible": eligible, "blocked": blocked, "file_mutations": False, "database_writes": bool(args.create_plan)}
    if args.create_plan:
        if not eligible:
            raise MigrationSafetyError("no_eligible_items")
        canonical = json.dumps(eligible, sort_keys=True, separators=(",", ":"))
        plan_key = hashlib.sha256(canonical.encode()).hexdigest()
        existing = copy_rows("SELECT id FROM public.personal_migration_plans WHERE plan_key={}".format(pg(plan_key)))
        if existing:
            payload["plan_id"] = existing[0]["id"]
            payload["mode"] = "existing_plan"
            report = export_report(payload)
            print(json.dumps({"status": "existing_plan", "eligible": len(eligible), "blocked": len(blocked),
                              "plan_id": payload["plan_id"], "report": str(report.relative_to(ROOT))}, ensure_ascii=False))
            return 0
        plan_id = str(uuid.uuid4())
        values = []
        planned_events = []
        for sequence, item in enumerate(eligible, 1):
            item_id = str(uuid.uuid4())
            item["item_id"] = item_id
            values.append("({},{},{},{},{},{},{},{},{},{},{},{},{},{},{})".format(
                pg(item_id), pg(plan_id), sequence, item["file_id"], pg(item["content_group_id"]),
                pg(item["content_sha256"]), item["size_bytes"], pg(item["source_path"]),
                pg(item["target_path"]), item["mtime_ns"], pg(item["effective_lifecycle"]),
                pg(item["lifecycle_reviewed_at"]), pg(item["target_path_reviewed_at"]),
                pg(item["duplicate_resolution"]), pg(item.get("deletion_nomination_id"))))
            detail = json.dumps({"source_path": item["source_path"], "target_path": item["target_path"],
                                 "duplicate_resolution": item["duplicate_resolution"],
                                 "deletion_nomination_id": item.get("deletion_nomination_id")},
                                ensure_ascii=False, separators=(",", ":"))
            planned_events.append("({},{},'planned',{},{},{}::jsonb)".format(
                pg(plan_id), pg(item_id), pg("{}:{}:planned".format(plan_id, item_id)),
                pg(args.actor), pg(detail)))
        sql = """BEGIN;
        INSERT INTO public.personal_migration_plans
          (id,plan_key,contract_version,source_root,target_root,max_batch_size,minimum_free_bytes,item_count,created_by)
        VALUES ({},{},{},'/volume1/data','/volume1/data',{},{},{},{});
        INSERT INTO public.personal_migration_plan_items
          (id,plan_id,sequence_no,file_id,content_group_id,content_sha256,size_bytes,source_path,target_path,mtime_ns,effective_lifecycle,lifecycle_reviewed_at,target_path_reviewed_at,duplicate_resolution,deletion_nomination_id)
        VALUES {};
        INSERT INTO public.personal_migration_events
          (plan_id,item_id,event_type,idempotency_key,actor,details)
        VALUES {};
        COMMIT;""".format(pg(plan_id), pg(plan_key), pg(CONTRACT), args.limit,
                           args.minimum_free_bytes, len(eligible), pg(args.actor), ",".join(values),
                           ",".join(planned_events))
        psql(sql)
        payload["plan_id"] = plan_id
    report = export_report(payload)
    print(json.dumps({"status": payload["mode"], "eligible": len(eligible), "blocked": len(blocked),
                      "plan_id": payload.get("plan_id"), "report": str(report.relative_to(ROOT))}, ensure_ascii=False))
    return 0


def require_confirmation(value: str, expected: str) -> None:
    if value != expected:
        raise MigrationSafetyError("explicit_confirmation_required:{}".format(expected))


def approve(args: argparse.Namespace) -> int:
    require_confirmation(args.confirm, args.plan_id)
    count = copy_rows("SELECT count(*) AS count FROM public.personal_migration_plan_items WHERE plan_id={}".format(pg(args.plan_id)))
    if not count or int(count[0]["count"]) < 1:
        raise MigrationSafetyError("plan_not_found_or_empty")
    details = pg(json.dumps({"explicit_confirmation": True}, separators=(",", ":")))
    psql("""BEGIN;
      INSERT INTO public.personal_migration_events
        (plan_id,item_id,event_type,idempotency_key,actor,details)
      VALUES ({},NULL,'approved',{},{},{}::jsonb)
      ON CONFLICT (idempotency_key) DO NOTHING;
      INSERT INTO public.personal_migration_events
        (plan_id,item_id,event_type,idempotency_key,actor,details)
      SELECT i.plan_id,i.id,'approved',i.plan_id || ':' || i.id || ':approved',{},{}::jsonb
      FROM public.personal_migration_plan_items i WHERE i.plan_id={}
      ON CONFLICT (idempotency_key) DO NOTHING;
      COMMIT;""".format(pg(args.plan_id), pg("{}:approved".format(args.plan_id)),
                         pg(args.actor), details, pg(args.actor), details, pg(args.plan_id)))
    print(json.dumps({"status": "approved", "plan_id": args.plan_id}))
    return 0


def plan_items(plan_id: str) -> List[Dict[str, str]]:
    return copy_rows("""SELECT i.*, s.current_status, p.minimum_free_bytes AS planned_minimum_free_bytes
      FROM public.personal_migration_plan_items i
      JOIN public.v_personal_migration_item_status s ON s.id=i.id
      JOIN public.personal_migration_plans p ON p.id=i.plan_id
      WHERE i.plan_id={} ORDER BY i.sequence_no""".format(pg(plan_id)))


def is_approved(plan_id: str) -> bool:
    rows = copy_rows("SELECT EXISTS(SELECT 1 FROM public.personal_migration_events WHERE plan_id={} AND item_id IS NULL AND event_type='approved') AS ok".format(pg(plan_id)))
    return bool(rows and rows[0]["ok"] == "t")


def deletion_nomination_is_current(item: dict) -> bool:
    if item["effective_lifecycle"] != "deletion_review":
        return True
    rows = copy_rows("""SELECT EXISTS(
      SELECT 1 FROM public.v_active_document_lifecycle_nominations nomination
      JOIN public.files file ON file.id=nomination.file_id AND file.deleted_at IS NULL
      WHERE nomination.id={} AND nomination.file_id={}
        AND nomination.nomination_type='deletion'
        AND nomination.content_sha256={}
        AND file.content_sha256=nomination.content_sha256
    ) AS ok""".format(
        pg(item["deletion_nomination_id"]), item["file_id"], pg(item["content_sha256"])
    ))
    return bool(rows and rows[0]["ok"] == "t")


def correlate(plan_id: str, item: dict, actor: str) -> bool:
    rows = copy_rows("""SELECT id FROM public.v_file_events_effective WHERE file_id={}
      AND event_type='MOVED' AND old_path={} AND new_path={}
      AND created_at >= (SELECT created_at FROM public.personal_migration_plans WHERE id={})
      ORDER BY created_at DESC LIMIT 1""".format(item["file_id"], pg(item["source_path"]), pg(item["target_path"]), pg(plan_id)))
    event_type = "MOVED"
    if not rows and item["effective_lifecycle"] == "deletion_review":
        rows = copy_rows("""SELECT fe.id FROM public.v_file_events_effective fe
          WHERE fe.file_id={} AND fe.event_type='DELETED' AND fe.old_path={}
            AND fe.created_at >= (SELECT created_at FROM public.personal_migration_plans WHERE id={})
            AND EXISTS (
              SELECT 1 FROM public.personal_migration_events verified
              WHERE verified.plan_id={} AND verified.item_id={} AND verified.event_type='verified'
                AND verified.details->>'content_sha256'={}
                AND verified.details->>'target_path'={}
                AND verified.details->>'source_path'={}
                AND verified.details->>'recovery_available'='true'
                AND verified.details->>'qualifies_for_activation'='false'
            ) ORDER BY fe.created_at DESC LIMIT 1""".format(
                item["file_id"], pg(item["source_path"]), pg(plan_id), pg(plan_id),
                pg(item["id"]), pg(str(item["content_sha256"]).lower()),
                pg(item["target_path"]), pg(item["source_path"])))
        event_type = "DELETED"
    if not rows:
        return False
    source = "core_deletion_quarantine" if item["effective_lifecycle"] == "deletion_review" else "core_managed_move"
    event(plan_id, "event_correlated", actor, "{}:{}:correlated:{}".format(plan_id, item["id"], rows[0]["id"]), item["id"],
          {"file_event_id": rows[0]["id"], "file_event_type": event_type,
           "qualifies_for_activation": False, "source": source,
           "physical_purge": False, "recovery_available": True})
    return True


def execute(args: argparse.Namespace) -> int:
    require_confirmation(args.confirm, args.plan_id)
    if not is_approved(args.plan_id):
        raise MigrationSafetyError("plan_not_approved")
    moved = 0
    for item in plan_items(args.plan_id):
        if item["current_status"] not in ("approved", "moving", "moved"):
            continue
        try:
            if not deletion_nomination_is_current(item):
                raise MigrationSafetyError("deletion_nomination_no_longer_current")
            event(args.plan_id, "moving", args.actor, "{}:{}:moving".format(args.plan_id, item["id"]), item["id"])
            if item["current_status"] in ("moving", "moved"):
                result = resume_verified_move(item, allowed_zones=allowed_zones(item))
            else:
                required_free = max(int(args.minimum_free_bytes), int(item["planned_minimum_free_bytes"]))
                result = move_verified(
                    item, minimum_free_bytes=required_free,
                    allowed_zones=allowed_zones(item),
                )
            event(args.plan_id, "moved", args.actor, "{}:{}:moved".format(args.plan_id, item["id"]), item["id"], result)
            event(args.plan_id, "verified", args.actor, "{}:{}:verified".format(args.plan_id, item["id"]), item["id"],
                  dict(result, qualifies_for_activation=False,
                       source=("core_deletion_quarantine" if item["effective_lifecycle"] == "deletion_review" else "core_managed_move"),
                       physical_purge=False, recovery_available=True))
            correlate(args.plan_id, item, args.actor)
            moved += 1
        except (MigrationSafetyError, OSError) as exc:
            event(args.plan_id, "failed", args.actor, "{}:{}:failed:{}".format(args.plan_id, item["id"], uuid.uuid4()), item["id"], {"reason": str(exc)})
            raise
    print(json.dumps({"status": "executed", "plan_id": args.plan_id, "verified": moved}))
    return 0


def reconcile(args: argparse.Namespace) -> int:
    correlated = sum(correlate(args.plan_id, item, args.actor) for item in plan_items(args.plan_id) if item["current_status"] in ("verified", "event_correlated"))
    print(json.dumps({"status": "reconciled", "plan_id": args.plan_id, "correlated": correlated}))
    return 0


def rollback(args: argparse.Namespace) -> int:
    require_confirmation(args.confirm, args.plan_id)
    restored = 0
    for item in reversed(plan_items(args.plan_id)):
        if item["current_status"] not in ("verified", "event_correlated", "rollback_pending", "failed"):
            continue
        event(args.plan_id, "rollback_pending", args.actor, "{}:{}:rollback-pending".format(args.plan_id, item["id"]), item["id"])
        result = rollback_verified(item, allowed_zones=allowed_zones(item))
        event(args.plan_id, "rolled_back", args.actor, "{}:{}:rolled-back".format(args.plan_id, item["id"]), item["id"], result)
        restored += 1
    print(json.dumps({"status": "rolled_back", "plan_id": args.plan_id, "restored": restored}))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="personal-migration-executor")
    sub = result.add_subparsers(dest="action", required=True)
    make = sub.add_parser("plan")
    mode = make.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--create-plan", action="store_true")
    make.add_argument("--limit", type=int, default=10)
    make.add_argument("--minimum-free-bytes", type=int, default=0)
    make.add_argument("--actor", default="core-cli")
    for name in ("approve", "execute", "rollback"):
        command = sub.add_parser(name)
        command.add_argument("plan_id")
        command.add_argument("--confirm", required=True)
        command.add_argument("--actor", default="core-cli")
        if name == "execute":
            command.add_argument("--minimum-free-bytes", type=int, default=0)
    sync = sub.add_parser("reconcile")
    sync.add_argument("plan_id")
    sync.add_argument("--actor", default="core-cli")
    return result


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if getattr(args, "limit", 1) < 1 or getattr(args, "limit", 1) > 100:
        print("limit must be between 1 and 100", file=sys.stderr); return 2
    try:
        return {"plan": plan, "approve": approve, "execute": execute,
                "reconcile": reconcile, "rollback": rollback}[args.action](args)
    except (MigrationSafetyError, subprocess.CalledProcessError, OSError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        print("Personal migration failed: {}".format(detail), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
