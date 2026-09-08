BEGIN;
DROP VIEW IF EXISTS public.v_effective_document_workset;
DROP FUNCTION IF EXISTS public.core_workset_family(text, text, text);
DROP FUNCTION IF EXISTS public.core_normalized_document_identity(text);
COMMIT;
