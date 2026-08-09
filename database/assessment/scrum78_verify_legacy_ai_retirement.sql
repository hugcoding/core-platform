\echo '=== SCRUM-78 retired legacy relations ==='
SELECT relation_name, to_regclass('public.' || relation_name) AS remaining_relation
FROM (VALUES ('embeddings'), ('ai_output')) AS retired(relation_name)
ORDER BY relation_name;

\echo '=== cleanup procedure legacy references ==='
SELECT p.proname,
       p.prosrc ILIKE '% embeddings %' OR p.prosrc ILIKE '% ai_output %'
           AS has_legacy_reference
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public'
  AND p.proname = 'cleanup_all_execute';

\echo '=== current semantic and classification relations remain ==='
SELECT relation_name, to_regclass('public.' || relation_name) AS current_relation
FROM (VALUES
    ('semantic_runs'),
    ('semantic_documents'),
    ('semantic_chunks'),
    ('semantic_embedding_runs'),
    ('semantic_embeddings_acc'),
    ('classification_runs'),
    ('classification_proposals'),
    ('classification_reviews')
) AS current_contract(relation_name)
ORDER BY relation_name;
