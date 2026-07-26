\set ON_ERROR_STOP on

BEGIN TRANSACTION READ ONLY;

-- SCRUM-61 read-only baseline. These rules are deliberately conservative:
-- UNKNOWN never becomes eligible for cleanup, migration, or semantic processing.
WITH active_files AS (
    SELECT *
    FROM files
    WHERE deleted_at IS NULL
),
root_inventory AS (
    SELECT
        COALESCE((regexp_match(path, '^/volume1/([^/]+)'))[1], '[volume1-root]') AS root_name,
        COUNT(*) AS file_count,
        COALESCE(SUM(size_bytes), 0)::bigint AS total_bytes
    FROM active_files
    GROUP BY 1
)
SELECT
    root_name,
    file_count,
    pg_size_pretty(total_bytes) AS total_size
FROM root_inventory
ORDER BY total_bytes DESC, root_name;

WITH classified AS (
    SELECT
        id AS file_id,
        size_bytes,
        CASE
            WHEN path ~* '(^|/)(@eaDir|__pycache__|node_modules|\.cache|cache|temp|tmp)(/|$)'
                 OR LOWER(COALESCE(extension, '')) IN ('tmp', 'temp', 'crdownload', 'part', 'pyc')
                THEN 'cache_or_temporary'
            WHEN LOWER(COALESCE(extension, '')) IN
                 ('key', 'pem', 'p12', 'pfx', 'ovpn', 'kdbx')
                THEN 'secret'
            WHEN path ~* '^/volume1/(docker|PlexMediaServer|web)(/|$)'
                THEN 'application_data'
            WHEN path ~* '(^|/)(backup|backups|archive|archief|CloudStation)(/|$)'
                THEN 'backup_or_archive'
            WHEN path ~* '(^|/)(projects?|development|repositories|repos)(/|$)'
                 OR path ~* '(^|/)\.git(/|$)'
                THEN 'project'
            WHEN LOWER(COALESCE(extension, '')) IN
                 ('jpg', 'jpeg', 'png', 'gif', 'bmp', 'tif', 'tiff', 'heic',
                  'mp3', 'wav', 'flac', 'm4a', 'mp4', 'mkv', 'avi', 'mov', 'mts')
                THEN 'personal_media_candidate'
            WHEN LOWER(COALESCE(extension, '')) IN
                 ('txt', 'md', 'pdf', 'doc', 'docx', 'rtf', 'odt',
                  'xls', 'xlsx', 'ods', 'csv', 'ppt', 'pptx', 'odp',
                  'html', 'htm', 'xml')
                THEN 'personal_document_candidate'
            ELSE 'unknown'
        END AS category
    FROM files
    WHERE deleted_at IS NULL
)
SELECT
    category,
    COUNT(*) AS file_count,
    pg_size_pretty(COALESCE(SUM(size_bytes), 0)::bigint) AS total_size,
    CASE
        WHEN category IN ('personal_document_candidate', 'personal_media_candidate', 'project')
            THEN 'review_required'
        ELSE 'not_eligible'
    END AS action_scope
FROM classified
GROUP BY category
ORDER BY COUNT(*) DESC, category;

-- Exact duplicate groups and theoretical maximum removable bytes.
-- This is evidence only: it does not authorize deletion.
WITH duplicate_groups AS (
    SELECT
        hash_content,
        size_bytes,
        COUNT(*) AS copies
    FROM files
    WHERE deleted_at IS NULL
      AND hash_content IS NOT NULL
      AND hash_content <> ''
      AND size_bytes IS NOT NULL
    GROUP BY hash_content, size_bytes
    HAVING COUNT(*) > 1
)
SELECT
    COUNT(*) AS duplicate_groups,
    SUM(copies) AS files_in_duplicate_groups,
    SUM(copies - 1) AS theoretical_duplicate_files,
    pg_size_pretty(COALESCE(SUM((copies - 1) * size_bytes), 0)::bigint)
        AS theoretical_maximum_savings
FROM duplicate_groups;

-- Roots participating in exact duplicate groups.
WITH duplicate_files AS (
    SELECT f.*
    FROM files f
    JOIN (
        SELECT hash_content, size_bytes
        FROM files
        WHERE deleted_at IS NULL
          AND hash_content IS NOT NULL
          AND hash_content <> ''
          AND size_bytes IS NOT NULL
        GROUP BY hash_content, size_bytes
        HAVING COUNT(*) > 1
    ) d USING (hash_content, size_bytes)
    WHERE f.deleted_at IS NULL
)
SELECT
    COALESCE((regexp_match(path, '^/volume1/([^/]+)'))[1], '[volume1-root]') AS root_name,
    COUNT(*) AS files_in_duplicate_groups,
    pg_size_pretty(COALESCE(SUM(size_bytes), 0)::bigint) AS duplicate_group_bytes
FROM duplicate_files
GROUP BY 1
ORDER BY COUNT(*) DESC, root_name;

-- Similar folder basenames under different parent paths. These are review
-- candidates only and are not evidence that directory contents are equivalent.
WITH folder_names AS (
    SELECT
        path,
        LOWER(regexp_replace(
            regexp_replace(path, '^.*/', ''),
            '[^[:alnum:]]',
            '',
            'g'
        )) AS normalized_name
    FROM folders
    WHERE path IS NOT NULL
),
similar_names AS (
    SELECT
        normalized_name,
        COUNT(DISTINCT path) AS distinct_paths
    FROM folder_names
    WHERE normalized_name <> ''
    GROUP BY normalized_name
    HAVING COUNT(DISTINCT path) > 1
)
SELECT
    COUNT(*) AS repeated_normalized_folder_names,
    SUM(distinct_paths) AS participating_folder_paths,
    MAX(distinct_paths) AS largest_name_group
FROM similar_names;

SELECT
    COUNT(*) FILTER (
        WHERE path = '/volume1/data' OR path LIKE '/volume1/data/%'
    ) AS active_files_already_in_target,
    pg_size_pretty(COALESCE(SUM(size_bytes) FILTER (
        WHERE path = '/volume1/data' OR path LIKE '/volume1/data/%'
    ), 0)::bigint) AS target_size,
    COUNT(*) FILTER (
        WHERE path <> '/volume1/data' AND path NOT LIKE '/volume1/data/%'
    ) AS active_files_outside_target
FROM files
WHERE deleted_at IS NULL;

ROLLBACK;
