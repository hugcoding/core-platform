BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.personal_migration_plan_items
        WHERE effective_lifecycle = 'deletion_review'
    ) OR EXISTS (
        SELECT 1 FROM public.personal_migration_plans
        WHERE target_root = '/volume1/data'
    ) THEN
        RAISE EXCEPTION 'rollback blocked: deletion-quarantine migration plans exist';
    END IF;
END;
$$;

ALTER TABLE public.personal_migration_plan_items
    DROP CONSTRAINT IF EXISTS personal_migration_item_paths_check;
ALTER TABLE public.personal_migration_plan_items
    ADD CONSTRAINT personal_migration_item_paths_check CHECK (
        source_path LIKE '/volume1/data/%'
        AND target_path ~ '^/volume1/data/Persoonlijk/(Actief|Inactief)/'
        AND source_path <> target_path
    );
ALTER TABLE public.personal_migration_plan_items
    DROP CONSTRAINT IF EXISTS personal_migration_plan_items_effective_lifecycle_check;
ALTER TABLE public.personal_migration_plan_items
    ADD CONSTRAINT personal_migration_plan_items_effective_lifecycle_check
    CHECK (effective_lifecycle IN ('active', 'archive'));
ALTER TABLE public.personal_migration_plan_items
    DROP COLUMN IF EXISTS deletion_nomination_id;

ALTER TABLE public.personal_migration_plans
    DROP CONSTRAINT IF EXISTS personal_migration_plan_roots_check;
ALTER TABLE public.personal_migration_plans
    ADD CONSTRAINT personal_migration_plan_roots_check CHECK (
        (source_root = '/volume1/data' OR source_root LIKE '/volume1/data/%')
        AND target_root = '/volume1/data/Persoonlijk'
    );

COMMIT;
