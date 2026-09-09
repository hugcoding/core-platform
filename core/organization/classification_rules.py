"""Versioned, explainable multilingual classification signals for SCRUM-147."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any


RULESET_VERSION = "classification-signals-v2"
SOURCE_WEIGHTS = {"filename": 4, "source_context_path": 3, "path": 1, "metadata": 1}

# Specific phrases deliberately precede broad words. Scores are aggregated by
# category/family, so corroborating filename and provenance evidence wins.
SIGNAL_RULES = (
    ("employment agreement", "work_career", "employment_documents", 4),
    ("employment contract", "work_career", "employment_documents", 4),
    ("secondment agreement", "work_career", "employment_documents", 4),
    ("compensation letter", "work_career", "employment_documents", 4),
    ("job profile", "work_career", "vacancies", 4),
    ("pension scheme", "finance", "pension_documents", 4),
    ("payroll", "finance", "salary_slips", 3),
    ("kadastrale kaart", "home_living", "property_documents", 4),
    ("kadastraal", "home_living", "property_documents", 3),
    ("leveringsakte", "home_living", "property_documents", 4),
    ("levering", "home_living", "property_documents", 2),
    ("mjop", "home_living", "vve_documents", 4),
    ("meerjarenonderhoudsplan", "home_living", "vve_documents", 4),
    ("programmeren", "learning_development", "course_material", 3),
    ("java", "learning_development", "course_material", 2),
    ("modopdr", "learning_development", "course_material", 4),
    ("badkamer", "home_living", "home_maintenance", 3),
    ("tuin", "home_living", "home_maintenance", 2),
    ("elektra", "home_living", "home_maintenance", 3),
    ("uitbouw", "home_living", "home_maintenance", 3),
    ("verbouwing", "home_living", "home_maintenance", 3),
    # An offer is intentionally weak: provenance must corroborate it.
    ("offerte", "home_living", "home_maintenance", 1),
)


def _normalize(value: Any) -> str:
    folded = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return " ".join(re.split(r"[^a-z0-9]+", folded.casefold())).strip()


def classify_weighted(row: dict[str, Any]) -> dict[str, Any]:
    def directory_context(value: Any) -> str:
        path = str(value or "").replace("\\", "/")
        return "/".join(PurePosixPath(path).parts[:-1])

    sources = {
        "filename": row.get("filename"),
        "source_context_path": directory_context(row.get("source_context_path")),
        "path": directory_context(row.get("path")),
        "metadata": " ".join(str(row.get(key) or "") for key in ("title", "subject", "document_type")),
    }
    scores: dict[tuple[str, str], int] = defaultdict(int)
    matches: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for source, raw in sources.items():
        evidence = _normalize(raw)
        if not evidence:
            continue
        padded = f" {evidence} "
        for term, category, family, rule_weight in SIGNAL_RULES:
            normalized_term = _normalize(term)
            if f" {normalized_term} " not in padded:
                continue
            key = (source, category, family)
            if key in seen:
                continue
            seen.add(key)
            weight = SOURCE_WEIGHTS[source] + rule_weight
            scores[(category, family)] += weight
            matches.append({
                "term": term, "source": source, "weight": weight,
                "category_code": category, "document_family_code": family,
            })
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    if not ranked:
        return {"status": "abstained", "reason_code": "no_weighted_signal", "confidence": "low",
                "ruleset_version": RULESET_VERSION, "matched_signals": []}
    (category, family), score = ranked[0]
    competing = [
        {"category_code": pair[0], "document_family_code": pair[1], "score": value}
        for pair, value in ranked[1:] if pair[0] != category and score - value <= 2
    ]
    if competing or score < 6:
        return {"status": "conflict" if competing else "abstained",
                "reason_code": "conflicting_weighted_signals" if competing else "insufficient_weighted_signal",
                "confidence": "low", "ruleset_version": RULESET_VERSION,
                "matched_signals": matches, "competing_candidates": competing}
    corroborated = len({match["source"] for match in matches if match["category_code"] == category
                        and match["document_family_code"] == family}) > 1
    return {"status": "proposed", "reason_code": "weighted_multilingual_signal",
            "confidence": "high" if score >= 10 or corroborated else "medium",
            "ruleset_version": RULESET_VERSION, "category_code": category,
            "document_family_code": family, "score": score,
            "matched_signals": matches, "competing_candidates": []}
