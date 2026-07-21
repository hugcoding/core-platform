# ADR-0002 - Separate full reconciliation from interval scanning

## Status

Accepted

## Context

The polling scanner inspected approximately 220,130 files every cycle. A cycle took 275–299 seconds and was followed by only 30 seconds of rest. Measurements showed an effective scanner duty-cycle of about 90%, while 12,987,681 file inspections across 59 cycles produced only 291 events.

ADR-0001 remains valid: polling inside Docker is more reliable on this Synology environment than host- or container-based inotify. The polling cadence and reconciliation semantics need refinement.

## Decision

The scanner uses two modes:

- `interval`: scan one top-level root per cycle for new or changed files;
- `full`: scan every allowed root and then reconcile missing files.

Interval scans never increment missing counters and never emit `DELETE`. They update file signatures while preserving the last successful full-sweep marker.

Full reconciliation runs only after every discovered root completes successfully. An empty root set or walk error aborts the sweep before reconciliation. Missing counters are measured in completed full sweeps.

The default post-scan interval is 600 seconds. Full reconciliation runs at most once per 3,600 seconds, measured from completion of the preceding full sweep. The first scan after process startup is full.

## Consequences

Positive:

- partial scans cannot create false deletes;
- filesystem and Redis load are substantially reduced;
- changed files are still detected between full sweeps;
- scan sessions distinguish `full` and `interval` work;
- per-root timing makes later shard balancing evidence-based.

Negative:

- change latency depends on root rotation;
- deletion confirmation depends on full-sweep cadence and threshold;
- large top-level roots may still require subdivision;
- Redis batching and bounded stream retention remain follow-up work.

## Rollback

Set `FULL_SCAN_INTERVAL` equal to `SCAN_INTERVAL` and redeploy the previous scanner version. Existing signature state remains readable because the stored tuple format is unchanged.

## Date

2026-07-21
