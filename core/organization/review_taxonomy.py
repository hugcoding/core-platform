"""Configuration-driven, deterministic portal review options."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def taxonomy() -> dict[str, Any]:
    return json.loads(Path(__file__).with_name("document_taxonomy_v1.json").read_text(encoding="utf-8"))


def category_label(code: str) -> str:
    return next((item["label"] for item in taxonomy()["categories"] if item["code"] == code), code)


def family_label(code: str) -> str:
    return next((item["label"] for item in taxonomy()["families"] if item["code"] == code), code)


def contextual_options(row: dict[str, Any], proposal: dict[str, Any], maximum: int = 5) -> dict[str, Any]:
    """Return a small explained family shortlist plus the full searchable contract."""
    evidence = " ".join(str(row.get(key) or "") for key in ("filename", "path", "document_family")).casefold()
    category = str(proposal.get("category_code") or "needs_review")
    current = str(proposal.get("document_family_code") or "general")
    scored = []
    for order, family in enumerate(taxonomy()["families"]):
        score, reasons = 0, []
        if family["code"] == current:
            score += 100
            reasons.append("current_core_proposal")
        if category in family["categories"]:
            score += 20
            reasons.append("same_category")
        hits = [keyword for keyword in family.get("keywords", []) if keyword in evidence]
        if hits:
            score += 50 + len(hits)
            reasons.append("keyword_match")
        if score:
            scored.append((score, -order, {**family, "reason_codes": reasons}))
    compact = [item for _, _, item in sorted(scored, reverse=True)[:maximum]]
    return {
        "taxonomy_version": taxonomy()["version"],
        "categories": taxonomy()["categories"],
        "compact_families": compact,
        "all_families": taxonomy()["families"],
        "maximum_compact_options": maximum,
        "selection_method": "deterministic_context_v1",
    }
