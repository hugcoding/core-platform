-- Make explicit batch approval the control boundary for policy-backed workset migration.
BEGIN;

ALTER TABLE public.personal_migration_plan_items
    ADD COLUMN IF NOT EXISTS lifecycle_basis text NOT NULL DEFAULT 'human_review';
ALTER TABLE public.personal_migration_plan_items
    ADD COLUMN IF NOT EXISTS target_path_basis text NOT NULL DEFAULT 'human_review';

ALTER TABLE public.personal_migration_plan_items
    ALTER COLUMN lifecycle_reviewed_at DROP NOT NULL;
ALTER TABLE public.personal_migration_plan_items
    ALTER COLUMN target_path_reviewed_at DROP NOT NULL;

ALTER TABLE public.personal_migration_plan_items
    DROP CONSTRAINT IF EXISTS personal_migration_lifecycle_basis_check;
ALTER TABLE public.personal_migration_plan_items
    ADD CONSTRAINT personal_migration_lifecycle_basis_check
    CHECK (lifecycle_basis IN ('human_review', 'workset_policy', 'deletion_nomination'));

ALTER TABLE public.personal_migration_plan_items
    DROP CONSTRAINT IF EXISTS personal_migration_target_path_basis_check;
ALTER TABLE public.personal_migration_plan_items
    ADD CONSTRAINT personal_migration_target_path_basis_check
    CHECK (target_path_basis IN ('human_review', 'core_proposal', 'zone_fallback', 'deletion_quarantine'));

ALTER TABLE public.personal_migration_plan_items
    ALTER COLUMN lifecycle_basis DROP DEFAULT;
ALTER TABLE public.personal_migration_plan_items
    ALTER COLUMN target_path_basis DROP DEFAULT;

COMMENT ON COLUMN public.personal_migration_plan_items.lifecycle_basis IS
    'Immutable explanation: human lifecycle review, current workset policy, or deletion nomination.';
COMMENT ON COLUMN public.personal_migration_plan_items.target_path_basis IS
    'Immutable explanation: human path, CORE proposal, safe zone fallback, or deletion quarantine.';

COMMIT;
