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


CATEGORY_SIGNALS = {
    "work_career": ("/werk/", "sollicit", "vacature", "cv & sollicitaties", "contractvoorstel", "werkgever"),
    "home_living": ("/wonen/", "/vve ", "/vve/", "woning", "eksterlaan", "riolering", "onderhoud"),
    "finance": ("/geldzaken/", "belasting", "factuur", "bank", "hypotheek", "toeslag", "salaris"),
    "health": ("/gezondheid/", "medisch", "huisarts", "ziekenhuis", "zorg"),
    "family_relationships": ("/gezin", "familie", "relatie"),
    "learning_development": ("/studie/", "/opleiding/", "cursus", "certificaat", "diploma"),
    "identity_personal": ("/persoonlijk/", "paspoort", "rijbewijs", "geboorteakte", "identiteit"),
    "legal": ("/juridisch/", "bezwaar", "beroep", "rechtbank", "advocaat"),
}


def category_options(row: dict[str, Any], proposal: dict[str, Any], maximum: int = 4) -> list[dict[str, Any]]:
    """Rank content categories; workflow state needs_review is never an option."""
    evidence = "/" + " ".join(str(row.get(key) or "") for key in ("path", "filename")).replace("\\", "/").casefold()
    current = str(proposal.get("category_code") or "")
    categories = [item for item in taxonomy()["categories"] if item["code"] != "needs_review"]
    scores: list[tuple[int, int, dict[str, Any]]] = []
    for order, item in enumerate(categories):
        hits = [signal for signal in CATEGORY_SIGNALS.get(item["code"], ()) if signal in evidence]
        score = len(hits) * 20
        reasons = ["path_or_filename_signal"] if hits else []
        if current == item["code"]:
            score += 100
            reasons.insert(0, "current_core_proposal")
        if score:
            confidence = "high" if score >= 100 and hits else "medium" if hits else "low"
            scores.append((score, -order, {**item, "reason_codes": reasons, "confidence": confidence}))
    ranked = [item for _, _, item in sorted(scores, reverse=True)]
    for item in categories:
        if len(ranked) >= maximum:
            break
        if not any(candidate["code"] == item["code"] for candidate in ranked):
            ranked.append({**item, "reason_codes": ["alternative"], "confidence": "low"})
    return ranked[:maximum]


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
        "category_options": category_options(row, proposal),
        "compact_families": compact,
        "all_families": taxonomy()["families"],
        "maximum_compact_options": maximum,
        "selection_method": "deterministic_context_v1",
    }
