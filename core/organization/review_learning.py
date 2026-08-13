"""Read-only candidate-rule analysis over append-only human reviews."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def analyze_reviews(rows: list[dict[str, Any]], minimum_support: int = 3) -> list[dict[str, Any]]:
    if minimum_support < 2:
        raise ValueError("minimum support must be at least 2")
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        category = str(row.get("corrected_category_code") or "")
        family = str(row.get("corrected_document_family_code") or "")
        source_family = str(row.get("proposal_document_family_code") or "")
        if row.get("decision") != "accepted" or not category or not family:
            continue
        groups[(source_family, category, family)].append(row)
    candidates = []
    for (source_family, category, family), examples in groups.items():
        if len(examples) < minimum_support:
            continue
        conflicting = len({str(item.get("proposed_target_path") or "") for item in examples if item.get("proposed_target_path")})
        confidence = "high" if len(examples) >= minimum_support * 2 and conflicting <= 1 else "medium"
        candidates.append({
            "candidate_type": "classification_correction_rule",
            "source_family_code": source_family,
            "target_category_code": category,
            "target_family_code": family,
            "support": len(examples),
            "confidence": confidence,
            "conflict_count": max(0, conflicting - 1),
            "example_file_ids": [int(item["file_id"]) for item in examples[:5]],
            "reason_codes": ["repeated_accepted_human_correction"],
            "activation_status": "candidate_only",
            "llm_context": {
                "evidence_type": "repeated_human_judgment",
                "instruction": (
                    f"When relevant, consider category {category} and family {family}; "
                    "this is advisory candidate evidence, not an active rule."
                ),
                "human_support": len(examples),
                "may_activate_rule": False,
            },
        })
    return sorted(candidates, key=lambda item: (-item["support"], item["target_category_code"], item["target_family_code"]))


def _privacy_pattern(row: dict[str, Any]) -> tuple[str, str, str]:
    evidence = row.get("privacy_evidence") or []
    if isinstance(evidence, str):
        evidence = [item.strip().strip('"') for item in evidence.strip("{}").split(",") if item.strip()]
    signal = "+".join(sorted(str(item) for item in evidence)) or "no_specific_signal"
    return (
        str(row.get("proposal_reason_code") or "unknown_reason"),
        signal,
        str(row.get("proposal_privacy_classification") or "unknown"),
    )


def analyze_privacy_reviews(
    rows: list[dict[str, Any]], minimum_support: int = 3,
) -> list[dict[str, Any]]:
    """Build inactive candidates from the latest human privacy judgment per file."""
    if minimum_support < 2:
        raise ValueError("minimum support must be at least 2")
    latest_by_file: dict[int, dict[str, Any]] = {}
    for row in rows:
        if row.get("review_type") != "privacy_classification":
            continue
        try:
            file_id = int(row["file_id"])
        except (KeyError, TypeError, ValueError):
            continue
        # Input is chronological. Replacing retains only the latest append-only judgment.
        latest_by_file[file_id] = row

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in latest_by_file.values():
        corrected = str(row.get("corrected_privacy_classification") or "")
        if row.get("decision") != "accepted" or corrected not in {"low", "medium", "high"}:
            continue
        groups[_privacy_pattern(row)].append(row)

    candidates = []
    for (reason, signal, proposed), examples in groups.items():
        if len(examples) < minimum_support:
            continue
        votes = Counter(str(item["corrected_privacy_classification"]) for item in examples)
        target, agreement_count = sorted(votes.items(), key=lambda item: (-item[1], item[0]))[0]
        agreement = agreement_count / len(examples)
        counterexamples = [
            {
                "file_id": int(item["file_id"]),
                "human_classification": str(item["corrected_privacy_classification"]),
                "filename": str(item.get("filename") or ""),
            }
            for item in examples if str(item["corrected_privacy_classification"]) != target
        ][:5]
        confidence = "high" if agreement >= 0.9 and len(examples) >= minimum_support * 2 else "medium" if agreement >= 0.75 else "low"
        candidates.append({
            "candidate_type": "privacy_classification_rule",
            "pattern_reason_code": reason,
            "pattern_evidence": signal,
            "source_privacy_classification": proposed,
            "target_privacy_classification": target,
            "support": len(examples),
            "agreement_count": agreement_count,
            "agreement": round(agreement, 4),
            "confidence": confidence,
            "counterexample_count": len(examples) - agreement_count,
            "counterexamples": counterexamples,
            "example_file_ids": [int(item["file_id"]) for item in examples[:5]],
            "reason_codes": ["repeated_latest_human_privacy_judgment"],
            "activation_status": "candidate_only",
            "may_lower_high_automatically": False,
            "eligible_for_activation_review": agreement >= 0.75,
        })
    return sorted(candidates, key=lambda item: (-item["support"], -item["agreement"], item["pattern_evidence"]))
