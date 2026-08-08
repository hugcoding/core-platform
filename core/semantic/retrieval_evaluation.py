from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


SCHEMA_VERSION_V1 = "semantic-retrieval-evaluation-v1"
SCHEMA_VERSION_V2 = "semantic-retrieval-evaluation-v2"
SCHEMA_VERSIONS = {SCHEMA_VERSION_V1, SCHEMA_VERSION_V2}
RELEVANCE_GRADES = {"irrelevant": 0, "hard_negative": 0, "related": 1, "relevant": 2}
REVIEW_FIELDS = (
    "ranking", "query_id", "query", "rank", "file_id", "filename", "path",
    "similarity", "lexical_similarity", "ranking_score", "proposed_judgment",
    "review_judgment", "document_family", "reviewer_notes",
)


def _ids(values: Any, field: str) -> list[int]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field} must be a list")
    result = [int(value) for value in values]
    if any(value < 1 for value in result):
        raise ValueError(f"{field} must contain positive file ids")
    return list(dict.fromkeys(result))


def _families(config: dict[str, Any]) -> dict[str, list[int]]:
    output: dict[str, list[int]] = {}
    for family in config.get("document_families", []):
        family_id = str(family.get("id", "")).strip()
        if not family_id or family_id in output:
            raise ValueError("document family ids must be present and unique")
        file_ids = _ids(family.get("file_ids"), f"document family {family_id}.file_ids")
        if not file_ids:
            raise ValueError(f"document family {family_id} requires file_ids")
        output[family_id] = file_ids
    return output


def review_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for ranking, metrics in report["rankings"].items():
        for query in metrics["queries"]:
            for result in query["top_10_review"]:
                proposed = result["judgment"]
                rows.append({
                    "ranking": ranking,
                    "query_id": query["id"],
                    "query": query["query"],
                    "rank": result["rank"],
                    "file_id": result["file_id"],
                    "filename": result.get("filename") or "",
                    "path": result.get("path") or "",
                    "similarity": result.get("similarity") or "",
                    "lexical_similarity": result.get("lexical_similarity") or "",
                    "ranking_score": result.get("ranking_score") or "",
                    "proposed_judgment": proposed,
                    "review_judgment": "" if proposed == "unjudged" else proposed,
                    "document_family": "",
                    "reviewer_notes": "",
                })
    return rows


def _expand_families(item: dict[str, Any], grade: str, families: dict[str, list[int]]) -> list[int]:
    values = _ids(item.get(f"{grade}_file_ids"), f"{grade}_file_ids")
    family_ids = item.get(f"{grade}_families", [])
    if not isinstance(family_ids, list):
        raise ValueError(f"{grade}_families must be a list")
    for family_id in family_ids:
        if family_id not in families:
            raise ValueError(f"unknown document family: {family_id}")
        values.extend(families[family_id])
    return list(dict.fromkeys(values))


