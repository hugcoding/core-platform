"""Deterministic golden-record scoring shared by batch and event processing."""

from __future__ import annotations

import re
from pathlib import PurePosixPath


ALGORITHM_VERSION = "golden-v3"
EXACT_MATCH_BASIS = "full_sha256_and_size"
SELECTION_QUALITY_SCOPE = "provenance_only"
LOW_VALUE_PATH_PARTS = {
    "cache", "temp", "tmp", "tijdelijk", "cloudstation", "backup",
    "backups", "archief", "archive", "export", "exports",
}


def score_candidate(row: dict) -> tuple[int, list[str]]:
    if int(row.get("size_bytes") or 0) <= 0:
        raise ValueError("Empty files are not eligible for golden-record selection")
    path = PurePosixPath(str(row["path"]))
    evidence = f"/{'/'.join(path.parts)}/".casefold()
    name = path.name.casefold()
    score = 100
    reasons = ["full SHA-256 available"]
    penalties = sorted(part for part in LOW_VALUE_PATH_PARTS if f"/{part}/" in evidence)
    if penalties:
        score -= 8 * len(penalties)
        reasons.append("legacy/path penalty: " + ", ".join(penalties))
    if re.search(r"(?:^|[\s_-])(kopie|copy|backup)(?:[\s_.()-]|$)", name):
        score -= 12
        reasons.append("copy-like filename penalty")
    if re.search(r"\(\d+\)(?=\.[^.]+$)", name):
        score -= 6
        reasons.append("numbered duplicate filename penalty")
    if name.startswith("~$") or name.endswith((".tmp", ".part")):
        score -= 30
        reasons.append("temporary filename penalty")
    return score, reasons


def rank_candidates(rows: list[dict]) -> list[dict]:
    ranked = []
    for row in rows:
        score, reasons = score_candidate(row)
        ranked.append(
            {
                **row,
                "selection_score": score,
                "selection_reasons": reasons,
                "eligibility_status": "eligible_nonempty_exact_content",
                "exact_match_basis": EXACT_MATCH_BASIS,
                "content_integrity_status": "stored_full_content_hash_evidence",
                "selection_quality_scope": SELECTION_QUALITY_SCOPE,
                "provenance_quality_score": score,
            }
        )
    ranked.sort(
        key=lambda row: (
            -row["selection_score"],
            len(str(row["path"])),
            str(row["path"]).casefold(),
            int(row["file_id"]),
        )
    )
    for rank, row in enumerate(ranked, start=1):
        row["selection_rank"] = rank
    return ranked


def selection_metadata(ranked: list[dict]) -> tuple[str, str, int]:
    if not ranked:
        raise ValueError("Cannot select a golden record from an empty group")
    best = ranked[0]["selection_score"]
    second = ranked[1]["selection_score"] if len(ranked) > 1 else None
    margin = best - second if second is not None else best
    if len(ranked) == 1:
        return "high", "single_source", margin
    if margin >= 8:
        return "high", "golden_selected", margin
    if margin > 0:
        return "medium", "golden_selected", margin
    return "low", "golden_selected_tiebreak", margin


def comparison_confidence(confidence: str, selection_status: str) -> str:
    """Separate singleton status from confidence between competing copies."""
    return "not_applicable" if selection_status == "single_source" else confidence
