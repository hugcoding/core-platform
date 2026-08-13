"""Bounded, provenance-rich context for future portal LLM advice."""

from __future__ import annotations

from typing import Any


def build_llm_learning_context(candidates: list[dict[str, Any]], limit: int = 10) -> dict[str, Any]:
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
