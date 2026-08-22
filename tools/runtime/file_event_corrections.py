#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os

import psycopg2
import psycopg2.extras


CONFIRMATION = "INVALIDATE_NON_MATERIAL_WATCHER_EVENTS"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="file-event-corrections")
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
    if args.apply and args.confirm != CONFIRMATION:
        raise SystemExit(f"--apply requires --confirm {CONFIRMATION}")

    conn = connection()
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
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
            evidence = {
                "event_created_at": row["created_at"].isoformat(),
                "current_filesystem_mtime": row["modified_at_fs"],
                "rule": "watcher_event_more_than_5m_after_unchanged_filesystem_mtime",
            }
            cur.execute("""
                INSERT INTO public.file_event_corrections (
                    file_event_id, correction_type, reason, evidence
                ) VALUES (%s, 'invalidated_as_non_material', %s, %s::jsonb)
                ON CONFLICT (file_event_id, correction_type) DO NOTHING
            """, (
                row["file_event_id"],
                "Watcher notification cannot represent the recorded filesystem modification",
                json.dumps(evidence),
            ))
            inserted += cur.rowcount
        conn.commit()
    else:
        conn.rollback()

    print(json.dumps({
        "status": "applied" if args.apply else "dry_run",
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
