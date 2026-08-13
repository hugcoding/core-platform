"""Read-only candidate-rule analysis over append-only human reviews."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import PurePosixPath
from typing import Any

from core.organization.path_normalization import normalize_target_path
from core.organization.target_path import CATEGORY_LABELS, FAMILY_LABELS


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


def analyze_proposal_quality(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assess category, family and target-path proposals using latest human reviews."""
    latest_by_file: dict[int, dict[str, Any]] = {}
    for row in rows:
        if row.get("review_type") != "target_path":
            continue
        try:
            latest_by_file[int(row["file_id"])] = row
        except (KeyError, TypeError, ValueError):
            continue

    dimensions = (
        ("category", "proposal_category_code", "corrected_category_code"),
        ("document_family", "proposal_document_family_code", "corrected_document_family_code"),
        ("target_path", "proposal_target_path", "proposed_target_path"),
    )
    assessments = []
    for dimension, proposal_field, human_field in dimensions:
        examples = [row for row in latest_by_file.values() if str(row.get(proposal_field) or "")]
        accepted = [row for row in examples if row.get("decision") == "accepted"]
        rejected = [row for row in examples if row.get("decision") == "rejected"]
        passed = [row for row in examples if row.get("decision") in {"needs_review", "passed"}]
        unchanged, corrected, counterexamples = 0, 0, []
        for row in accepted:
            proposal = str(row.get(proposal_field) or "")
            human = str(row.get(human_field) or "")
            if dimension == "target_path" and human:
                filename = str(row.get("filename") or "")
                try:
                    proposal = str(normalize_target_path(proposal, filename=filename)["normalized"])
                    human = str(normalize_target_path(human, filename=filename)["normalized"])
                except ValueError:
                    # Invalid input remains a visible disagreement/counterexample.
                    pass
            agrees = not human or (
                human.casefold() == proposal.casefold() if dimension == "target_path" else human == proposal
            )
            if agrees:
                unchanged += 1
            else:
                corrected += 1
                if len(counterexamples) < 5:
                    counterexamples.append({
                        "file_id": int(row["file_id"]), "filename": str(row.get("filename") or ""),
                        "proposal": proposal, "human_value": human,
                    })
        for row in rejected:
            if len(counterexamples) < 5:
                counterexamples.append({
                    "file_id": int(row["file_id"]), "filename": str(row.get("filename") or ""),
                    "proposal": str(row.get(proposal_field) or ""), "human_value": "rejected",
                })
        judged = len(accepted) + len(rejected)
        agreement = unchanged / judged if judged else 0.0
        assessments.append({
            "dimension": dimension, "reviewed_proposals": len(examples),
            "judged_proposals": judged, "accepted_unchanged": unchanged,
            "accepted_corrected": corrected, "rejected": len(rejected),
            "deferred_or_passed": len(passed), "agreement": round(agreement, 4),
            "counterexample_count": corrected + len(rejected),
            "counterexamples": counterexamples, "mode": "read_only",
        })
    return assessments


def _audit_path(
    *, file_id: int, filename: str, path: str, source_type: str,
    category_code: str, family_code: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    try:
        normalized = normalize_target_path(path, filename=filename)
    except ValueError as exc:
        return {
            "file_id": file_id, "filename": filename, "source_type": source_type,
            "path": path, "normalized_path": "", "status": "invalid",
            "reason_codes": [f"invalid_managed_path:{exc}"],
        }
    target = str(normalized["normalized"])
    parts = list(PurePosixPath(target).parts)
    folded_parts = [part.casefold() for part in parts]
    if normalized["changed"]:
        reasons.extend(str(item) for item in normalized["reason_codes"])
    if PurePosixPath(target).name.casefold() != filename.casefold():
        reasons.append("filename_changed_or_mismatched")
    if any(part in {"algemeen", "general"} for part in folded_parts[:-1]):
        reasons.append("generic_path_layer_present")
    category_label = CATEGORY_LABELS.get(category_code)
    if category_label and category_code != "needs_review" and category_label.casefold() not in folded_parts:
        reasons.append("category_layer_mismatch")
    family_label = FAMILY_LABELS.get(family_code)
    canonical_family_labels = {label.casefold(): code for code, label in FAMILY_LABELS.items() if code != "general"}
    foreign_families = sorted({
        canonical_family_labels[part] for part in folded_parts
        if part in canonical_family_labels and canonical_family_labels[part] != family_code
    })
    if foreign_families:
        reasons.append("conflicting_family_layer:" + ",".join(foreign_families))
    elif family_label and family_code != "general" and family_label.casefold() not in folded_parts:
        reasons.append("family_layer_omitted")
    material = [reason for reason in reasons if reason not in {
        "duplicate_separator_collapsed", "filename_appended_to_destination_directory",
        "family_layer_omitted",
    }]
    return {
        "file_id": file_id, "filename": filename, "source_type": source_type,
        "path": path, "normalized_path": target,
        "status": "needs_review" if material else "pass",
        "reason_codes": reasons or ["canonical_path_structure_consistent"],
    }


def audit_review_paths(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Audit CORE and latest human paths without treating human input as truth."""
    latest_by_file: dict[int, dict[str, Any]] = {}
    for row in rows:
        if row.get("review_type") != "target_path":
            continue
        try:
            latest_by_file[int(row["file_id"])] = row
        except (KeyError, TypeError, ValueError):
            continue
    audits = []
    for file_id, row in latest_by_file.items():
        filename = str(row.get("filename") or "")
        category = str(row.get("corrected_category_code") or row.get("proposal_category_code") or "")
        family = str(row.get("corrected_document_family_code") or row.get("proposal_document_family_code") or "")
        system_path = str(row.get("proposal_target_path") or "")
        if system_path:
            audits.append(_audit_path(
                file_id=file_id, filename=filename, path=system_path, source_type="core_proposal",
                category_code=category, family_code=family,
            ))
        human_path = str(row.get("proposed_target_path") or "")
        if human_path:
            audits.append(_audit_path(
                file_id=file_id, filename=filename, path=human_path, source_type="human_proposal",
                category_code=category, family_code=family,
            ))
    return sorted(audits, key=lambda item: (item["status"] == "pass", item["source_type"], item["file_id"]))
