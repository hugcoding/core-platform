from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from core.semantic.chunking import CHUNKER_VERSION
from core.semantic.extraction import EXTRACTOR_VERSION


RUN_NAMESPACE = uuid.UUID("d69b37ab-c45e-4d55-8bbc-204370239181")


def build_plan(manifest_bytes: bytes, results: list[dict[str, Any]]) -> dict[str, Any]:
    manifest = json.loads(manifest_bytes)
    if manifest.get("embedding_enabled") is not False or manifest.get("external_ai_enabled") is not False:
        raise ValueError("ACC metadata plan requires embeddings and external AI to remain disabled")
    items = {int(item["file_id"]): item for item in manifest["files"] if item["approval"] == "approved"}
    if len(results) != len(items):
        raise ValueError("planner result count does not match approved manifest documents")
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    identity = f"{manifest_sha256}:{EXTRACTOR_VERSION}:{CHUNKER_VERSION}"
    run_id = str(uuid.uuid5(RUN_NAMESPACE, identity))
    documents = []
    chunks = []
    for result in results:
        file_id = int(result["file_id"])
        item = items.get(file_id)
        if item is None:
            raise ValueError(f"planner returned unknown file_id={file_id}")
        status = result["status"]
        if status == "error" and result.get("error_type") == "PermissionError":
            status = "password_protected"
        if status == "planned" and result.get("content_version") != item["content_sha256"]:
            raise ValueError(f"content hash changed for file_id={file_id}")
        documents.append({
            "file_id": file_id,
            "content_group_id": item.get("content_group_id"),
            "content_sha256": item["content_sha256"],
            "status": status,
            "extension": result.get("extension") or item["path"].rsplit(".", 1)[-1].lower(),
            "size_bytes": item.get("size_bytes"),
            "characters": result.get("characters"),
            "words": result.get("words"),
            "pages": result.get("pages"),
            "estimated_tokens": result.get("estimated_tokens"),
            "chunk_count": result.get("chunks", 0),
            "error_type": result.get("error_type"),
            "error_reason": result.get("reason"),
        })
        for chunk in result.get("chunk_metadata", []):
            chunks.append({**chunk, "file_id": file_id, "content_sha256": item["content_sha256"]})
    error_count = sum(doc["status"] in {"error", "password_protected"} for doc in documents)
    return {
        "schema_version": "semantic-acc-metadata-v1",
        "run_id": run_id,
        "environment": "acceptance",
        "manifest_sha256": manifest_sha256,
        "source": manifest["source"],
        "selection_version": manifest["selection_version"],
        "extractor_version": EXTRACTOR_VERSION,
        "chunker_version": CHUNKER_VERSION,
        "status": "completed_with_errors" if error_count else "completed",
        "embedding_enabled": False,
        "external_ai_enabled": False,
        "documents": documents,
        "chunks": chunks,
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "error_count": error_count,
    }


def _sql(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def render_apply_sql(plan: dict[str, Any]) -> str:
    run = plan
    statements = ["BEGIN;", f"""INSERT INTO public.semantic_runs
        (id, environment, manifest_sha256, source, selection_version, extractor_version,
         chunker_version, status, document_count, chunk_count, error_count,
         embedding_enabled, external_ai_enabled)
        VALUES ({_sql(run['run_id'])}::uuid, {_sql(run['environment'])}, {_sql(run['manifest_sha256'])},
                {_sql(run['source'])}, {_sql(run['selection_version'])}, {_sql(run['extractor_version'])},
                {_sql(run['chunker_version'])}, {_sql(run['status'])}, {run['document_count']},
                {run['chunk_count']}, {run['error_count']}, FALSE, FALSE)
        ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status,
          document_count=EXCLUDED.document_count, chunk_count=EXCLUDED.chunk_count,
          error_count=EXCLUDED.error_count, updated_at=now();"""]
    for doc in run["documents"]:
        statements.append(f"""INSERT INTO public.semantic_documents
            (run_id, file_id, content_group_id, content_sha256, status, extension, size_bytes,
             characters, words, pages, estimated_tokens, chunk_count, error_type, error_reason)
            SELECT {_sql(run['run_id'])}::uuid, f.id, {_sql(doc['content_group_id'])}::uuid,
                   {_sql(doc['content_sha256'])}, {_sql(doc['status'])}, {_sql(doc['extension'])},
                   {_sql(doc['size_bytes'])}, {_sql(doc['characters'])}, {_sql(doc['words'])},
                   {_sql(doc['pages'])}, {_sql(doc['estimated_tokens'])}, {doc['chunk_count']},
                   {_sql(doc['error_type'])}, {_sql(doc['error_reason'])}
            FROM public.files f JOIN public.content_groups cg ON cg.id={_sql(doc['content_group_id'])}::uuid
            WHERE f.id={doc['file_id']} AND f.content_sha256={_sql(doc['content_sha256'])}
              AND cg.golden_file_id=f.id
            ON CONFLICT (run_id, file_id) DO UPDATE SET status=EXCLUDED.status,
              characters=EXCLUDED.characters, words=EXCLUDED.words, pages=EXCLUDED.pages,
              estimated_tokens=EXCLUDED.estimated_tokens, chunk_count=EXCLUDED.chunk_count,
              error_type=EXCLUDED.error_type, error_reason=EXCLUDED.error_reason, updated_at=now();""")
    for chunk in run["chunks"]:
        statements.append(f"""INSERT INTO public.semantic_chunks
            (run_id, file_id, chunk_id, ordinal, content_sha256, words, characters)
            VALUES ({_sql(run['run_id'])}::uuid, {chunk['file_id']}, {_sql(chunk['chunk_id'])},
                    {chunk['ordinal']}, {_sql(chunk['content_sha256'])}, {chunk['words']}, {chunk['characters']})
            ON CONFLICT (run_id, chunk_id) DO UPDATE SET words=EXCLUDED.words, characters=EXCLUDED.characters;""")
    statements.append(f"""DO $$ BEGIN
        IF (SELECT count(*) FROM public.semantic_documents WHERE run_id={_sql(run['run_id'])}::uuid) <> {run['document_count']} THEN
            RAISE EXCEPTION 'semantic document provenance validation failed';
        END IF;
    END $$;""")
    statements.append("COMMIT;")
    return "\n".join(statements) + "\n"
