from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "semantic-retrieval-evaluation-v1"


def load_evaluation(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"expected schema_version={SCHEMA_VERSION}")
    queries = config.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("evaluation requires at least one query")
    seen = set()
    for item in queries:
        if not item.get("id") or item["id"] in seen:
            raise ValueError("query ids must be present and unique")
        seen.add(item["id"])
        if not str(item.get("query", "")).strip():
            raise ValueError("query text must not be empty")
        expected = item.get("expected_file_ids")
        if not isinstance(expected, list) or not expected:
            raise ValueError("every query requires expected_file_ids")
        item["expected_file_ids"] = [int(value) for value in expected]
        item["irrelevant_file_ids"] = [int(value) for value in item.get("irrelevant_file_ids", [])]
    return config


def evaluate_results(config: dict[str, Any], runs: dict[str, list[list[dict]]]) -> dict[str, Any]:
    output: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "query_count": len(config["queries"]), "rankings": {}}
    for ranking, result_sets in runs.items():
        details = []
        reciprocal_sum = 0.0
        hits = {1: 0, 3: 0, 10: 0}
        irrelevant_top3 = 0
        for item, rows in zip(config["queries"], result_sets, strict=True):
            ids = [int(row["file_id"]) for row in rows]
            ranks = [ids.index(file_id) + 1 for file_id in item["expected_file_ids"] if file_id in ids]
            best_rank = min(ranks) if ranks else None
            if best_rank:
                reciprocal_sum += 1.0 / best_rank
                for cutoff in hits:
                    hits[cutoff] += best_rank <= cutoff
            irrelevant_top3 += sum(file_id in ids[:3] for file_id in item["irrelevant_file_ids"])
            details.append({
                "id": item["id"], "query": item["query"], "best_expected_rank": best_rank,
                "top_file_ids": ids[:10], "expected_file_ids": item["expected_file_ids"],
            })
        count = len(config["queries"])
        output["rankings"][ranking] = {
            "hit_at_1": round(hits[1] / count, 4),
            "hit_at_3": round(hits[3] / count, 4),
            "hit_at_10": round(hits[10] / count, 4),
            "mean_reciprocal_rank": round(reciprocal_sum / count, 4),
            "irrelevant_in_top_3": irrelevant_top3,
            "queries": details,
        }
    return output


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Semantic retrieval evaluation", "", f"Queries: **{report['query_count']}**", "", "| Ranking | Hit@1 | Hit@3 | Hit@10 | MRR | Irrelevant top 3 |", "|---|---:|---:|---:|---:|---:|"]
    for name, metrics in report["rankings"].items():
        lines.append(f"| `{name}` | {metrics['hit_at_1']:.4f} | {metrics['hit_at_3']:.4f} | {metrics['hit_at_10']:.4f} | {metrics['mean_reciprocal_rank']:.4f} | {metrics['irrelevant_in_top_3']} |")
    lines.extend(["", "Scores are evaluation metrics, not classification confidence or cleanup authorization.", ""])
    return "\n".join(lines)
