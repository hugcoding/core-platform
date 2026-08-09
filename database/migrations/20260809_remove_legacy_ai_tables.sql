BEGIN;
SET LOCAL lock_timeout = '10s';

-- Refuse destructive retirement when legacy data unexpectedly exists.
DO $$
DECLARE
    legacy_rows bigint;
BEGIN
    IF to_regclass('public.embeddings') IS NOT NULL THEN
        EXECUTE 'SELECT count(*) FROM public.embeddings' INTO legacy_rows;
        IF legacy_rows <> 0 THEN
            RAISE EXCEPTION 'Cannot retire public.embeddings: % rows remain', legacy_rows;
        END IF;
    END IF;

    IF to_regclass('public.ai_output') IS NOT NULL THEN
        EXECUTE 'SELECT count(*) FROM public.ai_output' INTO legacy_rows;
        IF legacy_rows <> 0 THEN
            RAISE EXCEPTION 'Cannot retire public.ai_output: % rows remain', legacy_rows;
        END IF;
    END IF;
END
$$;

CREATE OR REPLACE PROCEDURE public.cleanup_all_execute()
LANGUAGE plpgsql
AS $$
DECLARE
    dir_folders integer := 0;
    dir_files integer := 0;
    dir_meta integer := 0;
    file_files integer := 0;
    file_meta integer := 0;
    orphan_metadata integer := 0;
    orphan_files integer := 0;
    orphan_folders integer := 0;
BEGIN
    RAISE NOTICE '=== CLEANUP START ===';

    WITH excluded_folders AS (
        SELECT id FROM folders
        WHERE path LIKE '%/@eaDir%'
           OR path LIKE '%/@appstore%'
           OR path LIKE '%/@tmp%'
           OR path LIKE '%/@%'
    ), files_to_delete AS (
        SELECT id AS file_id FROM files
        WHERE folder_id IN (SELECT id FROM excluded_folders)
    )
    SELECT (SELECT count(*) FROM excluded_folders),
           (SELECT count(*) FROM files_to_delete),
           (SELECT count(*) FROM metadata WHERE file_id IN (SELECT file_id FROM files_to_delete))
    INTO dir_folders, dir_files, dir_meta;

    RAISE NOTICE 'DIRS: removing % folders, % files, % metadata',
        dir_folders, dir_files, dir_meta;

    DELETE FROM metadata
    WHERE file_id IN (
        SELECT id FROM files WHERE folder_id IN (
            SELECT id FROM folders
            WHERE path LIKE '%/@eaDir%'
               OR path LIKE '%/@appstore%'
               OR path LIKE '%/@tmp%'
               OR path LIKE '%/@%'
        )
    );

    DELETE FROM files
    WHERE folder_id IN (
        SELECT id FROM folders
        WHERE path LIKE '%/@eaDir%'
           OR path LIKE '%/@appstore%'
           OR path LIKE '%/@tmp%'
           OR path LIKE '%/@%'
    );

    DELETE FROM folders
    WHERE path LIKE '%/@eaDir%'
       OR path LIKE '%/@appstore%'
       OR path LIKE '%/@tmp%'
       OR path LIKE '%/@%';

    WITH excluded_files AS (
        SELECT id AS file_id FROM files
        WHERE filename LIKE '~$%'
           OR filename LIKE '._%'
           OR filename = '.DS_Store'
           OR filename = 'Thumbs.db'
           OR filename LIKE '%.tmp'
           OR filename LIKE '%.swp'
           OR filename LIKE '%.bak'
    )
    SELECT (SELECT count(*) FROM excluded_files),
           (SELECT count(*) FROM metadata WHERE file_id IN (SELECT file_id FROM excluded_files))
    INTO file_files, file_meta;

    RAISE NOTICE 'FILES: removing % files, % metadata', file_files, file_meta;

    DELETE FROM metadata
    WHERE file_id IN (
        SELECT id FROM files
        WHERE filename LIKE '~$%'
           OR filename LIKE '._%'
           OR filename = '.DS_Store'
           OR filename = 'Thumbs.db'
           OR filename LIKE '%.tmp'
           OR filename LIKE '%.swp'
           OR filename LIKE '%.bak'
    );

    DELETE FROM files
    WHERE filename LIKE '~$%'
       OR filename LIKE '._%'
       OR filename = '.DS_Store'
       OR filename = 'Thumbs.db'
       OR filename LIKE '%.tmp'
       OR filename LIKE '%.swp'
       OR filename LIKE '%.bak';

    SELECT count(*) INTO orphan_metadata
    FROM metadata m LEFT JOIN files f ON f.id = m.file_id
    WHERE f.id IS NULL;
    RAISE NOTICE 'ORPHANS: removing % orphaned metadata', orphan_metadata;
    DELETE FROM metadata m
    WHERE NOT EXISTS (SELECT 1 FROM files f WHERE f.id = m.file_id);

    SELECT count(*) INTO orphan_files
    FROM files fl LEFT JOIN folders fo ON fo.id = fl.folder_id
    WHERE fo.id IS NULL;
    RAISE NOTICE 'ORPHANS: removing % orphaned files', orphan_files;
    DELETE FROM files fl
    WHERE NOT EXISTS (SELECT 1 FROM folders fo WHERE fo.id = fl.folder_id);

    SELECT count(*) INTO orphan_folders
    FROM folders f LEFT JOIN folders p ON p.id = f.parent_id
    WHERE f.parent_id IS NOT NULL AND p.id IS NULL;
    RAISE NOTICE 'ORPHANS: removing % orphaned folders', orphan_folders;
    DELETE FROM folders f
    WHERE f.parent_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM folders p WHERE p.id = f.parent_id);

    RAISE NOTICE '=== CLEANUP COMPLETE ===';
END;
$$;

DROP TABLE IF EXISTS public.embeddings;
DROP TABLE IF EXISTS public.ai_output;

COMMIT;
