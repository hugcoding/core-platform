-- v_file_integrity
-- CORE Integrity Engine v0.1
-- Diagnose-only view. Verwijdert niets.

DROP VIEW IF EXISTS v_file_integrity;

CREATE VIEW v_file_integrity AS
SELECT
    f.*,
    CASE
        WHEN f.path IS NULL OR f.path = '' THEN 'LEGACY_MISSING_PATH'
        WHEN f.folder_id IS NULL THEN 'INVALID_MISSING_FOLDER'
        WHEN f.hash_path IS NULL OR f.hash_path = '' THEN 'INCOMPLETE_MISSING_HASH_PATH'
        WHEN f.hash_content IS NULL OR f.hash_content = '' THEN 'INCOMPLETE_MISSING_HASH_CONTENT'
        WHEN f.mime_type IS NULL OR f.mime_type = '' THEN 'INCOMPLETE_MISSING_MIME'
        WHEN f.deleted_at IS NOT NULL THEN 'DELETED'
        ELSE 'VALID'
    END AS integrity_status
FROM files f;
