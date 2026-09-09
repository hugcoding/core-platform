BEGIN;
DROP VIEW IF EXISTS public.v_workset_classification_rules_v2;
DROP FUNCTION IF EXISTS public.core_workset_family_v2(text, text, text, text);
COMMIT;
