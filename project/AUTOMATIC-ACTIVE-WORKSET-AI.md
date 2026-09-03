# Automatic AI advice for active documents

## Scope and behaviour

The background AI worker discovers current Workset golden records in keyset
pages of 25, every 300 seconds. It uses the effective lifecycle, including human
overrides and their expiry, not merely the folder name. CORE category rules and
taxonomy keyword fallback run first. Only documents with no category proposal
are queued. Existing classification, any explicit target-path review (including
Later/Skip), and reviewed redundant copies are left alone.

Automatic jobs are marked `core-auto-active-v1`, with priority 100 (manual active
requests have priority 300). Content/model/prompt-bound attempts are reused;
failed, dismissed and abstained attempts do not cause endless rediscovery.
Eligibility is rechecked before extraction. Queue size is capped at 20 open jobs
for discovery; manual requests remain possible. No new model/provider is added.

Ready proposals prefill only category/family and display AI provenance, reason,
confidence, model and prompt information. They are not accepted automatically.
User edits, reviewed records and known CORE categories are not overwritten.
The accepted classification records the proposal ID. No privacy/lifecycle
decisions or file moves are performed by automatic prefilling.

## Load protection and limitations

- Discovery is worker-only: no enqueue or inference in Workset HTTP requests.
- One worker processes one inference at a time, with a cooldown for automatic jobs.
- CPU/load, available memory and scanner lag gates apply to automatic jobs.
- Worker container capped at 0.5 CPU; existing inference endpoint remains external
  to this NAS worker. This cap does not cap PostgreSQL or the model server.
- Database sessions disable JIT and use 5s statement/500ms lock timeouts;
  discovery has a stricter 2s statement timeout and a five-minute retry interval.
- Scan diagnostics: Redis hash `workset_ai_worker:auto`; timeout/errors are visible.
- On this NAS, read-only EXPLAIN ANALYZE for one page measured 1208 ms after
  removing the unnecessary quarantine-execution joins (previously 2549 ms).
  This is not a promise of zero impact or a full-load benchmark.
- OCR is reused when available; missing text produces an explicit OCR advice,
  not an invented category. This change does not enable automatic OCR.

## Deployment (explicit operator action)

After merge and pull, apply the index migration, then set in the existing .env:

```text
CORE_AI_AUTO_ACTIVE_ENABLED=true
CORE_AI_AUTO_INTERVAL_SECONDS=300
```

```sh
core git pull
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test < database/migrations/20260904_auto_workset_ai_indexes.sql
docker compose up -d --build dashboard workset_ai_worker
```

The flag defaults to false until explicitly enabled. To stop discovery set it
back to false and recreate the worker; existing queued jobs are not deleted.
Do not disable the worker to clear jobs: retain their audit trail.
After activation verify a pending `core-auto-active-v1` job, then its ready
proposal and AI-labelled category/family prefill on an active document.
