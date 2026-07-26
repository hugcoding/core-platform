\set ON_ERROR_STOP on

BEGIN TRANSACTION READ ONLY;

-- 1. Case-sensitive target-root check after the DSM rename.
SELECT
    COALESCE((regexp_match(path, '^/volume1/([^/]+)'))[1], '[volume1-root]') AS actual_root,
    COUNT(*) AS active_files,
    pg_size_pretty(COALESCE(SUM(size_bytes), 0)::bigint) AS total_size
FROM files
WHERE deleted_at IS NULL
  AND LOWER(path) LIKE '/volume1/data/%'
GROUP BY 1
ORDER BY actual_root;

-- 2. First-level content below each user's home directory. A user home is
-- mixed-purpose until every component has been reviewed.
WITH home_parts AS (
    SELECT
        COALESCE((regexp_match(path, '^/volume1/homes/([^/]+)'))[1], '[unknown-user]')
            AS home_user,
        COALESCE((regexp_match(path, '^/volume1/homes/[^/]+/([^/]+)'))[1], '[home-root]')
            AS component,
        size_bytes
    FROM files
    WHERE deleted_at IS NULL
      AND path LIKE '/volume1/homes/%'
)
SELECT
    home_user,
    component,
    COUNT(*) AS active_files,
    pg_size_pretty(COALESCE(SUM(size_bytes), 0)::bigint) AS total_size
FROM home_parts
GROUP BY home_user, component
ORDER BY SUM(size_bytes) DESC, home_user, component;

-- 3. Direct files under /volume1. These require individual ownership review.
SELECT
    id AS file_id,
    pg_size_pretty(COALESCE(size_bytes, 0)::bigint) AS size,
    mime_type,
    path
FROM files
WHERE deleted_at IS NULL
  AND path ~ '^/volume1/[^/]+$'
ORDER BY size_bytes DESC NULLS LAST, path
LIMIT 100;

-- 4. Known non-personal roots. These remain in inventory but are ineligible
-- for cleanup, migration, and semantic processing by default.
SELECT
    COALESCE((regexp_match(path, '^/volume1/([^/]+)'))[1], '[volume1-root]') AS root_name,
    COUNT(*) AS active_files,
    pg_size_pretty(COALESCE(SUM(size_bytes), 0)::bigint) AS total_size
FROM files
WHERE deleted_at IS NULL
  AND path ~ '^/volume1/(system|ollama|docker|PlexMediaServer|web)(/|$)'
GROUP BY 1
ORDER BY SUM(size_bytes) DESC, root_name;

-- 5. Exact duplicate content shared by different roots. Each content hash and
-- size contributes at most once to a root pair, even if a root contains more
-- than one copy.
WITH rooted_files AS (
    SELECT
        hash_content,
        size_bytes,
        COALESCE((regexp_match(path, '^/volume1/([^/]+)'))[1], '[volume1-root]')
            AS root_name
    FROM files
    WHERE deleted_at IS NULL
      AND hash_content IS NOT NULL
      AND hash_content <> ''
      AND size_bytes IS NOT NULL
),
content_per_root AS (
    SELECT DISTINCT hash_content, size_bytes, root_name
    FROM rooted_files
),
root_pairs AS (
    SELECT
        left_root.root_name AS root_a,
        right_root.root_name AS root_b,
        left_root.hash_content,
        left_root.size_bytes
    FROM content_per_root left_root
    JOIN content_per_root right_root
      ON right_root.hash_content = left_root.hash_content
     AND right_root.size_bytes = left_root.size_bytes
     AND right_root.root_name > left_root.root_name
)
SELECT
    root_a,
    root_b,
    COUNT(*) AS shared_exact_contents,
    pg_size_pretty(COALESCE(SUM(size_bytes), 0)::bigint) AS shared_content_size
FROM root_pairs
GROUP BY root_a, root_b
ORDER BY SUM(size_bytes) DESC, root_a, root_b;

-- 6. Exact duplicate copies contained within the same root.
WITH rooted_groups AS (
    SELECT
        COALESCE((regexp_match(path, '^/volume1/([^/]+)'))[1], '[volume1-root]')
            AS root_name,
        hash_content,
        size_bytes,
        COUNT(*) AS copies
    FROM files
    WHERE deleted_at IS NULL
      AND hash_content IS NOT NULL
      AND hash_content <> ''
      AND size_bytes IS NOT NULL
    GROUP BY 1, hash_content, size_bytes
    HAVING COUNT(*) > 1
)
SELECT
    root_name,
    COUNT(*) AS duplicate_groups_inside_root,
    SUM(copies - 1) AS theoretical_extra_copies,
    pg_size_pretty(COALESCE(SUM((copies - 1) * size_bytes), 0)::bigint)
        AS theoretical_maximum_savings
FROM rooted_groups
GROUP BY root_name
ORDER BY SUM((copies - 1) * size_bytes) DESC, root_name;

-- 7. Preliminary source roles. These are recommendations for human review,
-- not persisted classifications.
WITH roots AS (
    SELECT
        COALESCE((regexp_match(path, '^/volume1/([^/]+)'))[1], '[volume1-root]')
            AS root_name,
        COUNT(*) AS active_files,
        COALESCE(SUM(size_bytes), 0)::bigint AS total_bytes
    FROM files
    WHERE deleted_at IS NULL
    GROUP BY 1
)
SELECT
    root_name,
    active_files,
    pg_size_pretty(total_bytes) AS total_size,
    CASE
        WHEN root_name = 'data' THEN 'canonical_target'
        WHEN root_name IN ('system', 'ollama', 'docker', 'PlexMediaServer', 'web')
            THEN 'application_or_system_excluded'
        WHEN root_name = 'backup' THEN 'legacy_or_backup_source'
        WHEN root_name IN ('photo', 'video') THEN 'possible_authoritative_media_source'
        WHEN root_name = 'homes' THEN 'mixed_requires_subroot_review'
        ELSE 'unknown_requires_review'
    END AS proposed_role
FROM roots
ORDER BY total_bytes DESC, root_name;

ROLLBACK;