def load_evaluation(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    schema_version = config.get("schema_version")
    if schema_version not in SCHEMA_VERSIONS:
        raise ValueError(f"expected schema_version in {sorted(SCHEMA_VERSIONS)}")
    queries = config.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("evaluation requires at least one query")
    families = _families(config) if schema_version == SCHEMA_VERSION_V2 else {}
    seen = set()
    for item in queries:
        if not item.get("id") or item["id"] in seen:
            raise ValueError("query ids must be present and unique")
        seen.add(item["id"])
        if not str(item.get("query", "")).strip():
            raise ValueError("query text must not be empty")
        if schema_version == SCHEMA_VERSION_V1:
            relevant = _ids(item.get("expected_file_ids"), "expected_file_ids")
            if not relevant:
                raise ValueError("every v1 query requires expected_file_ids")
            judgments = {
                "relevant": relevant,
                "related": [],
                "hard_negative": [],
                "irrelevant": _ids(item.get("irrelevant_file_ids"), "irrelevant_file_ids"),
            }
            item["expected_file_ids"] = relevant
            item["irrelevant_file_ids"] = judgments["irrelevant"]
        else:
            judgments = {grade: _expand_families(item, grade, families) for grade in RELEVANCE_GRADES}
            if not judgments["relevant"]:
                raise ValueError("every v2 query requires relevant files or families")
        assigned: dict[int, str] = {}
        for grade, file_ids in judgments.items():
            for file_id in file_ids:
                if file_id in assigned:
                    raise ValueError(
                        f"query {item['id']} assigns file {file_id} to both {assigned[file_id]} and {grade}"
                    )
                assigned[file_id] = grade
        item["judgments"] = judgments
    config["document_family_count"] = len(families)
    return config


def _dcg(grades: list[int]) -> float:
    return sum((2 ** grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(grades, start=1))


def _ndcg_at_10(rows: list[dict], judgment_by_id: dict[int, str]) -> float:
    actual = [RELEVANCE_GRADES.get(judgment_by_id.get(int(row["file_id"]), "irrelevant"), 0) for row in rows[:10]]
    ideal = sorted((RELEVANCE_GRADES[grade] for grade in judgment_by_id.values()), reverse=True)[:10]
    ideal_dcg = _dcg(ideal)
    return _dcg(actual) / ideal_dcg if ideal_dcg else 0.0


def evaluate_results(config: dict[str, Any], runs: dict[str, list[list[dict]]]) -> dict[str, Any]:
    output: dict[str, Any] = {
        "schema_version": config["schema_version"],
        "query_count": len(config["queries"]),
        "document_family_count": config.get("document_family_count", 0),
        "rankings": {},
    }
    for ranking, result_sets in runs.items():
        if len(result_sets) != len(config["queries"]):
            raise ValueError(f"result count for {ranking} does not match evaluation query count")
        details = []
        reciprocal_sum = ndcg_sum = 0.0
        hits = {1: 0, 3: 0, 10: 0}
        hard_negative_top3 = irrelevant_top3 = 0
        for item, rows in zip(config["queries"], result_sets):
            judgment_by_id = {
                file_id: grade for grade, file_ids in item["judgments"].items() for file_id in file_ids
            }
            ids = [int(row["file_id"]) for row in rows]
            relevant_ids = item["judgments"]["relevant"]
            ranks = [ids.index(file_id) + 1 for file_id in relevant_ids if file_id in ids]
            best_rank = min(ranks) if ranks else None
            if best_rank:
                reciprocal_sum += 1.0 / best_rank
                for cutoff in hits:
                    hits[cutoff] += best_rank <= cutoff
            ndcg = _ndcg_at_10(rows, judgment_by_id)
            ndcg_sum += ndcg
            top3_grades = [judgment_by_id.get(file_id, "unjudged") for file_id in ids[:3]]
            hard_negative_top3 += top3_grades.count("hard_negative")
            irrelevant_top3 += top3_grades.count("irrelevant")
            reviewed_results = []
            for rank, row in enumerate(rows[:10], start=1):
                reviewed_results.append({
                    "rank": rank,
                    "file_id": int(row["file_id"]),
                    "filename": row.get("filename"),
                    "path": row.get("path"),
                    "similarity": row.get("similarity"),
                    "lexical_similarity": row.get("lexical_similarity"),
                    "ranking_score": row.get("ranking_score"),
                    "judgment": judgment_by_id.get(int(row["file_id"]), "unjudged"),
                })
            details.append({
                "id": item["id"], "query": item["query"], "best_relevant_rank": best_rank,
                "ndcg_at_10": round(ndcg, 4), "judgments": item["judgments"],
                "top_10_review": reviewed_results,
                # Preserve the v1 report keys for existing report consumers.
                "best_expected_rank": best_rank,
                "top_file_ids": ids[:10],
                "expected_file_ids": relevant_ids,
            })
        count = len(config["queries"])
        output["rankings"][ranking] = {
            "hit_at_1": round(hits[1] / count, 4),
            "hit_at_3": round(hits[3] / count, 4),
            "hit_at_10": round(hits[10] / count, 4),
            "mean_reciprocal_rank": round(reciprocal_sum / count, 4),
            "ndcg_at_10": round(ndcg_sum / count, 4),
            "hard_negative_in_top_3": hard_negative_top3,
            "irrelevant_in_top_3": irrelevant_top3,
            "queries": details,
        }
    return output


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Semantic retrieval evaluation", "",
        f"Schema: **{report['schema_version']}**  ",
        f"Queries: **{report['query_count']}**  ",
        f"Document families: **{report.get('document_family_count', 0)}**", "",
        "| Ranking | Hit@1 | Hit@3 | Hit@10 | MRR | NDCG@10 | Hard negatives top 3 | Irrelevant top 3 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, metrics in report["rankings"].items():
        lines.append(
            f"| `{name}` | {metrics['hit_at_1']:.4f} | {metrics['hit_at_3']:.4f} | "
            f"{metrics['hit_at_10']:.4f} | {metrics['mean_reciprocal_rank']:.4f} | "
            f"{metrics['ndcg_at_10']:.4f} | {metrics['hard_negative_in_top_3']} | "
            f"{metrics['irrelevant_in_top_3']} |"
        )
    lines.extend(["", "## Top-10 review", ""])
    for name, metrics in report["rankings"].items():
        lines.extend([f"### {name}", ""])
        for query in metrics["queries"]:
            lines.extend([
                f"#### {query['id']}", "", f"Query: `{query['query']}`  ",
                f"Best relevant rank: **{query['best_relevant_rank'] or '-'}**  ",
                f"NDCG@10: **{query['ndcg_at_10']:.4f}**", "",
                "| Rank | Judgment | File ID | Filename | Path | Score |", "|---:|---|---:|---|---|---:|",
            ])
            for row in query["top_10_review"]:
                filename = str(row.get("filename") or "").replace("|", "\\|")
                path = str(row.get("path") or "").replace("|", "\\|")
                score = row.get("ranking_score")
                lines.append(
                    f"| {row['rank']} | {row['judgment']} | {row['file_id']} | {filename} | {path} | "
                    f"{score if score is not None else '-'} |"
                )
            lines.append("")
    lines.extend([
        "Judgments: `relevant` = direct antwoord, `related` = bruikbare context, "
        "`hard_negative` = lijkt passend maar is inhoudelijk fout, `irrelevant` = beoordeeld als niet bruikbaar. "
        "Niet-beoordeelde resultaten staan als `unjudged`.", "",
        "Scores are evaluation metrics, not classification confidence or cleanup authorization.", "",
    ])
    return "\n".join(lines)
