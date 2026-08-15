"""Deterministic, proposal-only trajectory learning from accepted target paths."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any


MINIMUM_SUPPORT = 3
TEMPORARY_COMPONENTS = {
    "uitzoeken", "nieuw", "tijdelijk", "temp", "algemeen", "general",
    "ongesorteerd", "inbox", "te beoordelen",
}
NON_TRAJECTORY_COMPONENTS = TEMPORARY_COMPONENTS | {
    "cv", "cvs", "curriculum vitae", "motivatiebrief", "motivatiebrieven",
    "vacature", "vacatures", "gespreksvoorbereiding", "ondersteunende analyses",
}
APPLICATION_MARKERS = {"sollicitaties", "cv sollicitaties", "cv en sollicitaties"}


def normalized_term(value: str) -> str:
    return " ".join(token for token in re.split(r"[^a-z0-9]+", value.casefold()) if token)


def trajectory_parts_from_target(path: str, filename: str) -> list[str]:
    parts = list(PurePosixPath(path.replace("\\", "/")).parts)
    folded = [normalized_term(part) for part in parts]
    marker = next((index for index, part in enumerate(folded) if part in APPLICATION_MARKERS), None)
    if marker is None or marker + 1 >= len(parts):
        return []
    candidates = []
    for candidate in parts[marker + 1:-1]:
        candidate = candidate.strip()
        if not candidate or normalized_term(candidate) in NON_TRAJECTORY_COMPONENTS:
            continue
        if candidate.casefold() == filename.casefold():
            continue
        candidates.append(candidate)
    return candidates[:2]


def trajectory_from_target(path: str, filename: str) -> str | None:
    parts = trajectory_parts_from_target(path, filename)
    return " / ".join(parts) if parts else None


def contains_term(evidence: str, term: str) -> bool:
    return f" {term} " in f" {evidence} "


def build_trajectory_rules(
    rows: list[dict[str, Any]], minimum_support: int = MINIMUM_SUPPORT,
) -> list[dict[str, Any]]:
    if minimum_support < 1:
        raise ValueError("trajectory rules require at least one example")
    latest: dict[int, dict[str, Any]] = {}
    for row in rows:
        latest[int(row["file_id"])] = row
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    labels: dict[str, str] = {}
    hierarchy_labels: dict[str, list[str]] = {}
    match_terms: dict[str, str] = {}
    trajectories: dict[int, str] = {}
    for file_id, row in latest.items():
        if row.get("decision") != "accepted" or not row.get("proposed_target_path"):
            continue
        hierarchy = trajectory_parts_from_target(
            str(row["proposed_target_path"]), str(row.get("filename") or ""),
        )
        if not hierarchy:
            continue
        hierarchy_key = " / ".join(normalized_term(part) for part in hierarchy)
        if not hierarchy_key:
            continue
        evidence = normalized_term(f"{row.get('filename', '')} {row.get('path', '')}")
        match_term = next(
            (normalized_term(part) for part in reversed(hierarchy)
             if contains_term(evidence, normalized_term(part))),
            None,
        )
        if not match_term:
            continue
        labels.setdefault(hierarchy_key, " / ".join(hierarchy))
        hierarchy_labels.setdefault(hierarchy_key, hierarchy)
        match_terms.setdefault(hierarchy_key, match_term)
        trajectories[file_id] = hierarchy_key
        groups[hierarchy_key].append(row)
    candidates = []
    for hierarchy_key, examples in groups.items():
        term = match_terms[hierarchy_key]
        counterexamples = []
        for file_id, row in latest.items():
            evidence = normalized_term(f"{row.get('filename', '')} {row.get('path', '')}")
            if (contains_term(evidence, term)
                    and trajectories.get(file_id) not in {None, hierarchy_key}):
                counterexamples.append({
                    "file_id": file_id,
                    "target_trajectory": labels.get(trajectories[file_id], trajectories[file_id]),
                })
        support = len(examples)
        agreement = support / (support + len(counterexamples))
        if support < minimum_support or counterexamples:
            continue
        repeated = support >= MINIMUM_SUPPORT
        candidates.append({
            "candidate_type": "application_trajectory_rule",
            "trajectory_code": re.sub(r"[^a-z0-9]+", "_", hierarchy_key).strip("_")[:80],
            "trajectory_label": labels[hierarchy_key],
            "trajectory_parts": hierarchy_labels[hierarchy_key],
            "match_term": term,
            "support": support,
            "agreement": round(agreement, 4),
            "counterexample_count": len(counterexamples),
            "counterexamples": counterexamples[:5],
            "example_file_ids": sorted(int(item["file_id"]) for item in examples)[:10],
            "source_review_event_ids": sorted(str(item["id"]) for item in examples)[:10],
            "confidence": "high" if repeated else "medium",
            "reason_codes": [
                "canonical_applications_context",
                ("repeated_accepted_human_target_path" if repeated
                 else "exact_context_term_from_accepted_human_target_path"),
                "temporary_source_layers_ignored",
            ],
            "activation_status": "proposal_only",
        })
    return sorted(candidates, key=lambda item: (-item["support"], item["trajectory_label"].casefold()))


def matching_trajectory_rule(
    document: dict[str, Any], rules: list[dict[str, Any]],
) -> dict[str, Any] | None:
    evidence = normalized_term(f"{document.get('filename', '')} {document.get('path', '')}")
    if "sollicit" not in evidence:
        return None
    matches = [rule for rule in rules if contains_term(evidence, str(rule["match_term"]))]
    return matches[0] if len(matches) == 1 else None
