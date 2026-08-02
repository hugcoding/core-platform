BEGIN;

CREATE INDEX IF NOT EXISTS idx_semantic_runs_created_at
    ON public.semantic_runs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_semantic_documents_file_run
    ON public.semantic_documents (file_id, run_id);

CREATE OR REPLACE VIEW public.v_semantic_golden_records AS
WITH copy_counts AS (
    SELECT content_group_id, count(*)::integer AS exact_copy_count
    FROM public.content_group_members
    GROUP BY content_group_id
),
latest_semantic AS (
    SELECT DISTINCT ON (sd.file_id)
        sd.file_id,
        sd.run_id,
        sd.content_group_id,
        sd.content_sha256,
        sd.status AS document_status,
        sd.characters,
        sd.words,
        sd.pages,
        sd.estimated_tokens,
        sd.chunk_count,
        sd.error_type,
        sd.error_reason,
        sd.updated_at AS semantic_updated_at,
        sr.environment,
        sr.status AS run_status,
        sr.extractor_version,
        sr.chunker_version,
        sr.created_at AS run_created_at
    FROM public.semantic_documents sd
    JOIN public.semantic_runs sr ON sr.id = sd.run_id
    ORDER BY sd.file_id, sr.created_at DESC, sr.id DESC
)
SELECT
    cg.id AS content_group_id,
    cg.golden_file_id,
    f.path AS golden_path,
    f.filename AS golden_filename,
    f.extension,
    f.size_bytes,
    f.content_sha256,
    COALESCE(cc.exact_copy_count, 0) AS exact_copy_count,
    cg.confidence AS golden_confidence,
    cg.selection_status AS golden_selection_status,
    cg.algorithm_version AS golden_algorithm_version,
    cg.selected_at AS golden_selected_at,
    ls.run_id AS semantic_run_id,
    ls.environment AS semantic_environment,
    ls.run_status AS semantic_run_status,
    ls.document_status AS semantic_document_status,
    ls.extractor_version,
    ls.chunker_version,
    ls.characters,
    ls.words,
    ls.pages,
    ls.estimated_tokens,
    ls.chunk_count,
    ls.error_type,
    ls.error_reason,
    ls.run_created_at,
    ls.semantic_updated_at,
    CASE
        WHEN ls.file_id IS NULL THEN 'not_processed'
        WHEN ls.content_sha256 IS DISTINCT FROM f.content_sha256 THEN 'stale'
        WHEN ls.content_group_id IS DISTINCT FROM cg.id THEN 'stale_content_group'
        WHEN ls.document_status = 'planned' THEN 'ready'
        ELSE ls.document_status
    END AS semantic_readiness,
    (ls.file_id IS NOT NULL
        AND ls.content_sha256 IS NOT DISTINCT FROM f.content_sha256
        AND ls.content_group_id IS NOT DISTINCT FROM cg.id
        AND ls.document_status = 'planned') AS semantic_metadata_current
FROM public.content_groups cg
JOIN public.files f ON f.id = cg.golden_file_id
LEFT JOIN copy_counts cc ON cc.content_group_id = cg.id
LEFT JOIN latest_semantic ls ON ls.file_id = f.id
WHERE f.deleted_at IS NULL;

COMMENT ON VIEW public.v_semantic_golden_records IS
    'Read-only operational projection of active golden records and their newest semantic metadata; stale provenance is explicit.';

COMMIT;
