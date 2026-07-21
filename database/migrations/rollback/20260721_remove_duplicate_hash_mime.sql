BEGIN;

ALTER TABLE public.files ADD COLUMN IF NOT EXISTS xxhash text;
UPDATE public.files SET xxhash = hash_path WHERE xxhash IS NULL;
CREATE INDEX IF NOT EXISTS idx_files_xxhash ON public.files USING btree (xxhash);

ALTER TABLE public.metadata ADD COLUMN IF NOT EXISTS mime_type text;
UPDATE public.metadata m
SET mime_type = f.mime_type
FROM public.files f
WHERE f.id = m.file_id
  AND m.mime_type IS NULL;
CREATE INDEX IF NOT EXISTS idx_metadata_mime_type ON public.metadata USING btree (mime_type);

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
    f.xxhash,
    fo.path
FROM public.files f
JOIN public.folders fo ON fo.id = f.folder_id
WHERE fo.path LIKE '/volume1/backup/NITRO/D/data/hugo/Documents%';

COMMIT;
