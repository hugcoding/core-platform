from __future__ import annotations

import os
from pathlib import PurePosixPath
from typing import Callable


def validate_scope(path: str | None) -> str | None:
    if path is None:
        return None
    normalized = str(PurePosixPath(path))
    if normalized == "/volume1" or normalized.startswith("/volume1/"):
        return normalized
    raise ValueError("Scope must be /volume1 or a directory below /volume1")


def inspect_file_identity(connector: Callable, path: str | None = None) -> dict:
    scope = validate_scope(path)
    conn = connector()
    conn.set_session(readonly=True, autocommit=False)
    cur = conn.cursor()
    where = "deleted_at IS NULL"
    params: tuple = ()
    if scope:
        where += " AND (path = %s OR path LIKE %s)"
        params = (scope, scope.rstrip("/") + "/%")

    cur.execute(
        f"SELECT id, path, inode FROM files WHERE {where} ORDER BY id",
        params,
    )
    active = cur.fetchall()
    stale = [
        {"file_id": row[0], "path": row[1]}
        for row in active
        if not os.path.exists(row[1])
    ]

    cur.execute(
        f"""
        SELECT inode, count(*), array_agg(id ORDER BY id), array_agg(path ORDER BY path)
        FROM files
        WHERE {where} AND inode IS NOT NULL
        GROUP BY inode HAVING count(*) > 1
        ORDER BY count(*) DESC, inode
        """,
        params,
    )
    inode_groups = [
        {"inode": row[0], "count": row[1], "file_ids": row[2], "paths": row[3]}
        for row in cur.fetchall()
    ]

    event_where = "confidence_level IN ('medium','low','ambiguous')"
    event_params: tuple = ()
    if scope:
        event_where += " AND (new_path = %s OR new_path LIKE %s)"
        event_params = params
    cur.execute(
        f"""
        SELECT id, event_type, file_id, candidate_file_id, new_path,
               confidence_score, confidence_level, decision, reason, created_at
        FROM file_events WHERE {event_where}
        ORDER BY created_at DESC LIMIT 200
        """,
        event_params,
    )
    review_events = cur.fetchall()
    conn.rollback()
    conn.close()
    return {
        "scope": scope or "/volume1 (all configured records)",
        "active_files": len(active),
        "stale_active_paths": stale,
        "shared_inode_groups": inode_groups,
        "review_event_count": len(review_events),
        "review_events": review_events,
    }
