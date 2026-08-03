from __future__ import annotations

import re
from typing import Iterable

from core.semantic.embedding_benchmark import MODEL_ID, MODEL_REVISION, TOKEN_CHUNKER_VERSION


def validate_search(limit: int, threshold: float) -> None:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")


def vector_literal(values: Iterable[float]) -> str:
    vector = [float(value) for value in values]
    if len(vector) != 384:
        raise ValueError("query vector must have dimension 384")
    return "[" + ",".join(format(value, ".9g") for value in vector) + "]"


def _quoted(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


STOP_WORDS = {"aan", "and", "de", "een", "en", "for", "het", "in", "met", "of", "the", "to", "van", "voor"}


def query_terms(query: str) -> list[str]:
    terms = re.findall(r"[\w]+", query.casefold(), flags=re.UNICODE)
    return list(dict.fromkeys(term for term in terms if len(term) >= 3 and term not in STOP_WORDS))


def _result_select(candidate_sql: str, *, limit: int, threshold: float) -> str:
    validate_search(limit, threshold)
    return f"""WITH candidates AS (
{candidate_sql}
), ranked AS (
    SELECT DISTINCT ON (file_id)
        file_id, semantic_run_id, chunk_id, ordinal, embedding_similarity,
        lexical_similarity, ranking_score
    FROM candidates
    WHERE ranking_score >= {threshold}
    ORDER BY file_id, ranking_score DESC, chunk_id
)
SELECT json_build_object(
    'file_id', r.file_id,
    'content_group_id', v.content_group_id,
    'path', v.golden_path,
    'filename', v.golden_filename,
    'extension', v.extension,
    'similarity', round(r.embedding_similarity::numeric, 6),
    'lexical_similarity', round(r.lexical_similarity::numeric, 6),
    'ranking_score', round(r.ranking_score::numeric, 6),
    'matched_chunk_id', r.chunk_id,
    'matched_chunk_ordinal', r.ordinal,
    'exact_copy_count', v.exact_copy_count,
    'golden_confidence', v.golden_confidence,
    'semantic_run_id', v.semantic_run_id
)::text
FROM ranked r
JOIN public.v_semantic_golden_records v
  ON v.golden_file_id = r.file_id
 AND v.semantic_run_id = r.semantic_run_id
 AND v.semantic_metadata_current
ORDER BY r.ranking_score DESC, r.file_id
LIMIT {limit};
"""


def render_query_similarity_sql(vector: Iterable[float], *, limit: int = 10, threshold: float = 0.0) -> str:
    literal = _quoted(vector_literal(vector))
    candidates = f"""    SELECT e.file_id, e.semantic_run_id, e.chunk_id, e.ordinal,
           1 - (e.embedding <=> {literal}::vector) AS embedding_similarity,
           0::double precision AS lexical_similarity,
           1 - (e.embedding <=> {literal}::vector) AS ranking_score
    FROM public.semantic_embeddings_acc e
    JOIN public.semantic_embedding_runs er ON er.id = e.embedding_run_id
    WHERE er.environment = 'acceptance'
      AND er.model_id = {_quoted(MODEL_ID)}
      AND er.model_revision = {_quoted(MODEL_REVISION)}
      AND er.chunker_version = {_quoted(TOKEN_CHUNKER_VERSION)}"""
    return _result_select(candidates, limit=limit, threshold=threshold)


def render_hybrid_query_similarity_sql(
    vector: Iterable[float], query: str, *, limit: int = 10, threshold: float = 0.0,
    embedding_weight: float = 0.85,
) -> str:
    if not 0.0 <= embedding_weight <= 1.0:
        raise ValueError("embedding_weight must be between 0 and 1")
    terms = query_terms(query)
    if not terms:
        return render_query_similarity_sql(vector, limit=limit, threshold=threshold)
    literal = _quoted(vector_literal(vector))
    matches = " + ".join(
        f"CASE WHEN lower(v.golden_filename || ' ' || v.golden_path) LIKE {_quoted('%' + term + '%')} THEN 1.0 ELSE 0.0 END"
        for term in terms
    )
    lexical = f"(({matches}) / {len(terms)}.0)"
    lexical_weight = 1.0 - embedding_weight
    candidates = f"""    SELECT e.file_id, e.semantic_run_id, e.chunk_id, e.ordinal,
           1 - (e.embedding <=> {literal}::vector) AS embedding_similarity,
           {lexical} AS lexical_similarity,
           ({embedding_weight} * (1 - (e.embedding <=> {literal}::vector)) +
            {lexical_weight} * {lexical}) AS ranking_score
    FROM public.semantic_embeddings_acc e
    JOIN public.semantic_embedding_runs er ON er.id = e.embedding_run_id
    JOIN public.v_semantic_golden_records v
      ON v.golden_file_id = e.file_id
     AND v.semantic_run_id = e.semantic_run_id
     AND v.semantic_metadata_current
    WHERE er.environment = 'acceptance'
      AND er.model_id = {_quoted(MODEL_ID)}
      AND er.model_revision = {_quoted(MODEL_REVISION)}
      AND er.chunker_version = {_quoted(TOKEN_CHUNKER_VERSION)}"""
    return _result_select(candidates, limit=limit, threshold=threshold)


def render_document_similarity_sql(file_id: int, *, limit: int = 10, threshold: float = 0.0) -> str:
    if file_id < 1:
        raise ValueError("file_id must be positive")
    candidates = f"""    SELECT target.file_id, target.semantic_run_id, target.chunk_id, target.ordinal,
           max(1 - (source.embedding <=> target.embedding)) AS embedding_similarity,
           0::double precision AS lexical_similarity,
           max(1 - (source.embedding <=> target.embedding)) AS ranking_score
    FROM public.semantic_embeddings_acc source
    JOIN public.semantic_embedding_runs source_run ON source_run.id = source.embedding_run_id
    JOIN public.v_semantic_golden_records source_v
      ON source_v.golden_file_id = source.file_id
     AND source_v.semantic_run_id = source.semantic_run_id
     AND source_v.semantic_metadata_current
    JOIN public.semantic_embeddings_acc target ON target.file_id <> source.file_id
    JOIN public.semantic_embedding_runs target_run ON target_run.id = target.embedding_run_id
    WHERE source.file_id = {file_id}
      AND source_run.environment = 'acceptance'
      AND target_run.environment = 'acceptance'
      AND source_run.model_id = target_run.model_id
      AND source_run.model_revision = target_run.model_revision
      AND source_run.chunker_version = target_run.chunker_version
      AND source_run.model_id = {_quoted(MODEL_ID)}
      AND source_run.model_revision = {_quoted(MODEL_REVISION)}
      AND source_run.chunker_version = {_quoted(TOKEN_CHUNKER_VERSION)}
    GROUP BY target.file_id, target.semantic_run_id, target.chunk_id, target.ordinal"""
    return _result_select(candidates, limit=limit, threshold=threshold)
