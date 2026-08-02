from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable

from core.semantic.extraction import extract_document


MODEL_ID = "intfloat/multilingual-e5-small"
MODEL_REVISION = "fd1525a9fd15316a2d503bf26ab031a61d056e98"
MODEL_DIRECTORY = "multilingual-e5-small"
TARGET_TOKENS = 384
OVERLAP_TOKENS = 64
TOKEN_CHUNKER_VERSION = "e5-tokens-384-overlap-64-v1"


def peak_rss_mib() -> float | None:
    try:
        import resource
    except ImportError:
        return None
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("processing") != "local_only":
        raise ValueError("benchmark requires local_only processing")
    if manifest.get("embedding_enabled") is not False:
        raise ValueError("manifest must not pre-authorize embedding persistence")
    if manifest.get("external_ai_enabled") is not False:
        raise ValueError("external AI must remain disabled")
    if manifest.get("database_writes_enabled") is not False:
        raise ValueError("database writes must remain disabled")
    return manifest


def collect_passages(
    manifest: dict[str, Any], *, tokenizer: Any, max_chunks: int,
    target_tokens: int = TARGET_TOKENS, overlap_tokens: int = OVERLAP_TOKENS,
    extractor: Callable[[Path], tuple[str, int]] = extract_document,
) -> tuple[list[str], dict[str, int]]:
    if max_chunks < 1:
        raise ValueError("max_chunks must be positive")
    if overlap_tokens < 0 or overlap_tokens >= target_tokens:
        raise ValueError("overlap_tokens must be between zero and target_tokens")
    passages: list[str] = []
    stats = {"source_documents": 0, "skipped_no_text": 0, "errors": 0}
    for item in manifest["files"]:
        if item.get("approval") != "approved":
            continue
        try:
            text, _ = extractor(Path(item["path"]))
            token_ids = tokenizer.encode(text, add_special_tokens=False)
            chunks = []
            step = target_tokens - overlap_tokens
            for start in range(0, len(token_ids), step):
                if start and len(token_ids) - start <= overlap_tokens:
                    break
                token_chunk = token_ids[start : start + target_tokens]
                if token_chunk:
                    chunks.append(tokenizer.decode(token_chunk, skip_special_tokens=True))
        except Exception:
            stats["errors"] += 1
            continue
        if not chunks:
            stats["skipped_no_text"] += 1
            continue
        stats["source_documents"] += 1
        passages.extend(f"passage: {chunk}" for chunk in chunks[: max_chunks - len(passages)])
        if len(passages) >= max_chunks:
            break
    return passages, stats


def run_benchmark(
    manifest: dict[str, Any], model_path: Path, *, max_chunks: int = 32,
    batch_size: int = 4, model_factory: Callable[[str], Any] | None = None,
    extractor: Callable[[Path], tuple[str, int]] = extract_document,
) -> dict[str, Any]:
    if not model_path.is_dir():
        raise FileNotFoundError(f"local model not found: {model_path}")
    if model_factory is None:
        from sentence_transformers import SentenceTransformer
        model_factory = lambda path: SentenceTransformer(path, local_files_only=True)

    load_started = time.perf_counter()
    model = model_factory(str(model_path))
    load_seconds = time.perf_counter() - load_started
    max_sequence_length = int(getattr(model, "max_seq_length", 0) or 0)
    tokenizer = getattr(model, "tokenizer", None)
    if tokenizer is None or not max_sequence_length:
        raise ValueError("model must expose a tokenizer and max_seq_length")
    passages, stats = collect_passages(
        manifest, tokenizer=tokenizer, max_chunks=max_chunks, extractor=extractor,
    )
    if not passages:
        raise ValueError("no extractable chunks available for benchmark")
    tokenized = tokenizer(passages, add_special_tokens=True, truncation=False, padding=False)
    input_token_counts = [len(ids) for ids in tokenized["input_ids"]]
    truncated_chunks = sum(count > max_sequence_length for count in input_token_counts)
    if truncated_chunks:
        raise RuntimeError(
            f"token chunker produced {truncated_chunks} inputs above model limit; refusing silent truncation"
        )

    encode_started = time.perf_counter()
    vectors = model.encode(passages, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False)
    encode_seconds = time.perf_counter() - encode_started
    dimension = int(vectors.shape[1])
    chunks = int(vectors.shape[0])
    del vectors
    del passages
    return {
        "schema_version": "semantic-embedding-benchmark-v1",
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "chunker_version": TOKEN_CHUNKER_VERSION,
        "target_tokens": TARGET_TOKENS,
        "overlap_tokens": OVERLAP_TOKENS,
        "dimension": dimension,
        "chunks": chunks,
        **stats,
        "batch_size": batch_size,
        "model_load_seconds": round(load_seconds, 3),
        "embedding_seconds": round(encode_seconds, 3),
        "chunks_per_second": round(chunks / encode_seconds, 3) if encode_seconds else None,
        "peak_rss_mib": peak_rss_mib(),
        "estimated_float32_bytes": chunks * dimension * 4,
        "model_max_sequence_length": max_sequence_length or None,
        "max_input_tokens": max(input_token_counts),
        "truncated_chunks": truncated_chunks,
        "network_enabled": False,
        "database_writes": False,
        "vectors_stored": False,
        "raw_text_stored": False,
    }


def fetch_model(target: Path) -> None:
    from huggingface_hub import snapshot_download
    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=MODEL_ID, revision=MODEL_REVISION, local_dir=target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="semantic-embedding-benchmark")
    subparsers = parser.add_subparsers(dest="command", required=True)
    fetch = subparsers.add_parser("fetch")
    fetch.add_argument("--target", required=True, type=Path)
    benchmark = subparsers.add_parser("benchmark")
    benchmark.add_argument("--manifest", required=True, type=Path)
    benchmark.add_argument("--model-path", required=True, type=Path)
    benchmark.add_argument("--max-chunks", type=int, default=32)
    benchmark.add_argument("--batch-size", type=int, default=4)
    args = parser.parse_args(argv)
    if args.command == "fetch":
        fetch_model(args.target)
        return 0
    result = run_benchmark(load_manifest(args.manifest), args.model_path,
                           max_chunks=args.max_chunks, batch_size=args.batch_size)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
