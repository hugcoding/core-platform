#!/usr/bin/env python3
"""Opt-in, read-only JIT comparison in the dashboard container. No file writes.

Run during a quiet period: baseline can consume tens of seconds of NAS CPU.
Both calls share one repeatable-read snapshot; output contains no document data.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path.cwd() if __file__ == "<stdin>" else Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard import app


def main() -> int:
    connect, query_all = app.db_connect, app.query_all
    connection = connect()
    connection.set_session(readonly=True, isolation_level="REPEATABLE READ")

    class Snapshot:
        def __enter__(self):
            return connection

        def __exit__(self, *args):
            return False

    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()

    measurements = []
    try:
        app.db_connect = Snapshot
        for jit in ("on", "off"):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '60s'")
                cursor.execute("SET LOCAL jit = " + jit)
            timings = []

            def measured(conn, sql, *args, **kwargs):
                started = time.monotonic()
                rows = query_all(conn, sql, *args, **kwargs)
                if "w.content_group_id," in sql and "latest_review_id" in sql:
                    timings.append({"seconds": round(time.monotonic() - started, 3),
                                    "rows": len(rows),
                                    "rows_digest": digest(sorted(digest(row) for row in rows))})
                return rows

            app.query_all = measured
            started = time.monotonic()
            result = app.workset(status="all", extension="all", search="", family="all",
                                 review_state="all", review_decision="all", nomination="all",
                                 sort="context", limit=50, offset=0)
            measurement = {"jit": jit, "seconds": round(time.monotonic() - started, 3),
                           "filtered_total": result["filtered_total"],
                           "documents": len(result["documents"]),
                           "documents_digest": digest(result["documents"]),
                           "queries": timings}
            measurements.append(measurement)
            print(json.dumps(measurement), flush=True)
        equal = (len(measurements[0]["queries"]) == len(measurements[1]["queries"]) == 1
                 and measurements[0]["documents_digest"] == measurements[1]["documents_digest"]
                 and measurements[0]["filtered_total"] == measurements[1]["filtered_total"]
                 and [q["rows_digest"] for q in measurements[0]["queries"]]
                 == [q["rows_digest"] for q in measurements[1]["queries"]])
        print(json.dumps({"results_equal": equal}), flush=True)
        return 0 if equal else 1
    finally:
        app.db_connect, app.query_all = connect, query_all
        connection.rollback()
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
