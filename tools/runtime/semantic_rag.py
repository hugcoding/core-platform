#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.semantic.rag import (
    PROMPT_VERSION, RAG_SCHEMA_VERSION, GenerationRequest,
    OpenAICompatibleLocalProvider, abstention, build_prompts, render_markdown,
    validate_answer,
)
from core.semantic.similarity import render_hybrid_query_similarity_sql
from tools.runtime.semantic_similarity import psql, query_vector


def reconstruct_context(rows: list[dict]) -> list[dict]:
    image = os.getenv("SEMANTIC_BENCHMARK_IMAGE", "core-semantic-embedding-benchmark:local")
    command = [
        "docker", "run", "--rm", "-i", "--network", "none", "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=1g",
        "--volume", "/volume1:/volume1:ro",
        "--volume", f"{ROOT / 'core'}:/app/core:ro",
        "--volume", f"{ROOT / 'project/models'}:/models:ro",
        image, "python", "-m", "core.semantic.rag_context",
        "--model-path", "/models/multilingual-e5-small",
    ]
    completed = subprocess.run(
        command, input=json.dumps(rows), capture_output=True, text=True,
    )
    if completed.returncode:
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        raise RuntimeError("local context reconstruction failed")
    return json.loads(completed.stdout.strip().splitlines()[-1])["sources"]


def source_metadata(sources: list[dict]) -> list[dict]:
    fields = (
        "source_id", "file_id", "content_group_id", "path", "filename",
        "chunk_ordinal", "ranking_score", "similarity", "lexical_similarity",
    )
    return [{key: source.get(key) for key in fields} for source in sources]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only local RAG over CORE hybrid retrieval.")
    parser.add_argument("query")
    parser.add_argument("--model", required=False)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--limit", type=int, default=3, choices=range(1, 6), metavar="1..5")
    parser.add_argument("--threshold", type=float, default=0.40)
    parser.add_argument("--prompt", default=str(ROOT / "project/prompts/scrum-59-rag-v1.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.dry_run and not args.model:
        parser.error("--model is required unless --dry-run is used")

    prompt_config = json.loads(Path(args.prompt).read_text(encoding="utf-8"))
    if prompt_config.get("prompt_version") != PROMPT_VERSION:
        raise ValueError(f"unsupported prompt version: {prompt_config.get('prompt_version')}")
    vector = query_vector(args.query)
    rows = psql(render_hybrid_query_similarity_sql(
        vector, args.query, limit=args.limit, threshold=args.threshold,
    ))
    sources = reconstruct_context(rows) if rows else []
    system_prompt, user_prompt = build_prompts(
        args.query, sources, system_prompt=prompt_config["system_prompt"],
    )
    provider_metadata = None
    if args.dry_run:
        answer = abstention("dry_run_no_llm_invocation")
        status = "planned"
    elif not sources:
        answer = abstention("no_sources_above_threshold")
        status = "abstained"
    else:
        provider = OpenAICompatibleLocalProvider(args.endpoint)
        generated = provider.generate(GenerationRequest(
            model=args.model, system_prompt=system_prompt, user_prompt=user_prompt,
        ))
        answer = validate_answer(generated["content"], sources)
        provider_metadata = {
            "provider_id": provider.provider_id,
            "model": generated["model"], "usage": generated["usage"],
        }
        status = "abstained" if answer["abstained"] else "completed"

    report = {
        "schema_version": RAG_SCHEMA_VERSION, "prompt_version": PROMPT_VERSION,
        "status": status, "read_only": True, "database_writes": False,
        "original_documents_modified": False, "query": args.query,
        "retrieval": {"ranking": "hybrid-v1", "threshold": args.threshold, "limit": args.limit},
        "answer": answer, "sources": source_metadata(sources),
        "provider": provider_metadata,
    }
    export_dir = ROOT / "project/exports/semantic-pilot"
    export_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    output = export_dir / f"semantic-local-rag-{stamp}.json"
    markdown_output = export_dir / f"semantic-local-rag-{stamp}.md"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({
        **report, "json_report": str(output.relative_to(ROOT)),
        "markdown_report": str(markdown_output.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
