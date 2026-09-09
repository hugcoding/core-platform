-- SCRUM-147: SQL companion for the versioned multilingual proposal rules.
BEGIN;
SET LOCAL lock_timeout = '2s';

CREATE OR REPLACE FUNCTION public.core_workset_family_v2(
    filename text,
    current_path text,
    source_context_path text,
    accepted_family text DEFAULT NULL
) RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $function$
    WITH evidence AS (
        SELECT
            ' ' || lower(regexp_replace(coalesce(filename, ''), '[^a-zA-Z0-9]+', ' ', 'g')) || ' ' AS name,
            ' ' || lower(regexp_replace(concat_ws(' ', current_path, source_context_path), '[^a-zA-Z0-9]+', ' ', 'g')) || ' ' AS paths
    ), domains AS (
        SELECT *,
            name LIKE ANY (ARRAY['% employment agreement %','% employment contract %','% secondment agreement %','% compensation letter %','% job profile %']) AS work_hit,
            (name || paths) LIKE ANY (ARRAY['% kadastrale kaart %','% kadastraal %','% leveringsakte %','% mjop %','% meerjarenonderhoudsplan %','% badkamer %','% elektra %','% uitbouw %']) AS home_hit,
            (name || paths) LIKE ANY (ARRAY['% pension scheme %','% payroll %']) AS finance_hit,
            (name || paths) LIKE ANY (ARRAY['% programmeren %','% java %','% modopdr %']) AS learning_hit
        FROM evidence
    )
    SELECT CASE
        WHEN nullif(lower(trim(accepted_family)), '') IS NOT NULL THEN lower(trim(accepted_family))
        WHEN (work_hit::int + home_hit::int + finance_hit::int + learning_hit::int) > 1 THEN 'general'
        WHEN name LIKE ANY (ARRAY['% employment agreement %','% employment contract %','% secondment agreement %','% compensation letter %']) THEN 'employment_documents'
        WHEN name LIKE '% job profile %' THEN 'vacancies'
        WHEN (name || paths) LIKE '% pension scheme %' THEN 'pension_documents'
        WHEN (name || paths) LIKE '% payroll %' THEN 'salary_slips'
        WHEN (name || paths) LIKE ANY (ARRAY['% kadastrale kaart %','% kadastraal %','% leveringsakte %','% levering %']) THEN 'property_documents'
        WHEN (name || paths) LIKE ANY (ARRAY['% mjop %','% meerjarenonderhoudsplan %']) THEN 'vve_documents'
        WHEN (name || paths) LIKE ANY (ARRAY['% programmeren %','% java %','% modopdr %']) THEN 'course_material'
        WHEN (name || paths) LIKE ANY (ARRAY['% badkamer %','% tuin %','% elektra %','% uitbouw %','% verbouwing %']) THEN 'home_maintenance'
        WHEN name LIKE '% offerte %' AND paths LIKE ANY (ARRAY['% woning %','% verbouwing %','% vve %']) THEN 'home_maintenance'
        ELSE public.core_workset_family(filename, concat_ws(' ', current_path, source_context_path), NULL)
    END
    FROM domains;
$function$;

COMMENT ON FUNCTION public.core_workset_family_v2(text, text, text, text) IS
    'classification-signals-v2 SQL companion; historical paths are evidence only and never execution targets.';

CREATE OR REPLACE VIEW public.v_workset_classification_rules_v2 AS
SELECT
    w.*,
    public.core_workset_family_v2(
        w.filename,
        w.path,
        source.source_context_path,
        w.accepted_family
    ) AS rules_v2_family,
    source.source_context_path AS rules_v2_source_context_path,
    CASE
        WHEN w.review_family <> 'general' AND nullif(w.review_category, '') IS NOT NULL THEN w.review_category
        WHEN public.core_workset_family_v2(w.filename, w.path, source.source_context_path, w.accepted_family)
             IN ('employment_documents', 'vacancies') THEN 'work_career'
        WHEN public.core_workset_family_v2(w.filename, w.path, source.source_context_path, w.accepted_family)
             IN ('salary_slips', 'pension_documents') THEN 'finance'
        WHEN public.core_workset_family_v2(w.filename, w.path, source.source_context_path, w.accepted_family)
             IN ('property_documents', 'vve_documents', 'home_maintenance') THEN 'home_living'
        WHEN public.core_workset_family_v2(w.filename, w.path, source.source_context_path, w.accepted_family)
             = 'course_material' THEN 'learning_development'
        ELSE coalesce(nullif(w.review_category, ''), 'needs_review')
    END AS rules_v2_category
FROM public.v_effective_document_workset w
LEFT JOIN public.v_workset_source_context source ON source.file_id = w.file_id;

COMMENT ON VIEW public.v_workset_classification_rules_v2 IS
    'Read-only SQL projection of classification-signals-v2 for parity checks and pending/general measurement.';

COMMIT;
