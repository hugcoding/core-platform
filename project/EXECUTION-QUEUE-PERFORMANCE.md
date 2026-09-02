# Controlled-execution queue preview performance

Scope: opening/loading the queue. No batch approval, file movement or resource
throttling is performed by this change or its benchmark.

## Findings and change

Turning off JIT alone did not materially improve this endpoint (~7.7 s).
Three targeted changes reduce repeated database work:

- Materialize exact-duplicate group evidence once per SQL statement. All
  existing handoff eligibility checks and output columns are unchanged.
- Materialize known locations once for flat-path correction and preselect
  files with a registered OR current path under Persoonlijk. Keep the final
  exact flat-path check; migrated files with old import paths remain included.
- Evaluate personal migration inventory once, sharing it between the first
  500 candidates and the referenced golden records outside that window.

There is no persistent cache, no reduced evidence validation, and no changed
batch limit. Approval still revalidates candidates; the worker checks files.

## Read-only NAS measurements (2 September 2026)

Existing dashboard container, jit=off in both cases. Proposed function and view
SQL inlined into diagnostic reads, without replacing production views.

| Run | Before elapsed | After elapsed | Before CPU | After CPU | CPU reduction |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 7.551 s | 2.617 s | 6.922 s | 2.438 s | 64.8% |
| 2 | 7.846 s | 2.790 s | 6.939 s | 2.900 s | 58.2% |

Both runs returned matching full response digests: 183 ready, 1391 blocked.
CPU is cumulative CPU time from the Postgres container's cgroup v1 counter;
it includes concurrent background work. Runs are sequential and warm-cache
effects are possible. This is not a promise to halve instantaneous CPU percent,
nor a measurement of a running file-migration batch.

The NAS-host diagnostic is `tools/runtime/benchmark_execution_queue_reads.py`.
It needs an existing dashboard container and reads repository source locally.
It starts no batches, changes no production schema, sets read-only connections
and bounded statement timeouts. It compares the deployed baseline with the
proposed code, so run before deployment in a quiet period, not as polling.

## Deploy

Merge/pull, apply `20260902_optimize_exact_duplicate_handoff.sql` with psql
ON_ERROR_STOP=1, then run `core dashboard deploy`. No PostgreSQL restart.
The migration replaces one view atomically, without changing files or audit
rows. Earlier JIT optimization is retained on this branch.
