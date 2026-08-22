-- SCRUM-104: reversible exact-duplicate quarantine pilot; no purge support.
BEGIN;

CREATE TABLE IF NOT EXISTS public.duplicate_cleanup_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_key text NOT NULL UNIQUE,
    contract_version text NOT NULL,
    source_root text NOT NULL DEFAULT '/volume1/data',
    quarantine_root text NOT NULL DEFAULT '/volume1/data/.core/quarantaine/duplicaten',
    max_batch_size integer NOT NULL CHECK (max_batch_size BETWEEN 1 AND 100),
    item_count integer NOT NULL CHECK (item_count BETWEEN 1 AND max_batch_size),
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT duplicate_cleanup_plan_roots_check CHECK (
        source_root = '/volume1/data'
        AND quarantine_root = '/volume1/data/.core/quarantaine/duplicaten'
    )
);

CREATE TABLE IF NOT EXISTS public.duplicate_cleanup_plan_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id uuid NOT NULL REFERENCES public.duplicate_cleanup_plans(id) ON DELETE RESTRICT,
    sequence_no integer NOT NULL CHECK (sequence_no > 0),
    review_event_id uuid NOT NULL REFERENCES public.exact_duplicate_review_events(id) ON DELETE RESTRICT,
    content_group_id uuid NOT NULL REFERENCES public.content_groups(id) ON DELETE RESTRICT,
    leader_file_id bigint NOT NULL REFERENCES public.files(id) ON DELETE RESTRICT,
    redundant_file_id bigint NOT NULL REFERENCES public.files(id) ON DELETE RESTRICT,
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    leader_path text NOT NULL,
    source_path text NOT NULL,
    quarantine_path text NOT NULL,
    mtime_ns bigint NOT NULL,
    policy_id uuid NOT NULL REFERENCES public.policy_versions(id) ON DELETE RESTRICT,
    policy_code text NOT NULL,
    policy_version text NOT NULL,
    policy_snapshot jsonb NOT NULL CHECK (jsonb_typeof(policy_snapshot) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (plan_id, sequence_no),
    UNIQUE (plan_id, redundant_file_id),
    UNIQUE (plan_id, quarantine_path),
    CONSTRAINT duplicate_cleanup_distinct_copies_check CHECK (leader_file_id <> redundant_file_id),
    CONSTRAINT duplicate_cleanup_item_paths_check CHECK (
        leader_path LIKE '/volume1/data/%'
        AND source_path LIKE '/volume1/data/%'
        AND source_path NOT LIKE '/volume1/data/.core/quarantaine/duplicaten/%'
        AND quarantine_path LIKE '/volume1/data/.core/quarantaine/duplicaten/%'
        AND source_path <> quarantine_path
    )
);

CREATE TABLE IF NOT EXISTS public.duplicate_cleanup_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id uuid NOT NULL REFERENCES public.duplicate_cleanup_plans(id) ON DELETE RESTRICT,
    item_id uuid NULL REFERENCES public.duplicate_cleanup_plan_items(id) ON DELETE RESTRICT,
    event_type text NOT NULL CHECK (event_type IN (
        'planned', 'approved', 'quarantine_pending', 'quarantined', 'verified',
        'failed', 'event_correlated', 'rollback_pending', 'rolled_back'
    )),
    idempotency_key text NOT NULL UNIQUE,
    actor text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS duplicate_cleanup_events_plan_created_idx
    ON public.duplicate_cleanup_events(plan_id, created_at DESC);
CREATE INDEX IF NOT EXISTS duplicate_cleanup_events_item_created_idx
    ON public.duplicate_cleanup_events(item_id, created_at DESC) WHERE item_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS duplicate_cleanup_items_redundant_file_idx
    ON public.duplicate_cleanup_plan_items(redundant_file_id, created_at DESC);

CREATE OR REPLACE FUNCTION public.reject_duplicate_cleanup_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'duplicate cleanup plans, items and events are append-only';
END;
$$;

DROP TRIGGER IF EXISTS duplicate_cleanup_plans_immutable ON public.duplicate_cleanup_plans;
CREATE TRIGGER duplicate_cleanup_plans_immutable BEFORE UPDATE OR DELETE ON public.duplicate_cleanup_plans
FOR EACH ROW EXECUTE FUNCTION public.reject_duplicate_cleanup_mutation();
DROP TRIGGER IF EXISTS duplicate_cleanup_plan_items_immutable ON public.duplicate_cleanup_plan_items;
CREATE TRIGGER duplicate_cleanup_plan_items_immutable BEFORE UPDATE OR DELETE ON public.duplicate_cleanup_plan_items
FOR EACH ROW EXECUTE FUNCTION public.reject_duplicate_cleanup_mutation();
DROP TRIGGER IF EXISTS duplicate_cleanup_events_immutable ON public.duplicate_cleanup_events;
CREATE TRIGGER duplicate_cleanup_events_immutable BEFORE UPDATE OR DELETE ON public.duplicate_cleanup_events
FOR EACH ROW EXECUTE FUNCTION public.reject_duplicate_cleanup_mutation();

CREATE OR REPLACE VIEW public.v_duplicate_cleanup_item_status AS
SELECT i.*, latest.event_type AS current_status, latest.details AS latest_details,
       latest.created_at AS status_changed_at
FROM public.duplicate_cleanup_plan_items i
LEFT JOIN LATERAL (
    SELECT e.event_type, e.details, e.created_at
    FROM public.duplicate_cleanup_events e
    WHERE e.item_id = i.id
    ORDER BY e.created_at DESC, e.id DESC LIMIT 1
) latest ON true;

COMMENT ON TABLE public.duplicate_cleanup_plans IS
    'Immutable, explicitly approved plans for reversible exact-duplicate quarantine moves.';
COMMENT ON TABLE public.duplicate_cleanup_events IS
    'Append-only audit evidence for duplicate quarantine and rollback; physical purge is unsupported.';

COMMIT;
