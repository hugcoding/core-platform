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


def trajectory_from_target(path: str, filename: str) -> str | None:
    parts = list(PurePosixPath(path.replace("\\", "/")).parts)
    folded = [normalized_term(part) for part in parts]
    marker = next((index for index, part in enumerate(folded) if part in APPLICATION_MARKERS), None)
    if marker is None or marker + 1 >= len(parts):
        return None
    candidate = parts[marker + 1].strip()
    if (normalized_term(candidate) in NON_TRAJECTORY_COMPONENTS
            or candidate.casefold() == filename.casefold()):
        return None
    return candidate


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
    trajectories: dict[int, str] = {}
    for file_id, row in latest.items():
        if row.get("decision") != "accepted" or not row.get("proposed_target_path"):
            continue
        label = trajectory_from_target(
            str(row["proposed_target_path"]), str(row.get("filename") or ""),
        )
        if not label:
            continue
        term = normalized_term(label)
        if not term:
            continue
        evidence = normalized_term(f"{row.get('filename', '')} {row.get('path', '')}")
        if not contains_term(evidence, term):
            continue
        labels.setdefault(term, label)
        trajectories[file_id] = term
        groups[term].append(row)
    candidates = []
    for term, examples in groups.items():
        counterexamples = []
        for file_id, row in latest.items():
            evidence = normalized_term(f"{row.get('filename', '')} {row.get('path', '')}")
            if contains_term(evidence, term) and trajectories.get(file_id) not in {None, term}:
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
            "trajectory_code": re.sub(r"[^a-z0-9]+", "_", term).strip("_")[:80],
            "trajectory_label": labels[term],
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
