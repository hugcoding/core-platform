"""Configuration-driven, deterministic portal review options."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from collections import Counter


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


def category_options(
    row: dict[str, Any],
    proposal: dict[str, Any],
    maximum: int = 4,
) -> list[dict[str, Any]]:
    """Rank categories using direct signals and family keyword evidence."""

    evidence = (
        "/"
        + " ".join(
            str(row.get(key) or "")
            for key in ("path", "filename")
        )
        .replace("\\", "/")
        .casefold()
    )

    current = str(proposal.get("category_code") or "")

    categories = [
        item
        for item in taxonomy()["categories"]
        if item["code"] != "needs_review"
    ]

    scores: list[tuple[int, int, dict[str, Any]]] = []

    for order, item in enumerate(categories):
        score = 0
        reasons: list[str] = []

        # 1. Bestaande directe categorie-signalen.
        direct_hits = [
            signal
            for signal in CATEGORY_SIGNALS.get(item["code"], ())
            if signal in evidence
        ]

        if direct_hits:
            score += len(direct_hits) * 20
            reasons.append("path_or_filename_signal")

        # 2. Keywords van families die bij deze categorie horen.
        family_hits: list[dict[str, Any]] = []

        for family in taxonomy()["families"]:
            if item["code"] not in family.get("categories", []):
                continue

            hits = [
                keyword
                for keyword in family.get("keywords", [])
                if str(keyword).casefold() in evidence
            ]

            if not hits:
                continue

            family_hits.append({
                "family_code": family["code"],
                "hits": hits,
            })

            # Een family-keyword is sterker bewijs dan een
            # algemeen categorie-signaal.
            score += 40 + (len(hits) * 10)

        if family_hits:
            reasons.append("family_keyword_match")

        # 3. Het bestaande CORE-voorstel blijft zwaar meewegen.
        if current == item["code"]:
            score += 100
            reasons.insert(0, "current_core_proposal")

        if not score:
            continue

        if score >= 100:
            confidence = "high"
        elif score >= 50:
            confidence = "medium"
        else:
            confidence = "low"

        scores.append((
            score,
            -order,
            {
                **item,
                "reason_codes": reasons,
                "confidence": confidence,
                "family_evidence": family_hits,
            },
        ))

    ranked = [
        item
        for _, _, item
        in sorted(scores, reverse=True)
    ]

    # Vul de lijst aan met alternatieven zodat de UI bruikbaar blijft.
    for item in categories:
        if len(ranked) >= maximum:
            break

        if not any(
            candidate["code"] == item["code"]
            for candidate in ranked
        ):
            ranked.append({
                **item,
                "reason_codes": ["alternative"],
                "confidence": "low",
                "family_evidence": [],
            })

    return ranked[:maximum]

def taxonomy_fallback_proposal(
    row: dict[str, Any],
    proposal: dict[str, Any],
) -> dict[str, Any] | None:
    """Suggest category + family when CORE has no reliable classification."""
    current_category = str(proposal.get("category_code") or "")

    if current_category and current_category != "needs_review":
        return None

    evidence = " ".join(
        str(row.get(key) or "")
        for key in ("filename", "path", "document_family")
    ).casefold()

    matches: list[tuple[int, int, dict[str, Any], list[str]]] = []

    for order, family in enumerate(taxonomy()["families"]):
        if family["code"] == "general":
            continue

        hits = [
            keyword
            for keyword in family.get("keywords", [])
            if keyword.casefold() in evidence
        ]

        if not hits:
            continue

        # Longer/multiple matching keywords provide stronger evidence.
        score = (
            len(hits) * 100
            + max(len(keyword) for keyword in hits)
        )

        matches.append((score, -order, family, hits))

    if not matches:
        return None

    matches.sort(reverse=True, key=lambda item: (item[0], item[1]))

    best_score, _, family, hits = matches[0]

    # Do not guess between multiple categories without additional evidence.
    categories = family.get("categories", [])

    if len(categories) != 1:
        category_scores: Counter[str] = Counter()

        path_evidence = "/" + str(row.get("path") or "").replace("\\", "/").casefold()

        for category in categories:
            for signal in CATEGORY_SIGNALS.get(category, ()):
                if signal in path_evidence:
                    category_scores[category] += 1

        if category_scores:
            category = category_scores.most_common(1)[0][0]
        else:
            # Taxonomy order is the deterministic fallback.
            category = categories[0]
    else:
        category = categories[0]

    return {
        "category_code": category,
        "document_family_code": family["code"],
        "family_label": family["label"],
        "matched_keywords": hits,
        "score": best_score,
        "confidence": "high" if len(hits) >= 2 else "medium",
        "reason_code": "taxonomy_keyword_fallback",
    }

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
