BEGIN;

ALTER TABLE public.scan_sessions
    DROP CONSTRAINT IF EXISTS scan_sessions_type_check;

ALTER TABLE public.scan_sessions
    ADD CONSTRAINT scan_sessions_type_check
    CHECK (type IN ('full', 'interval', 'watcher', 'hash_backfill'));

COMMIT;
