BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.personal_migration_plan_items
        WHERE lifecycle_basis <> 'human_review' OR target_path_basis <> 'human_review'
    ) THEN
        RAISE EXCEPTION 'rollback blocked: policy-backed personal migration plans exist';
    END IF;
END;
$$;

ALTER TABLE public.personal_migration_plan_items
    DROP CONSTRAINT IF EXISTS personal_migration_target_path_basis_check;
ALTER TABLE public.personal_migration_plan_items
    DROP CONSTRAINT IF EXISTS personal_migration_lifecycle_basis_check;
ALTER TABLE public.personal_migration_plan_items
    DROP COLUMN IF EXISTS target_path_basis;
ALTER TABLE public.personal_migration_plan_items
    DROP COLUMN IF EXISTS lifecycle_basis;
ALTER TABLE public.personal_migration_plan_items
    ALTER COLUMN lifecycle_reviewed_at SET NOT NULL;
ALTER TABLE public.personal_migration_plan_items
    ALTER COLUMN target_path_reviewed_at SET NOT NULL;

COMMIT;
