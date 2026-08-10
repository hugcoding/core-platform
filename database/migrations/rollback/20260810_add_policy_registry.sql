BEGIN;
DROP VIEW IF EXISTS public.v_current_policies;
DROP TRIGGER IF EXISTS policy_versions_immutable ON public.policy_versions;
DROP TABLE IF EXISTS public.policy_versions;
DROP FUNCTION IF EXISTS public.reject_policy_version_mutation();
COMMIT;
