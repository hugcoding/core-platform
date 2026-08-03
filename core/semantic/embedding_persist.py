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
    extractor: Callable[[Path], tuple[str, int]] = extract_document,
) -> tuple[list[dict[str, Any]], int]:
    if max_chunks < 1:
        raise ValueError("max_chunks must be positive")
    chunks: list[dict[str, Any]] = []
    errors = 0
    step = TARGET_TOKENS - OVERLAP_TOKENS
    for item in manifest["files"]:
        if item.get("approval") != "approved":
            continue
        path = Path(item["path"])
        try:
            text, _ = extractor(path)
            token_ids = tokenizer.encode(text, add_special_tokens=False, verbose=False)
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
                chunks.append({
                    "file_id": int(item["file_id"]),
                    "chunk_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                    "ordinal": ordinal,
                    "content_sha256": item["content_sha256"],
                    "token_count": len(ids),
                    "passage": passage,
                })
                ordinal += 1
                if len(chunks) >= max_chunks:
                    return chunks, errors
        except Exception:
            errors += 1
    return chunks, errors


def build_embedding_plan(
    manifest_bytes: bytes, model_path: Path, *, max_chunks: int = 32,
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
        manifest, tokenizer=tokenizer, max_chunks=max_chunks, extractor=extractor,
    )
    if not chunks:
        raise ValueError("no extractable chunks available for persistence")
    passages = [chunk.pop("passage") for chunk in chunks]
    vectors = model.encode(
        passages, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False,
    )
    for chunk, vector in zip(chunks, vectors.tolist(), strict=True):
        chunk["embedding"] = vector
    return build_storage_plan(manifest_bytes, chunks, batch_size=batch_size, errors=errors)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="semantic-embedding-acc-plan")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--model-path", type=Path, default=Path("/models") / MODEL_DIRECTORY)
    parser.add_argument("--max-chunks", type=int, default=32)
    parser.add_argument("--batch-size", type=int, default=4)
    args = parser.parse_args(argv)
    plan = build_embedding_plan(
        args.manifest.read_bytes(), args.model_path,
        max_chunks=args.max_chunks, batch_size=args.batch_size,
    )
    print(json.dumps(plan, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
