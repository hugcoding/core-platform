from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.semantic.embedding_benchmark import MODEL_DIRECTORY, OVERLAP_TOKENS, TARGET_TOKENS
from core.semantic.extraction import extract_document


def build_contexts(manifest: dict, model_path: Path, max_chunks: int = 3) -> list[dict]:
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    step = TARGET_TOKENS - OVERLAP_TOKENS
    results = []
    for item in manifest["files"]:
        try:
            text, _ = extract_document(Path(item["path"]))
            ids = tokenizer.encode(text, add_special_tokens=False, verbose=False)
            chunks = [ids[start : start + TARGET_TOKENS] for start in range(0, len(ids), step)]
            chunks = [chunk for chunk in chunks if chunk]
            if not chunks:
                raise ValueError("no_extractable_text")
            if len(chunks) <= max_chunks:
                indexes = list(range(len(chunks)))
            elif max_chunks == 1:
                indexes = [len(chunks) // 2]
            else:
                indexes = [round(i * (len(chunks) - 1) / (max_chunks - 1)) for i in range(max_chunks)]
            results.append({
                **item, "status": "ready", "chunks": [{
                    "ordinal": index,
                    "text": tokenizer.decode(chunks[index], skip_special_tokens=True).strip(),
                } for index in dict.fromkeys(indexes)],
            })
        except Exception as exc:
            results.append({**item, "status": "needs_review", "error": str(exc), "chunks": []})
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", type=Path, default=Path("/models") / MODEL_DIRECTORY)
    parser.add_argument("--max-chunks", type=int, default=3)
    args = parser.parse_args(argv)
    print(json.dumps({
        "documents": build_contexts(json.load(sys.stdin), args.model_path, args.max_chunks),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
