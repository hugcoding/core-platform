"""Deterministic, explainable privacy proposals for SCRUM-99."""

from __future__ import annotations

import re
from typing import Any


RULE_VERSION = "document-privacy-v1"
LEVELS = ("low", "medium", "high")

HIGH_TERMS = {
    "api key", "apikey", "bsn", "credential", "diagnose", "diagnosis",
    "identiteitskaart", "identity card", "medisch", "medical", "paspoort",
    "passport", "password", "rijbewijs", "secret", "wachtwoord",
}
MEDIUM_TERMS = {
    "arbeidscontract", "bank", "belasting", "contract", "employment",
    "inkomen", "insurance", "loon", "polis", "salary", "salaris",
    "tax", "uitkering", "verzekering", "uwv",
}


def _evidence_text(row: dict[str, Any]) -> str:
    values = (
        row.get("filename"), row.get("path"), row.get("category"),
        row.get("document_family"), row.get("sensitivity"),
    )
    return " ".join(str(value or "") for value in values).casefold()


def _matched_terms(evidence: str, terms: set[str]) -> list[str]:
    return sorted(term for term in terms if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", evidence))


def propose_privacy(row: dict[str, Any]) -> dict[str, Any]:
    """Return a proposal only; this function never persists or lowers a review."""
    evidence = _evidence_text(row)
    high = _matched_terms(evidence, HIGH_TERMS)
    medium = _matched_terms(evidence, MEDIUM_TERMS)
    sensitivity = str(row.get("sensitivity") or "").casefold()

    if high or sensitivity == "highly_sensitive":
        level, confidence, reason = "high", "high", "high_impact_privacy_signal"
        signals = high or ["existing:highly_sensitive"]
    elif medium or sensitivity in {"personal", "sensitive"}:
        level, confidence, reason = "medium", "medium", "personal_or_financial_signal"
        signals = medium or [f"existing:{sensitivity}"]
    elif sensitivity == "normal":
        level, confidence, reason = "low", "medium", "existing_normal_classification"
        signals = ["existing:normal"]
    else:
        # Unknown is deliberately not silently classified as low.
        level, confidence, reason = "medium", "low", "insufficient_privacy_evidence"
        signals = []

    return {
        "classification": level,
        "confidence": confidence,
        "reason_code": reason,
        "rule_version": RULE_VERSION,
        "evidence": signals,
        "requires_human_review": True,
        "external_llm_content_allowed": level != "high",
    }
