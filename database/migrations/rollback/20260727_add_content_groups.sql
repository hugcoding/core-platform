BEGIN;

DROP VIEW IF EXISTS public.v_content_group_members;
ALTER TABLE IF EXISTS public.content_groups
    DROP CONSTRAINT IF EXISTS content_groups_golden_member_fk;
DROP TABLE IF EXISTS public.content_group_members;
DROP TABLE IF EXISTS public.content_groups;

COMMIT;
