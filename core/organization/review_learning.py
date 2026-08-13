"""Read-only candidate-rule analysis over append-only human reviews."""

from __future__ import annotations

from collections import defaultdict
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
