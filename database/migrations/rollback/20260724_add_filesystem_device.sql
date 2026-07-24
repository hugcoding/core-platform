BEGIN;
DROP INDEX IF EXISTS public.files_device_inode_active_idx;
ALTER TABLE public.files DROP COLUMN IF EXISTS filesystem_device;
COMMIT;
