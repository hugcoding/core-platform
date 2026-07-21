BEGIN;

-- Older deployments used `done`; newer schema dumps documented `finished`.
-- Accept both so rolling upgrades and existing callers remain compatible.
ALTER TABLE public.scan_sessions
    DROP CONSTRAINT IF EXISTS scan_sessions_status_check;

ALTER TABLE public.scan_sessions
    ADD CONSTRAINT scan_sessions_status_check
    CHECK (status IN ('running', 'done', 'finished', 'failed', 'aborted'));

CREATE OR REPLACE FUNCTION public.finish_scan_session(sid uuid) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE public.scan_sessions
    SET finished_at = NOW(), status = 'finished'
    WHERE id = sid;
END;
$$;

CREATE OR REPLACE FUNCTION public.is_scan_complete(sid uuid) RETURNS boolean
LANGUAGE plpgsql AS $$
DECLARE complete boolean;
BEGIN
    SELECT status IN ('done', 'finished') AND jobs_processed >= jobs_enqueued
    INTO complete
    FROM public.scan_sessions
    WHERE id = sid;
    RETURN COALESCE(complete, FALSE);
END;
$$;

COMMIT;
