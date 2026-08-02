from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from core.semantic.acc_storage import RUN_NAMESPACE, _sql
from core.semantic.chunking import CHUNKER_VERSION
from core.semantic.embedding_benchmark import MODEL_ID, MODEL_REVISION, TOKEN_CHUNKER_VERSION
from core.semantic.extraction import EXTRACTOR_VERSION


EMBEDDING_RUN_NAMESPACE = uuid.UUID("5d436bf4-45ce-4b2e-b90a-810536717a3c")


def semantic_run_id(manifest_bytes: bytes) -> str:
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    identity = f"{digest}:{EXTRACTOR_VERSION}:{CHUNKER_VERSION}"
    return str(uuid.uuid5(RUN_NAMESPACE, identity))


def build_storage_plan(
    manifest_bytes: bytes,
    chunks: list[dict[str, Any]],
    *,
    batch_size: int = 4,
    errors: int = 0,
) -> dict[str, Any]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    manifest = json.loads(manifest_bytes)
    if manifest.get("processing") != "local_only":
        raise ValueError("embedding persistence requires local_only processing")
    if manifest.get("external_ai_enabled") is not False:
        raise ValueError("external AI must remain disabled")
    approved = {int(item["file_id"]): item for item in manifest["files"] if item["approval"] == "approved"}
    for chunk in chunks:
        item = approved.get(int(chunk["file_id"]))
        if item is None:
            raise ValueError(f"unknown or unapproved file_id={chunk['file_id']}")
        if chunk["content_sha256"] != item["content_sha256"]:
            raise ValueError(f"content hash changed for file_id={chunk['file_id']}")
        if len(chunk["embedding"]) != 384:
            raise ValueError("multilingual-e5-small vectors must have dimension 384")
    run_id = semantic_run_id(manifest_bytes)
    identity = f"{run_id}:{MODEL_ID}:{MODEL_REVISION}:{TOKEN_CHUNKER_VERSION}"
    embedding_run_id = str(uuid.uuid5(EMBEDDING_RUN_NAMESPACE, identity))
    return {
        "schema_version": "semantic-embedding-acc-v1",
        "embedding_run_id": embedding_run_id,
        "semantic_run_id": run_id,
        "environment": "acceptance",
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "dimension": 384,
        "chunker_version": TOKEN_CHUNKER_VERSION,
        "batch_size": batch_size,
        "status": "completed_with_errors" if errors else "completed",
        "document_count": len({int(chunk["file_id"]) for chunk in chunks}),
        "chunk_count": len(chunks),
        "error_count": errors,
        "network_enabled": False,
        "raw_text_stored": False,
        "chunks": chunks,
    }


def _vector(values: list[float]) -> str:
    return "'[" + ",".join(format(float(value), ".9g") for value in values) + "]'::vector"


def render_apply_sql(plan: dict[str, Any]) -> str:
    statements = ["BEGIN;", f"""INSERT INTO public.semantic_embedding_runs
        (id, semantic_run_id, environment, model_id, model_revision, dimension,
         chunker_version, batch_size, status, document_count, chunk_count, error_count,
         network_enabled, raw_text_stored)
        VALUES ({_sql(plan['embedding_run_id'])}::uuid, {_sql(plan['semantic_run_id'])}::uuid,
                'acceptance', {_sql(plan['model_id'])}, {_sql(plan['model_revision'])}, 384,
                {_sql(plan['chunker_version'])}, {plan['batch_size']}, {_sql(plan['status'])},
                {plan['document_count']}, {plan['chunk_count']}, {plan['error_count']}, FALSE, FALSE)
        ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status,
          document_count=EXCLUDED.document_count, chunk_count=EXCLUDED.chunk_count,
          error_count=EXCLUDED.error_count, updated_at=now();"""]
    for chunk in plan["chunks"]:
        statements.append(f"""INSERT INTO public.semantic_embeddings_acc
            (embedding_run_id, semantic_run_id, file_id, chunk_id, ordinal,
             content_sha256, token_count, embedding)
            VALUES ({_sql(plan['embedding_run_id'])}::uuid, {_sql(plan['semantic_run_id'])}::uuid,
                    {int(chunk['file_id'])}, {_sql(chunk['chunk_id'])}, {int(chunk['ordinal'])},
                    {_sql(chunk['content_sha256'])}, {int(chunk['token_count'])},
                    {_vector(chunk['embedding'])})
            ON CONFLICT (embedding_run_id, chunk_id) DO UPDATE SET
              token_count=EXCLUDED.token_count, embedding=EXCLUDED.embedding;""")
    statements.append(f"""DO $$ BEGIN
        IF (SELECT count(*) FROM public.semantic_embeddings_acc
            WHERE embedding_run_id={_sql(plan['embedding_run_id'])}::uuid) <> {plan['chunk_count']} THEN
            RAISE EXCEPTION 'semantic embedding count validation failed';
        END IF;
    END $$;""")
    statements.append("COMMIT;")
    return "\n".join(statements) + "\n"
