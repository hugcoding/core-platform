"""Proposal-only learning of bounded course contexts from human reviews."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any


LEARNING_CONTEXT_TERMS = {
    "cursus", "opleiding", "studie", "training", "introductie", "python",
    "data science", "notebook", "jupyter",
}


def build_llm_learning_context(candidates: list[dict[str, Any]], limit: int = 10) -> dict[str, Any]:
    """Keep the existing bounded LLM context contract alongside course learning."""
    selected = [item for item in candidates if item.get("confidence") in {"medium", "high"}][:limit]
    return {
        "context_version": "review-learning-llm-context-v1",
        "provenance": "append_only_human_portal_reviews",
        "usage": "advisory_only",
        "rules_activated": False,
        "file_mutations_allowed": False,
        "candidates": [{
            "source_family_code": item["source_family_code"],
            "target_category_code": item["target_category_code"],
            "target_family_code": item["target_family_code"],
            "support": item["support"],
            "confidence": item["confidence"],
            "conflict_count": item["conflict_count"],
            "instruction": item["llm_context"]["instruction"],
        } for item in selected],
    }


def normalized_context(value: str) -> str:
    return " ".join(token for token in re.split(r"[^a-z0-9]+", value.casefold()) if token)


def course_context_from_path(path: str) -> tuple[str, str] | None:
    parts = list(PurePosixPath(path.replace("\\", "/")).parts)
    folded = [normalized_context(part) for part in parts]
    marker = next((index for index, part in enumerate(folded) if part == "documenten"), None)
    if marker is None or marker + 1 >= len(parts) - 1:
        return None
    label = parts[marker + 1].strip()
    code = normalized_context(label)
    if len(code) < 5 or not any(term in code for term in LEARNING_CONTEXT_TERMS):
        return None
    return code, label


def build_learning_context_rules(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest = {int(row["file_id"]): row for row in rows}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    labels: dict[str, str] = {}
    judgments: dict[str, set[str]] = defaultdict(set)
    for row in latest.values():
        if row.get("decision") != "accepted":
            continue
        context = course_context_from_path(str(row.get("path") or ""))
        category = str(row.get("corrected_category_code") or "")
        if not context or not category:
            continue
        code, label = context
        judgments[code].add(category)
        if category == "learning_development":
            labels.setdefault(code, label)
            grouped[code].append(row)
    rules = []
    for code, examples in grouped.items():
        if judgments[code] != {"learning_development"}:
            continue
        support = len(examples)
        rules.append({
            "candidate_type": "learning_course_context_rule",
            "context_code": code,
            "context_label": labels[code],
            "category_code": "learning_development",
            "family_code": "course_material",
            "support": support,
            "confidence": "high" if support >= 3 else "medium",
            "counterexample_count": 0,
            "source_review_event_ids": sorted(str(row["id"]) for row in examples)[:10],
            "reason_codes": ["exact_course_context", "accepted_human_classification"],
            "activation_status": "proposal_only",
        })
    return sorted(rules, key=lambda rule: (-rule["support"], rule["context_label"].casefold()))


def matching_learning_context_rule(
    document: dict[str, Any], rules: list[dict[str, Any]],
) -> dict[str, Any] | None:
    context = course_context_from_path(str(document.get("path") or ""))
    if not context:
        return None
    matches = [rule for rule in rules if rule["context_code"] == context[0]]
    return matches[0] if len(matches) == 1 else None
