-- SCRUM-104: independent, append-only archive and deletion nominations.
BEGIN;

WITH seed(configuration) AS (
    VALUES ('{
      "archive_review_days": 0,
      "deletion_review_days": 90,
      "direct_file_mutations": false,
      "automatic_archive_on_deletion_nomination": false,
      "permanent_delete_enabled": false
    }'::jsonb)
INSERT INTO public.policy_versions (
    id, policy_code, environment, contract_version, policy_version, status,
    configuration, configuration_checksum, effective_from, created_by,
    change_reason, approved_at, approved_by
)
SELECT
    'e6754b4a-223c-54ae-911d-f460bd945360'::uuid,
    'document_retention', 'acceptance', 'document-retention-policy-v1',
    'retention-nomination-v1', 'active', configuration,
    'ed7a4fb0a44bda9cd4e8da07644ef356c83cf74b5340b22533bee8cc51a0b6dd',
    '2026-08-15 00:00:00+02'::timestamptz, 'core-migration',
    'Safe manual nomination policy; review only, no file mutation or permanent deletion.',
    '2026-08-15 00:00:00+02'::timestamptz, 'hugo'
FROM seed
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS public.document_lifecycle_nomination_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key uuid NOT NULL UNIQUE,
    file_id bigint NOT NULL REFERENCES public.files(id) ON DELETE RESTRICT,
    content_group_id uuid NOT NULL REFERENCES public.content_groups(id) ON DELETE RESTRICT,
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    nomination_type text NOT NULL CHECK (nomination_type IN ('archive', 'deletion')),
    action text NOT NULL CHECK (action IN ('nominated', 'withdrawn')),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 1000),
    policy_id uuid NOT NULL REFERENCES public.policy_versions(id) ON DELETE RESTRICT,
    policy_code text NOT NULL,
    policy_version text NOT NULL,
    policy_snapshot jsonb NOT NULL CHECK (jsonb_typeof(policy_snapshot) = 'object'),
    review_at timestamptz NOT NULL,
    workset_status_snapshot text NOT NULL,
    category_snapshot text,
    family_snapshot text,
    privacy_snapshot text CHECK (privacy_snapshot IS NULL OR privacy_snapshot IN ('low', 'medium', 'high')),
    channel text NOT NULL DEFAULT 'workset_portal' CHECK (channel = 'workset_portal'),
    nominated_by text NOT NULL,
    supersedes_event_id uuid REFERENCES public.document_lifecycle_nomination_events(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (action = 'nominated' OR supersedes_event_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS document_lifecycle_nomination_file_idx
    ON public.document_lifecycle_nomination_events(file_id, nomination_type, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS document_lifecycle_nomination_review_idx
    ON public.document_lifecycle_nomination_events(review_at)
    WHERE action = 'nominated';

CREATE OR REPLACE FUNCTION public.reject_document_lifecycle_nomination_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'document lifecycle nominations are append-only; insert a superseding event';
END;
$$;

DROP TRIGGER IF EXISTS document_lifecycle_nomination_events_immutable
    ON public.document_lifecycle_nomination_events;
CREATE TRIGGER document_lifecycle_nomination_events_immutable
BEFORE UPDATE OR DELETE ON public.document_lifecycle_nomination_events
FOR EACH ROW EXECUTE FUNCTION public.reject_document_lifecycle_nomination_mutation();

CREATE OR REPLACE VIEW public.v_latest_document_lifecycle_nomination AS
SELECT DISTINCT ON (file_id, nomination_type)
    id, file_id, content_group_id, content_sha256, nomination_type, action,
    reason, policy_id, policy_code, policy_version, policy_snapshot, review_at,
    workset_status_snapshot, category_snapshot, family_snapshot, privacy_snapshot,
    channel, nominated_by, supersedes_event_id, created_at
FROM public.document_lifecycle_nomination_events
ORDER BY file_id, nomination_type, created_at DESC, id DESC;

CREATE OR REPLACE VIEW public.v_active_document_lifecycle_nominations AS
SELECT * FROM public.v_latest_document_lifecycle_nomination WHERE action = 'nominated';

COMMENT ON TABLE public.document_lifecycle_nomination_events IS
    'Append-only human nominations. They never change workset state, archive state, storage location or files.';
COMMENT ON VIEW public.v_active_document_lifecycle_nominations IS
    'Current independent archive/deletion nominations; withdrawal remains available in event history.';

COMMIT;
