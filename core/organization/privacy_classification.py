"""Deterministic, explainable privacy proposals for SCRUM-99."""

from __future__ import annotations

import re
from typing import Any


RULE_VERSION = "document-privacy-v4"
LEVELS = ("low", "medium", "high")

HIGH_TERMS = {
    "api key",
    "apikey",
    "bsn",
    "burgerservicenummer",
    "credential",
    "diagnose",
    "diagnosis",
    "iban",
    "identiteitskaart",
    "identity card",
    "medisch",
    "medical",
    "paspoort",
    "passport",
    "password",
    "rekeningnummer",
    "bankrekeningnummer",
    "rijbewijs",
    "secret",
    "wachtwoord",
}

MEDIUM_TERMS = {
    "arbeidscontract",
    "bank",
    "belasting",
    "contract",
    "employment",
    "inkomen",
    "insurance",
    "loon",
    "polis",
    "salary",
    "salaris",
    "tax",
    "uitkering",
    "verzekering",
    "uwv",
}

PERSONAL_IDENTITY_TERMS = {
    "naam",
    "adres",
    "postcode",
    "woonplaats",
    "geboortedatum",
}

SENSITIVE_FINANCIAL_TERMS = {
    "hypotheeknummer",
    "leningdeel",
    "hypotheek",
    "rente",
    "inkomen",
    "salaris",
    "uitkering",
    "jaaroverzicht",
}

IBAN_PATTERN = re.compile(
    r"\bNL\d{2}[A-Z]{4}\d{10}\b",
    re.IGNORECASE,
)

BSN_LABEL_PATTERN = re.compile(
    r"\b(?:bsn|burgerservicenummer)\b.{0,30}\b\d{9}\b",
    re.IGNORECASE,
)

DUTCH_POSTCODE_PATTERN = re.compile(
    r"\b\d{4}\s?[A-Z]{2}\b",
    re.IGNORECASE,
)

PERSON_SALUTATION_PATTERN = re.compile(
    r"\b(?:de heer|mevrouw|dhr\.?|mw\.?)\b",
    re.IGNORECASE,
)


def _evidence_text(row: dict[str, Any]) -> str:
    values = (
        row.get("filename"),
        row.get("path"),
        row.get("category"),
        row.get("document_family"),
        row.get("sensitivity"),
    )
    return " ".join(str(value or "") for value in values).casefold()


def _content_text(row: dict[str, Any]) -> str:
    values = (
        row.get("extracted_text"),
        row.get("document_text"),
        row.get("content_text"),
    )
    return " ".join(str(value or "") for value in values).casefold()


def _matched_terms(evidence: str, terms: set[str]) -> list[str]:
    return sorted(
        term
        for term in terms
        if re.search(
            rf"(?<!\w){re.escape(term)}(?!\w)",
            evidence,
        )
    )


def _high_content_signals(row: dict[str, Any]) -> list[str]:
    text = _content_text(row)

    if not text:
        return []

    signals: list[str] = []

    # Expliciete identifiers
    if IBAN_PATTERN.search(text):
        signals.append("iban")

    if BSN_LABEL_PATTERN.search(text):
        signals.append("bsn")

    if "burgerservicenummer" in text:
        signals.append("burgerservicenummer")

    if "bankrekeningnummer" in text:
        signals.append("bankrekeningnummer")
    elif "rekeningnummer" in text:
        signals.append("rekeningnummer")

    if any(
        term in text
        for term in (
            "paspoortnummer",
            "identiteitsnummer",
            "rijbewijsnummer",
        )
    ):
        signals.append("identity_number")

    # Expliciete labels voor persoonsgegevens
    identity_hits = [
        term
        for term in PERSONAL_IDENTITY_TERMS
        if term in text
    ]

    # Financiële gegevens
    financial_hits = [
        term
        for term in SENSITIVE_FINANCIAL_TERMS
        if term in text
    ]

    # Persoonsgegevens via inhoud/patroon herkennen.
    # Bijvoorbeeld:
    # "De heer H.W. Hoogendoorn"
    # "2135 NJ Hoofddorp"
    has_postcode = bool(DUTCH_POSTCODE_PATTERN.search(text))
    has_person = bool(PERSON_SALUTATION_PATTERN.search(text))

    # Combinatie van meerdere expliciete persoonsgegevens
    # + financiële gegevens.
    if len(identity_hits) >= 2 and financial_hits:
        signals.append("personal_financial_data")

    # Of herkenbare persoon/adrescontext
    # + financiële gegevens.
    if financial_hits and (has_postcode or has_person):
        signals.append("personal_financial_data")

    return sorted(set(signals))

def propose_privacy(row: dict[str, Any]) -> dict[str, Any]:
    """Return a proposal only; this function never persists or lowers a review."""
    evidence = _evidence_text(row)
    high = _matched_terms(evidence, HIGH_TERMS)
    content_high = _high_content_signals(row)
    medium = _matched_terms(evidence, MEDIUM_TERMS)
    sensitivity = str(row.get("sensitivity") or "").casefold()

    if high or content_high or sensitivity == "highly_sensitive":
        level = "high"
        confidence = "high"
        reason = "high_impact_privacy_signal"
        signals = (
            high
            or content_high
            or ["existing:highly_sensitive"]
        )

    elif medium or sensitivity in {"personal", "sensitive"}:
        level = "medium"
        confidence = "medium"
        reason = "personal_or_financial_signal"
        signals = medium or [f"existing:{sensitivity}"]

    elif sensitivity == "normal":
        level = "low"
        confidence = "medium"
        reason = "existing_normal_classification"
        signals = ["existing:normal"]

    else:
        # Unknown is deliberately not silently classified as low.
        level = "medium"
        confidence = "low"
        reason = "insufficient_privacy_evidence"
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