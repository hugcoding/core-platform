#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os

import psycopg2
import psycopg2.extras


CONFIRMATION = "INVALIDATE_NON_MATERIAL_WATCHER_EVENTS"
DUPLICATE_DELETE_CONFIRMATION = "INVALIDATE_DUPLICATE_DELETE_OBSERVATIONS"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="file-event-corrections")
    result.add_argument(
        "--kind", choices=("read-events", "duplicate-deletes"), default="read-events"
    )
    result.add_argument("--limit", type=int, default=100)
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    result.add_argument("--confirm")
    return result


def connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT")),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASS"),
        dbname=os.getenv("DB_NAME"),
    )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.limit < 1:
        raise SystemExit("--limit must be positive")
    confirmation = (
        DUPLICATE_DELETE_CONFIRMATION if args.kind == "duplicate-deletes" else CONFIRMATION
    )
    if args.apply and args.confirm != confirmation:
        raise SystemExit(f"--apply requires --confirm {confirmation}")

    conn = connection()
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if args.kind == "duplicate-deletes":
        cur.execute("""
            SELECT scanner.id AS file_event_id, scanner.file_id,
                   scanner.old_path, scanner.created_at,
                   watcher.id AS watcher_event_id,
                   watcher.created_at AS watcher_created_at
            FROM public.v_file_events_effective scanner
            JOIN LATERAL (
                SELECT candidate.id, candidate.created_at
                FROM public.v_file_events_effective candidate
                WHERE candidate.file_id = scanner.file_id
                  AND candidate.event_type = 'DELETED'
                  AND candidate.source = 'filesystem_watcher'
                  AND candidate.old_path = scanner.old_path
                  AND candidate.created_at < scanner.created_at
                ORDER BY candidate.created_at DESC, candidate.id DESC
                LIMIT 1
            ) watcher ON true
            WHERE scanner.event_type = 'DELETED'
              AND scanner.source = 'polling_scanner'
              AND scanner.old_path IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM public.v_file_events_effective intervening
                  WHERE intervening.file_id = scanner.file_id
                    AND intervening.created_at > watcher.created_at
                    AND intervening.created_at < scanner.created_at
                    AND intervening.event_type IN (
                        'RESTORED', 'CREATED', 'MOVED', 'RENAMED'
                    )
              )
            ORDER BY scanner.created_at, scanner.id
            LIMIT %s
        """, (args.limit,))
    else:
        cur.execute("""
        SELECT event.id AS file_event_id, event.file_id, event.new_path,
               event.created_at, files.modified_at_fs
        FROM public.file_events event
        JOIN public.files files
          ON files.id = event.file_id AND files.path = event.new_path
        WHERE event.event_type = 'MODIFIED'
          AND event.source = 'filesystem_watcher'
          AND event.event_status <> 'invalidated'
          AND files.modified_at_fs IS NOT NULL
          AND event.created_at > to_timestamp(files.modified_at_fs) + interval '5 minutes'
          AND NOT EXISTS (
              SELECT 1 FROM public.file_event_corrections correction
              WHERE correction.file_event_id = event.id
                AND correction.correction_type = 'invalidated_as_non_material'
          )
        ORDER BY event.created_at, event.id
        LIMIT %s
        """, (args.limit,))
    rows = cur.fetchall()

    inserted = 0
    if args.apply:
        for row in rows:
            if args.kind == "duplicate-deletes":
                correction_type = "duplicate_observation"
                reason = "Polling scanner repeated an effective watcher DELETE without an intervening restore or move"
                evidence = {
                    "scanner_event_created_at": row["created_at"].isoformat(),
                    "watcher_event_id": str(row["watcher_event_id"]),
                    "watcher_event_created_at": row["watcher_created_at"].isoformat(),
                    "file_id": row["file_id"],
                    "old_path": row["old_path"],
                    "rule": "same_file_path_watcher_delete_precedes_scanner_delete_without_intervening_state_change",
                }
            else:
                correction_type = "invalidated_as_non_material"
                reason = "Watcher notification cannot represent the recorded filesystem modification"
                evidence = {
                    "event_created_at": row["created_at"].isoformat(),
                    "current_filesystem_mtime": row["modified_at_fs"],
                    "rule": "watcher_event_more_than_5m_after_unchanged_filesystem_mtime",
                }
            cur.execute("""
                INSERT INTO public.file_event_corrections (
                    file_event_id, correction_type, reason, evidence
                ) VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (file_event_id, correction_type) DO NOTHING
            """, (
                row["file_event_id"],
                correction_type,
                reason,
                json.dumps(evidence),
            ))
            inserted += cur.rowcount
        conn.commit()
    else:
        conn.rollback()

    print(json.dumps({
        "status": "applied" if args.apply else "dry_run",
        "kind": args.kind,
        "candidates": len(rows),
        "corrections_inserted": inserted,
        "original_events_deleted": False,
        "file_mutations": False,
    }, sort_keys=True))
    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
