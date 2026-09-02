# Workset query latency: dashboard-local JIT setting

## Measurement, 2 September 2026

Read-only benchmark in the running dashboard container against nasdb_test.
Two calls used one REPEATABLE READ snapshot, status=all, review_state=all,
limit=50. No file writes, migration execution, or global database settings.

| Measurement | JIT on | JIT off |
| --- | ---: | ---: |
| Full Workset function | 34.948 s | 3.607 s |
| Document query | 32.672 s | 1.421 s |
| Query rows / returned cards | 113 / 50 | 113 / 50 |

Row digests and document payload digests matched. This is endpoint-function
latency, not a guarantee for total browser load under concurrent activity.
The baseline ran first (warm-cache/order effects are possible). A separate
JIT-off EXPLAIN ANALYZE measured 1.674 s for the document query. Separate full
endpoint tests measured 3.629 and 4.179 s with JIT off versus 38.446 s baseline.

## Change

dashboard.app.db_connect passes options="-c jit=off" at connection startup.
This avoids the high compilation overhead of expanded Workset views on this
NAS. It applies to dashboard sessions (including queue/read endpoints), not
scanner, workers, all PostgreSQL sessions, or persistent server configuration.
Queries, transactions, result semantics, review writes and safety checks are
unchanged. No caching or delayed data freshness is introduced.

## Repeat the check (optional, during a quiet period)

After deployment, from the NAS repository:

```sh
docker exec nas-dashboard-1 python tools/runtime/benchmark_workset_reads.py
```

This intentionally runs the expensive old setting once and the new setting
once. It uses read-only transactions with a 60-second per-statement timeout,
rolls back and closes the connection, prints timings and digests (no document
names/content), and exits nonzero if results differ. Do not poll this benchmark.

## Deployment

Merge/pull, then rebuild/recreate the dashboard using the normal deployment
workflow. No database migration or PostgreSQL restart required. Validate in
the browser with one Workset tab and observe Docker CPU stats during and after
loading. The remaining few seconds and other independent background queries
are separate opportunities, not claimed as solved by this change.
