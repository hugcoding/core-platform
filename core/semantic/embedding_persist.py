from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from core.semantic.embedding_benchmark import MODEL_DIRECTORY, OVERLAP_TOKENS, TARGET_TOKENS
from core.semantic.embedding_storage import build_storage_plan
from core.semantic.extraction import extract_document


def collect_embedding_chunks(
    manifest: dict[str, Any], *, tokenizer: Any, max_chunks: int,
    max_chunks_per_document: int = 3, max_documents: int = 100,
    extractor: Callable[[Path], tuple[str, int]] = extract_document,
) -> tuple[list[dict[str, Any]], int]:
    if max_chunks < 1:
        raise ValueError("max_chunks must be positive")
    if max_chunks_per_document < 1:
        raise ValueError("max_chunks_per_document must be positive")
    if max_documents < 1:
        raise ValueError("max_documents must be positive")
    chunks: list[dict[str, Any]] = []
    errors = 0
    step = TARGET_TOKENS - OVERLAP_TOKENS
    approved = [item for item in manifest["files"] if item.get("approval") == "approved"]
    if len(approved) > max_documents:
        raise ValueError(f"approved manifest documents exceed max_documents={max_documents}")
    for item in approved:
        path = Path(item["path"])
        try:
            text, _ = extractor(path)
            token_ids = tokenizer.encode(text, add_special_tokens=False, verbose=False)
        except Exception:
            errors += 1
            continue
        document_chunks = []
        ordinal = 0
        for start in range(0, len(token_ids), step):
            if start and len(token_ids) - start <= OVERLAP_TOKENS:
                break
            ids = token_ids[start : start + TARGET_TOKENS]
            if not ids:
                continue
            passage = "passage: " + tokenizer.decode(ids, skip_special_tokens=True)
            text_hash = hashlib.sha256(passage.encode("utf-8")).hexdigest()
            identity = f"{item['file_id']}:{item['content_sha256']}:{ordinal}:{text_hash}"
            document_chunks.append({
                "file_id": int(item["file_id"]),
                "chunk_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                "ordinal": ordinal,
                "content_sha256": item["content_sha256"],
                "token_count": len(ids),
                "passage": passage,
            })
            ordinal += 1
        if len(document_chunks) <= max_chunks_per_document:
            selected_chunks = document_chunks
        elif max_chunks_per_document == 1:
            selected_chunks = [document_chunks[len(document_chunks) // 2]]
        else:
            indexes = [
                round(index * (len(document_chunks) - 1) / (max_chunks_per_document - 1))
                for index in range(max_chunks_per_document)
            ]
            selected_chunks = [document_chunks[index] for index in dict.fromkeys(indexes)]
        if len(chunks) + len(selected_chunks) > max_chunks:
            raise ValueError(
                f"representative chunks exceed max_chunks={max_chunks}; increase the explicit hard limit"
            )
        chunks.extend(selected_chunks)
    return chunks, errors


def build_embedding_plan(
    manifest_bytes: bytes, model_path: Path, *, max_chunks: int = 32,
    max_chunks_per_document: int = 3, max_documents: int = 100,
    batch_size: int = 4, model_factory: Callable[[str], Any] | None = None,
    extractor: Callable[[Path], tuple[str, int]] = extract_document,
) -> dict[str, Any]:
    manifest = json.loads(manifest_bytes)
    if manifest.get("processing") != "local_only":
        raise ValueError("embedding persistence requires local_only processing")
    if manifest.get("embedding_enabled") is not False:
        raise ValueError("manifest must not pre-authorize embedding persistence")
    if manifest.get("external_ai_enabled") is not False:
        raise ValueError("external AI must remain disabled")
    if manifest.get("database_writes_enabled") is not False:
        raise ValueError("manifest database writes must remain disabled; use the explicit --apply mode")
    if model_factory is None:
        from sentence_transformers import SentenceTransformer
        model_factory = lambda path: SentenceTransformer(path, local_files_only=True)
    model = model_factory(str(model_path))
    tokenizer = getattr(model, "tokenizer", None)
    if tokenizer is None:
        raise ValueError("model must expose a tokenizer")
    chunks, errors = collect_embedding_chunks(
        manifest, tokenizer=tokenizer, max_chunks=max_chunks,
        max_chunks_per_document=max_chunks_per_document, max_documents=max_documents,
        extractor=extractor,
    )
    if not chunks:
        raise ValueError("no extractable chunks available for persistence")
    passages = [chunk.pop("passage") for chunk in chunks]
    vectors = model.encode(
        passages, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False,
    )
    vector_rows = vectors.tolist()
    if len(vector_rows) != len(chunks):
        raise ValueError("embedding count does not match prepared chunk count")
    for chunk, vector in zip(chunks, vector_rows):
        chunk["embedding"] = vector
    return build_storage_plan(manifest_bytes, chunks, batch_size=batch_size, errors=errors)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="semantic-embedding-acc-plan")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--model-path", type=Path, default=Path("/models") / MODEL_DIRECTORY)
    parser.add_argument("--max-chunks", type=int, default=32)
    parser.add_argument("--max-chunks-per-document", type=int, default=3)
    parser.add_argument("--max-documents", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=4)
    args = parser.parse_args(argv)
    plan = build_embedding_plan(
        args.manifest.read_bytes(), args.model_path,
        max_chunks=args.max_chunks, max_chunks_per_document=args.max_chunks_per_document,
        max_documents=args.max_documents, batch_size=args.batch_size,
    )
    print(json.dumps(plan, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
