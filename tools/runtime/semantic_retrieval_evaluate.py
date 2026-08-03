#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.semantic.retrieval_evaluation import evaluate_results, load_evaluation, render_markdown
from core.semantic.similarity import render_hybrid_query_similarity_sql, render_query_similarity_sql
from tools.runtime.semantic_similarity import psql, query_vectors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate read-only semantic rankings in ACC.")
    parser.add_argument("config")
    args = parser.parse_args(argv)
    config_path = Path(args.config).resolve()
    if not config_path.is_file():
        parser.error(f"evaluation config not found: {config_path}")
    config = load_evaluation(config_path)
    queries = [item["query"] for item in config["queries"]]
    vectors = query_vectors(queries)
    if len(vectors) != len(queries):
        raise ValueError("query embedding count does not match evaluation query count")
    runs = {"embedding-v1": [], "hybrid-v1": []}
    for query, vector in zip(queries, vectors):
        runs["embedding-v1"].append(psql(render_query_similarity_sql(vector, limit=10)))
        runs["hybrid-v1"].append(psql(render_hybrid_query_similarity_sql(vector, query, limit=10)))
    report = evaluate_results(config, runs)
    report.update({
        "read_only": True,
        "database_writes": False,
        "query_text_stored_in_database": False,
        "evaluation_config": str(config_path),
    })
    export_dir = ROOT / "project/exports/semantic-pilot"
    export_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    json_path = export_dir / f"semantic-retrieval-evaluation-{stamp}.json"
    markdown_path = export_dir / f"semantic-retrieval-evaluation-{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({
        "status": "completed", "read_only": True,
        "embedding": report["rankings"]["embedding-v1"],
        "hybrid": report["rankings"]["hybrid-v1"],
        "json_report": str(json_path.relative_to(ROOT)),
        "markdown_report": str(markdown_path.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
