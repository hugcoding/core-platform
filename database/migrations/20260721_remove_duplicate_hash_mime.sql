BEGIN;

-- Preserve the legacy v_test_documents output contract while moving its
-- dependency to the canonical path hash.
CREATE OR REPLACE VIEW public.v_test_documents AS
SELECT
    f.id,
    f.folder_id,
    f.filename,
    f.extension,
    f.size_bytes,
    f.created_at,
    f.updated_at,
    f.modified_at_fs,
    f.inode,
    f.hash_path AS xxhash,
    fo.path
FROM public.files f
JOIN public.folders fo ON fo.id = f.folder_id
WHERE fo.path LIKE '/volume1/backup/NITRO/D/data/hugo/Documents%';

DROP INDEX IF EXISTS public.idx_files_xxhash;
ALTER TABLE public.files DROP COLUMN IF EXISTS xxhash;

DROP INDEX IF EXISTS public.idx_metadata_mime_type;
ALTER TABLE public.metadata DROP COLUMN IF EXISTS mime_type;

COMMIT;
