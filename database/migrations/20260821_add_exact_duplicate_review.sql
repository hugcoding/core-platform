-- SCRUM-110: append-only exact duplicate review and safe executor handoff.
BEGIN;

CREATE TABLE IF NOT EXISTS public.exact_duplicate_review_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key uuid NOT NULL UNIQUE,
    content_group_id uuid NOT NULL REFERENCES public.content_groups(id) ON DELETE RESTRICT,
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    action text NOT NULL CHECK (action IN ('selected_leader', 'withdrawn')),
    selected_file_id bigint NOT NULL REFERENCES public.files(id) ON DELETE RESTRICT,
    golden_file_id_snapshot bigint NOT NULL REFERENCES public.files(id) ON DELETE RESTRICT,
    redundant_file_ids bigint[] NOT NULL,
    review_notes text NOT NULL DEFAULT '' CHECK (length(review_notes) <= 2000),
    policy_id uuid NOT NULL REFERENCES public.policy_versions(id) ON DELETE RESTRICT,
    policy_code text NOT NULL,
    policy_version text NOT NULL,
    policy_snapshot jsonb NOT NULL CHECK (jsonb_typeof(policy_snapshot) = 'object'),
    quarantine_root text NOT NULL DEFAULT '/volume1/data/.core/quarantaine/duplicaten',
    reviewer text NOT NULL,
    supersedes_event_id uuid REFERENCES public.exact_duplicate_review_events(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT exact_duplicate_review_quarantine_check CHECK (
        quarantine_root = '/volume1/data/.core/quarantaine/duplicaten'
    ),
    CONSTRAINT exact_duplicate_review_selection_check CHECK (
        selected_file_id <> ALL(redundant_file_ids)
        AND cardinality(redundant_file_ids) > 0
        AND (action = 'selected_leader' OR supersedes_event_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS exact_duplicate_review_group_created_idx
    ON public.exact_duplicate_review_events(content_group_id, created_at DESC, id DESC);

CREATE OR REPLACE FUNCTION public.reject_exact_duplicate_review_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'exact duplicate reviews are append-only; insert a superseding event';
END;
$$;

DROP TRIGGER IF EXISTS exact_duplicate_review_events_immutable
    ON public.exact_duplicate_review_events;
CREATE TRIGGER exact_duplicate_review_events_immutable
BEFORE UPDATE OR DELETE ON public.exact_duplicate_review_events
FOR EACH ROW EXECUTE FUNCTION public.reject_exact_duplicate_review_mutation();

CREATE OR REPLACE VIEW public.v_latest_exact_duplicate_review AS
SELECT DISTINCT ON (content_group_id)
    id, idempotency_key, content_group_id, content_sha256, size_bytes, action,
    selected_file_id, golden_file_id_snapshot, redundant_file_ids, review_notes,
    policy_id, policy_code, policy_version, policy_snapshot, quarantine_root,
    reviewer, supersedes_event_id, created_at
FROM public.exact_duplicate_review_events
ORDER BY content_group_id, created_at DESC, id DESC;

CREATE OR REPLACE VIEW public.v_exact_duplicate_review_groups AS
SELECT
    g.id AS content_group_id,
    g.content_sha256,
    g.size_bytes,
    g.golden_file_id,
    count(*) AS available_copies,
    (g.size_bytes * (count(*) - 1))::bigint AS potential_savings_bytes,
    coalesce(bool_and(f.content_sha256 = g.content_sha256 AND f.size_bytes = g.size_bytes), false) AS evidence_current,
    array_agg(f.id ORDER BY (f.id = g.golden_file_id) DESC, lower(f.path), f.id) AS file_ids,
    latest.id AS latest_review_id,
    latest.action AS latest_review_action,
    latest.selected_file_id,
    latest.created_at AS reviewed_at
FROM public.content_groups g
JOIN public.content_group_members gm ON gm.content_group_id = g.id
JOIN public.files f ON f.id = gm.file_id AND f.deleted_at IS NULL
LEFT JOIN public.v_latest_exact_duplicate_review latest ON latest.content_group_id = g.id
WHERE g.content_sha256 IS NOT NULL AND g.size_bytes > 0
GROUP BY g.id, g.content_sha256, g.size_bytes, g.golden_file_id,
         latest.id, latest.action, latest.selected_file_id, latest.created_at
HAVING count(*) > 1;

CREATE OR REPLACE VIEW public.v_exact_duplicate_review_handoff AS
SELECT
    review.id AS review_event_id,
    review.content_group_id,
    review.content_sha256,
    review.selected_file_id,
    redundant.file_id AS redundant_file_id,
    selected.path AS selected_path,
    duplicate.path AS redundant_path,
    review.quarantine_root || '/' || review.content_group_id::text || '/'
        || duplicate.id::text || '-' || duplicate.filename AS quarantine_path,
    'inactive'::text AS intended_lifecycle,
    'redundant_duplicate'::text AS nomination_reason,
    review.policy_id,
    review.policy_code,
    review.policy_version,
    (groups.golden_file_id = review.selected_file_id) AS selected_is_current_golden,
    (
        review.action = 'selected_leader'
        AND groups.evidence_current
        AND groups.golden_file_id = review.selected_file_id
        AND selected.deleted_at IS NULL
        AND duplicate.deleted_at IS NULL
        AND selected.content_sha256 = review.content_sha256
        AND duplicate.content_sha256 = review.content_sha256
        AND selected.size_bytes = review.size_bytes
        AND duplicate.size_bytes = review.size_bytes
    ) AS eligible_for_executor,
    CASE
        WHEN review.action <> 'selected_leader' THEN 'review_withdrawn'
        WHEN NOT groups.evidence_current THEN 'duplicate_evidence_changed'
        WHEN groups.golden_file_id <> review.selected_file_id THEN 'golden_switch_required'
        WHEN selected.deleted_at IS NOT NULL OR duplicate.deleted_at IS NOT NULL THEN 'copy_unavailable'
        WHEN selected.content_sha256 <> review.content_sha256
          OR duplicate.content_sha256 <> review.content_sha256
          OR selected.size_bytes <> review.size_bytes
          OR duplicate.size_bytes <> review.size_bytes THEN 'duplicate_changed_after_nomination'
        ELSE 'ready_for_controlled_handoff'
    END AS handoff_reason
FROM public.v_latest_exact_duplicate_review review
JOIN public.v_exact_duplicate_review_groups groups USING (content_group_id)
JOIN public.files selected ON selected.id = review.selected_file_id
CROSS JOIN LATERAL unnest(review.redundant_file_ids) redundant(file_id)
JOIN public.files duplicate ON duplicate.id = redundant.file_id;

COMMENT ON TABLE public.exact_duplicate_review_events IS
    'Append-only human choice of one leading physical copy; never moves, deletes or rewrites files.';
COMMENT ON VIEW public.v_exact_duplicate_review_handoff IS
    'Revalidated, read-only handoff from duplicate review to SCRUM-97 and SCRUM-104.';

COMMIT;
