BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.scan_sessions WHERE type = 'hash_backfill') THEN
        RAISE EXCEPTION 'rollback blocked: hash_backfill session history exists';
    END IF;
END
$$;

ALTER TABLE public.scan_sessions
    DROP CONSTRAINT IF EXISTS scan_sessions_type_check;

ALTER TABLE public.scan_sessions
    ADD CONSTRAINT scan_sessions_type_check
    CHECK (type IN ('full', 'interval', 'watcher'));

COMMIT;
