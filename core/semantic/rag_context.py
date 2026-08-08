from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.semantic.embedding_benchmark import MODEL_DIRECTORY, OVERLAP_TOKENS, TARGET_TOKENS
from core.semantic.extraction import extract_document


def reconstruct(rows: list[dict], model_path: Path) -> list[dict]:
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    step = TARGET_TOKENS - OVERLAP_TOKENS
    contexts = []
    for index, row in enumerate(rows, start=1):
        try:
            text, _ = extract_document(Path(row["path"]))
            token_ids = tokenizer.encode(text, add_special_tokens=False, verbose=False)
            ordinal = int(row["matched_chunk_ordinal"])
            start = ordinal * step
            selected = token_ids[start : start + TARGET_TOKENS]
            if not selected:
                continue
            contexts.append({
                **row, "source_id": f"S{index}", "chunk_ordinal": ordinal,
                "text": tokenizer.decode(selected, skip_special_tokens=True).strip(),
            })
        except Exception as exc:
            print(json.dumps({"file_id": row.get("file_id"), "error": str(exc)}), file=sys.stderr)
    return contexts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", type=Path, default=Path("/models") / MODEL_DIRECTORY)
    args = parser.parse_args(argv)
    rows = json.load(sys.stdin)
    print(json.dumps({"sources": reconstruct(rows, args.model_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
