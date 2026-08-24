-- Extend the controlled personal migration executor with reversible deletion-review quarantine.
BEGIN;

ALTER TABLE public.personal_migration_plan_items
    ADD COLUMN IF NOT EXISTS deletion_nomination_id uuid NULL
        REFERENCES public.document_lifecycle_nomination_events(id) ON DELETE RESTRICT;

ALTER TABLE public.personal_migration_plan_items
    DROP CONSTRAINT IF EXISTS personal_migration_plan_items_effective_lifecycle_check;
ALTER TABLE public.personal_migration_plan_items
    ADD CONSTRAINT personal_migration_plan_items_effective_lifecycle_check
    CHECK (effective_lifecycle IN ('active', 'archive', 'deletion_review'));

ALTER TABLE public.personal_migration_plan_items
    DROP CONSTRAINT IF EXISTS personal_migration_item_paths_check;
ALTER TABLE public.personal_migration_plan_items
    ADD CONSTRAINT personal_migration_item_paths_check CHECK (
        source_path LIKE '/volume1/data/%'
        AND (
            (effective_lifecycle IN ('active', 'archive')
             AND target_path ~ '^/volume1/data/Persoonlijk/(Actief|Inactief)/'
             AND deletion_nomination_id IS NULL)
            OR
            (effective_lifecycle = 'deletion_review'
             AND target_path LIKE '/volume1/data/.core/quarantaine/verwijderreview/%'
             AND deletion_nomination_id IS NOT NULL
             AND duplicate_resolution = 'deletion_review')
        )
        AND source_path <> target_path
    );

ALTER TABLE public.personal_migration_plans
    DROP CONSTRAINT IF EXISTS personal_migration_plan_roots_check;
ALTER TABLE public.personal_migration_plans
    ADD CONSTRAINT personal_migration_plan_roots_check CHECK (
        (source_root = '/volume1/data' OR source_root LIKE '/volume1/data/%')
        AND target_root IN ('/volume1/data/Persoonlijk', '/volume1/data')
    );

COMMENT ON COLUMN public.personal_migration_plan_items.deletion_nomination_id IS
    'Immutable lineage to the active human deletion-review nomination that overrode Actief/Inactief.';

COMMIT;
