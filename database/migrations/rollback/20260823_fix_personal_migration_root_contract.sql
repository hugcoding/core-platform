-- Guarded rollback: the original constraint cannot be restored after a canonical
-- /volume1/data plan exists without making valid audit evidence invalid.
BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.personal_migration_plans
        WHERE source_root = '/volume1/data'
    ) THEN
        RAISE EXCEPTION
            'rollback blocked: canonical /volume1/data migration plans exist';
    END IF;
END;
$$;

ALTER TABLE public.personal_migration_plans
    DROP CONSTRAINT IF EXISTS personal_migration_plan_roots_check;
ALTER TABLE public.personal_migration_plans
    ADD CONSTRAINT personal_migration_plan_roots_check CHECK (
        source_root LIKE '/volume1/data/%'
        AND target_root = '/volume1/data/Persoonlijk'
    );

COMMIT;
