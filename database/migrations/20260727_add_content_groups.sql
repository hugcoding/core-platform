BEGIN;

CREATE TABLE IF NOT EXISTS public.content_groups (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    hash_content text NOT NULL,
    size_bytes bigint NOT NULL,
    golden_file_id integer NOT NULL REFERENCES public.files(id) ON DELETE RESTRICT,
    golden_score integer NOT NULL,
    confidence text NOT NULL,
    selection_status text NOT NULL,
    algorithm_version text NOT NULL,
    selected_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT content_groups_hash_size_unique UNIQUE NULLS NOT DISTINCT
        (hash_content, size_bytes),
    CONSTRAINT content_groups_confidence_check
        CHECK (confidence IN ('high', 'medium', 'low')),
    CONSTRAINT content_groups_selection_status_check
        CHECK (selection_status IN
            ('single_source', 'golden_selected', 'golden_selected_tiebreak'))
);

CREATE TABLE IF NOT EXISTS public.content_group_members (
    content_group_id uuid NOT NULL
        REFERENCES public.content_groups(id) ON DELETE CASCADE,
    file_id integer NOT NULL REFERENCES public.files(id) ON DELETE RESTRICT,
    source_path_snapshot text NOT NULL,
    selection_score integer NOT NULL,
    selection_rank integer NOT NULL CHECK (selection_rank > 0),
    selection_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
    assessed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (content_group_id, file_id),
    CONSTRAINT content_group_members_rank_unique
        UNIQUE (content_group_id, selection_rank)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'content_groups_golden_member_fk'
          AND conrelid = 'public.content_groups'::regclass
    ) THEN
        ALTER TABLE public.content_groups
            ADD CONSTRAINT content_groups_golden_member_fk
            FOREIGN KEY (id, golden_file_id)
            REFERENCES public.content_group_members(content_group_id, file_id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS content_groups_golden_file_idx
    ON public.content_groups (golden_file_id);
CREATE INDEX IF NOT EXISTS content_group_members_file_idx
    ON public.content_group_members (file_id);

CREATE OR REPLACE VIEW public.v_content_group_members AS
SELECT
    m.content_group_id,
    g.hash_content,
    g.size_bytes,
    m.file_id,
    m.source_path_snapshot,
    m.selection_score,
    m.selection_rank,
    (m.file_id = g.golden_file_id) AS is_golden,
    m.selection_reasons,
    g.confidence,
    g.selection_status,
    g.algorithm_version,
    g.selected_at,
    m.assessed_at
FROM public.content_group_members m
JOIN public.content_groups g ON g.id = m.content_group_id;

COMMENT ON TABLE public.content_groups IS
    'One durable golden-record decision per exact content-hash and size group.';
COMMENT ON TABLE public.content_group_members IS
    'Auditable snapshot of every physical file record considered for a content group.';
COMMENT ON VIEW public.v_content_group_members IS
    'Content-group members with is_golden derived from the single authoritative golden_file_id.';

COMMIT;
