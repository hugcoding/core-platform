BEGIN;
ALTER TABLE public.files ADD COLUMN IF NOT EXISTS filesystem_device bigint NULL;
CREATE INDEX IF NOT EXISTS files_device_inode_active_idx
    ON public.files (filesystem_device, inode)
    WHERE deleted_at IS NULL AND filesystem_device IS NOT NULL AND inode IS NOT NULL;
COMMENT ON COLUMN public.files.filesystem_device IS
    'stat.st_dev; inode identity is valid only within this filesystem context.';
COMMIT;
