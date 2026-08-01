from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable

from core.semantic.extraction import extract_document


TARGET_WORDS = 600
OVERLAP_WORDS = 75


def normalize_text(text: str) -> str:
    return " ".join(text.split())


def chunk_text(
    text: str,
    *,
    target_words: int = TARGET_WORDS,
    overlap_words: int = OVERLAP_WORDS,
) -> list[str]:
    if target_words < 1:
        raise ValueError("target_words must be positive")
    if overlap_words < 0 or overlap_words >= target_words:
        raise ValueError("overlap_words must be between zero and target_words")

    words = normalize_text(text).split()
    if not words:
        return []

    step = target_words - overlap_words
    chunks = []
    for start in range(0, len(words), step):
        if start and len(words) - start <= overlap_words:
            break
        chunks.append(" ".join(words[start : start + target_words]))
    return chunks


def _sha256_bytes(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _chunk_id(file_id: int, content_version: str, ordinal: int, text: str) -> str:
    chunk_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    identity = f"{file_id}:{content_version}:{ordinal}:{chunk_hash}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def plan_document_chunks(
    file_id: int,
    path: Path,
    *,
    extractor: Callable[[Path], tuple[str, int]] = extract_document,
) -> dict[str, Any]:
    text, pages = extractor(path)
    normalized = normalize_text(text)
    if not normalized:
        return {
            "file_id": file_id,
            "status": "needs_ocr" if path.suffix.lower() == ".pdf" else "no_text",
            "pages": pages or None,
            "characters": 0,
            "words": 0,
            "chunks": 0,
            "estimated_tokens": 0,
        }

    content_version = _sha256_bytes(path)
    chunks = chunk_text(normalized)
    chunk_words = [len(chunk.split()) for chunk in chunks]
    return {
        "file_id": file_id,
        "status": "planned",
        "pages": pages or None,
        "characters": len(normalized),
        "words": len(normalized.split()),
        "estimated_tokens": math.ceil(len(normalized) / 4),
        "chunks": len(chunks),
        "chunk_words_min": min(chunk_words),
        "chunk_words_max": max(chunk_words),
        "content_version": content_version,
        "chunk_ids": [
            _chunk_id(file_id, content_version, ordinal, chunk)
            for ordinal, chunk in enumerate(chunks)
        ],
    }


def run_manifest(
    manifest_path: Path,
    *,
    planner: Callable[[int, Path], dict[str, Any]] = plan_document_chunks,
) -> list[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("processing") != "local_only":
        raise ValueError("pilot manifest must require local_only processing")
    if manifest.get("embedding_enabled") is not False:
        raise ValueError("embeddings must be disabled for the chunking dry-run")
    if manifest.get("external_ai_enabled") is not False:
        raise ValueError("external AI must be disabled for the chunking dry-run")
    if manifest.get("database_writes_enabled") is not False:
        raise ValueError("database writes must be disabled for the chunking dry-run")

    results = []
    for item in manifest["files"]:
        if item["approval"] != "approved":
            results.append(
                {
                    "file_id": item["file_id"],
                    "status": "skipped",
                    "reason": f"approval={item['approval']}",
                }
            )
            continue
        try:
            results.append(planner(item["file_id"], Path(item["path"])))
        except Exception as exc:
            results.append(
                {
                    "file_id": item["file_id"],
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "reason": str(exc),
                }
            )
    return results


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    planned = [result for result in results if result["status"] == "planned"]
    return {
        "status": "summary",
        "documents": len(results),
        "planned_documents": len(planned),
        "needs_ocr": sum(result["status"] == "needs_ocr" for result in results),
        "errors": sum(result["status"] == "error" for result in results),
        "chunks": sum(result.get("chunks", 0) for result in results),
        "estimated_tokens": sum(result.get("estimated_tokens", 0) for result in results),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="semantic-pilot-chunks")
    parser.add_argument(
        "--manifest",
        default="/app/project/pilots/scrum-57-documents-v1.json",
    )
    args = parser.parse_args(argv)

    results = run_manifest(Path(args.manifest))
    for result in results:
        print(json.dumps(result, ensure_ascii=False))
    print(json.dumps(summarize(results), ensure_ascii=False))
    return 1 if any(result["status"] == "error" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
