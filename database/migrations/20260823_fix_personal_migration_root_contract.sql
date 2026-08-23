-- SCRUM-97: align the deployed plan-root constraint with the safe runtime contract.
BEGIN;

ALTER TABLE public.personal_migration_plans
    DROP CONSTRAINT IF EXISTS personal_migration_plan_roots_check;
ALTER TABLE public.personal_migration_plans
    ADD CONSTRAINT personal_migration_plan_roots_check CHECK (
        (source_root = '/volume1/data' OR source_root LIKE '/volume1/data/%')
        AND target_root = '/volume1/data/Persoonlijk'
    );

COMMENT ON CONSTRAINT personal_migration_plan_roots_check
    ON public.personal_migration_plans IS
    'Allows the canonical /volume1/data source root or a child while keeping the target fixed to /volume1/data/Persoonlijk.';

COMMIT;
