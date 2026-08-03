from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

from core.semantic.embedding_benchmark import MODEL_DIRECTORY, MODEL_ID, MODEL_REVISION


def embed_query(
    query: str, model_path: Path, *, model_factory: Callable[[str], Any] | None = None,
) -> list[float]:
    query = " ".join(query.split())
    if not query:
        raise ValueError("query must not be empty")
    if len(query) > 4000:
        raise ValueError("query must not exceed 4000 characters")
    if model_factory is None:
        from sentence_transformers import SentenceTransformer
        model_factory = lambda path: SentenceTransformer(path, local_files_only=True)
    model = model_factory(str(model_path))
    vectors = model.encode(["query: " + query], batch_size=1, normalize_embeddings=True, show_progress_bar=False)
    vector = [float(value) for value in vectors.tolist()[0]]
    if len(vector) != 384:
        raise ValueError("query model must produce dimension 384")
    return vector


def embed_queries(
    queries: list[str], model_path: Path, *, model_factory: Callable[[str], Any] | None = None,
) -> list[list[float]]:
    normalized = [" ".join(query.split()) for query in queries]
    if not normalized or any(not query for query in normalized):
        raise ValueError("queries must not be empty")
    if any(len(query) > 4000 for query in normalized):
        raise ValueError("queries must not exceed 4000 characters")
    if model_factory is None:
        from sentence_transformers import SentenceTransformer
        model_factory = lambda path: SentenceTransformer(path, local_files_only=True)
    model = model_factory(str(model_path))
    vectors = model.encode(
        ["query: " + query for query in normalized], batch_size=4,
        normalize_embeddings=True, show_progress_bar=False,
    ).tolist()
    result = [[float(value) for value in vector] for vector in vectors]
    if any(len(vector) != 384 for vector in result):
        raise ValueError("query model must produce dimension 384")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="semantic-query-embedding")
    parser.add_argument("--model-path", type=Path, default=Path("/models") / MODEL_DIRECTORY)
    parser.add_argument("--json", action="store_true", help="read a JSON array of queries from stdin")
    args = parser.parse_args(argv)
    query = sys.stdin.read()
    if args.json:
        queries = json.loads(query)
        vectors = embed_queries(queries, args.model_path)
        print(json.dumps({
            "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
            "dimension": 384, "vectors": vectors,
            "network_enabled": False, "queries_stored": False,
        }, separators=(",", ":")))
        return 0
    vector = embed_query(query, args.model_path)
    print(json.dumps({
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "dimension": len(vector),
        "vector": vector,
        "network_enabled": False,
        "query_stored": False,
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
