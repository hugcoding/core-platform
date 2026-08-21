BEGIN;

CREATE TABLE IF NOT EXISTS public.personal_migration_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_key text NOT NULL UNIQUE,
    contract_version text NOT NULL,
    source_root text NOT NULL,
    target_root text NOT NULL,
    max_batch_size integer NOT NULL CHECK (max_batch_size BETWEEN 1 AND 100),
    minimum_free_bytes bigint NOT NULL DEFAULT 0 CHECK (minimum_free_bytes >= 0),
    item_count integer NOT NULL CHECK (item_count BETWEEN 1 AND max_batch_size),
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT personal_migration_plan_roots_check CHECK (
        source_root LIKE '/volume1/data/%'
        AND target_root = '/volume1/data/Persoonlijk'
    )
);

CREATE TABLE IF NOT EXISTS public.personal_migration_plan_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id uuid NOT NULL REFERENCES public.personal_migration_plans(id) ON DELETE RESTRICT,
    sequence_no integer NOT NULL CHECK (sequence_no > 0),
    file_id integer NOT NULL REFERENCES public.files(id) ON DELETE RESTRICT,
    content_group_id uuid NOT NULL REFERENCES public.content_groups(id) ON DELETE RESTRICT,
    content_sha256 text NOT NULL CHECK (length(content_sha256) = 64),
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    source_path text NOT NULL,
    target_path text NOT NULL,
    mtime_ns bigint NOT NULL,
    effective_lifecycle text NOT NULL CHECK (effective_lifecycle IN ('active', 'archive')),
    lifecycle_reviewed_at timestamptz NOT NULL,
    target_path_reviewed_at timestamptz NOT NULL,
    duplicate_resolution text NULL CHECK (duplicate_resolution IN ('golden_only', 'keep_copy', 'archive_copy', 'deletion_review')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (plan_id, sequence_no),
    UNIQUE (plan_id, file_id),
    UNIQUE (plan_id, target_path),
    CONSTRAINT personal_migration_item_paths_check CHECK (
        source_path LIKE '/volume1/data/%'
        AND target_path ~ '^/volume1/data/Persoonlijk/(Actief|Inactief)/'
        AND source_path <> target_path
    )
);

CREATE TABLE IF NOT EXISTS public.personal_migration_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id uuid NOT NULL REFERENCES public.personal_migration_plans(id) ON DELETE RESTRICT,
    item_id uuid NULL REFERENCES public.personal_migration_plan_items(id) ON DELETE RESTRICT,
    event_type text NOT NULL CHECK (event_type IN (
        'planned', 'approved', 'moving', 'moved', 'verified', 'failed',
        'rollback_pending', 'rolled_back', 'event_correlated'
    )),
    idempotency_key text NOT NULL UNIQUE,
    actor text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS personal_migration_events_plan_created_idx
    ON public.personal_migration_events(plan_id, created_at DESC);
CREATE INDEX IF NOT EXISTS personal_migration_events_item_created_idx
    ON public.personal_migration_events(item_id, created_at DESC) WHERE item_id IS NOT NULL;

CREATE OR REPLACE FUNCTION public.reject_personal_migration_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'personal migration plans, items and events are append-only';
END;
$$;

DROP TRIGGER IF EXISTS personal_migration_plans_immutable ON public.personal_migration_plans;
CREATE TRIGGER personal_migration_plans_immutable BEFORE UPDATE OR DELETE ON public.personal_migration_plans
FOR EACH ROW EXECUTE FUNCTION public.reject_personal_migration_mutation();
DROP TRIGGER IF EXISTS personal_migration_plan_items_immutable ON public.personal_migration_plan_items;
CREATE TRIGGER personal_migration_plan_items_immutable BEFORE UPDATE OR DELETE ON public.personal_migration_plan_items
FOR EACH ROW EXECUTE FUNCTION public.reject_personal_migration_mutation();
DROP TRIGGER IF EXISTS personal_migration_events_immutable ON public.personal_migration_events;
CREATE TRIGGER personal_migration_events_immutable BEFORE UPDATE OR DELETE ON public.personal_migration_events
FOR EACH ROW EXECUTE FUNCTION public.reject_personal_migration_mutation();

CREATE OR REPLACE VIEW public.v_personal_migration_item_status AS
SELECT i.*, latest.event_type AS current_status, latest.details AS latest_details,
       latest.created_at AS status_changed_at
FROM public.personal_migration_plan_items i
LEFT JOIN LATERAL (
    SELECT e.event_type, e.details, e.created_at
    FROM public.personal_migration_events e
    WHERE e.item_id = i.id
    ORDER BY e.created_at DESC, e.id DESC LIMIT 1
) latest ON true;

COMMENT ON TABLE public.personal_migration_plans IS 'Immutable approved-scope plans for controlled personal document moves.';
COMMENT ON TABLE public.personal_migration_events IS 'Append-only lifecycle, verification, correlation and rollback evidence for controlled moves.';
COMMIT;
