from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any


RULE_VERSION = "temporal-canonical-selection-v2-impact"
CREDIBLE_SOURCES = {
    "office_core_properties",
    "pdf_info_dictionary",
    "pdf_xmp",
}
CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}
SOURCE_RANK = {
    "pdf_xmp": 2,
    "pdf_info_dictionary": 3,
    "office_core_properties": 4,
}


def parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _candidate(row: dict[str, Any], *, as_of: datetime) -> dict[str, Any]:
    value_at = parse_timestamp(row.get("evidence_value_at"))
    local_value = parse_timestamp(row.get("evidence_local_value"))
    comparison_at = value_at or local_value
    excluded_reason = ""
    if str(row.get("evidence_source_type") or "") not in CREDIBLE_SOURCES:
        excluded_reason = "unsupported_or_technical_source"
    elif str(row.get("evidence_date_type") or "") not in {"created", "modified"}:
        excluded_reason = "unsupported_date_semantics"
    elif comparison_at is None:
        excluded_reason = "invalid_timestamp"
    elif comparison_at > as_of + timedelta(hours=24):
        excluded_reason = "future_timestamp"
    elif (comparison_at.month, comparison_at.day) == (1, 1) and comparison_at.year in {1900, 1970}:
        excluded_reason = "known_placeholder_timestamp"
    return {
        "evidence_id": str(row.get("evidence_id") or ""),
        "date_type": str(row.get("evidence_date_type") or ""),
        "source_type": str(row.get("evidence_source_type") or ""),
        "confidence": str(row.get("evidence_confidence") or "low"),
        "timezone_status": str(row.get("evidence_timezone_status") or ""),
        "raw_value": str(row.get("evidence_raw_value") or ""),
        "value_at": value_at.isoformat() if value_at else "",
        "local_value": str(row.get("evidence_local_value") or ""),
        "comparison_at": comparison_at,
        "excluded_reason": excluded_reason,
    }


def _select(candidates: list[dict[str, Any]], date_type: str) -> dict[str, Any] | None:
    eligible = [
        row for row in candidates
        if row["date_type"] == date_type and not row["excluded_reason"]
    ]
    if not eligible:
        return None

    def rank(row: dict[str, Any]) -> tuple[Any, ...]:
        confidence = CONFIDENCE_RANK.get(row["confidence"], 0)
        source = SOURCE_RANK.get(row["source_type"], 0)
        timestamp = row["comparison_at"].timestamp()
        if date_type == "created":
            return (timestamp, -confidence, -source, row["evidence_id"])
        return (-timestamp, -confidence, -source, row["evidence_id"])

    return sorted(eligible, key=rank)[0]


def _display_timestamp(candidate: dict[str, Any] | None) -> str:
    if candidate is None:
        return ""
    return candidate["value_at"] or candidate["local_value"]


def assess_file(
    rows: list[dict[str, Any]], *, as_of: datetime, activity_window_months: int,
) -> dict[str, Any]:
    base = rows[0]
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        evidence_id = str(row.get("evidence_id") or "")
        if evidence_id:
            evidence_by_id[evidence_id] = _candidate(row, as_of=as_of)
    candidates = list(evidence_by_id.values())
    credible = [row for row in candidates if not row["excluded_reason"]]
    excluded = [row for row in candidates if row["excluded_reason"]]
    created = _select(candidates, "created")
    modified = _select(candidates, "modified")
    created_values = [
        row["comparison_at"] for row in credible if row["date_type"] == "created"
    ]
    modified_values = [
        row["comparison_at"] for row in credible if row["date_type"] == "modified"
    ]
    chronology_issue = bool(
        created and modified and created["comparison_at"] > modified["comparison_at"]
    )

    from core.workset.active_workset import subtract_months

    cutoff = subtract_months(as_of, activity_window_months)
    filesystem_modified = parse_timestamp(base.get("filesystem_modified_at"))
    fixed_recent = bool(filesystem_modified and cutoff <= filesystem_modified <= as_of)
    temporal_values = [row["comparison_at"] for row in credible]
    has_before = any(value < cutoff for value in temporal_values)
    has_within = any(cutoff <= value <= as_of for value in temporal_values)
    material_conflict = str(base.get("created_has_conflict") or "").lower() in {
        "t", "true", "1",
    } or str(base.get("modified_has_conflict") or "").lower() in {"t", "true", "1"}
    decision_sensitive = material_conflict and not fixed_recent and has_before and has_within
    if material_conflict:
        conflict_effect = (
            "decision_sensitive_temporal_conflict"
            if decision_sensitive else "decision_invariant_temporal_conflict"
        )
    else:
        conflict_effect = "none"

    activity_candidates = [
        value for value in (
            modified["comparison_at"] if modified else None,
            created["comparison_at"] if created else None,
            filesystem_modified,
        ) if value is not None and value <= as_of
    ]
    canonical_activity = max(activity_candidates) if activity_candidates else None
    if chronology_issue:
        v2_status = "needs_review"
        v2_reason = "created_after_modified"
    elif decision_sensitive:
        v2_status = "needs_review"
        v2_reason = "decision_sensitive_temporal_conflict"
    elif canonical_activity is None:
        v2_status = "needs_review"
        v2_reason = "insufficient_credible_evidence"
    elif canonical_activity >= cutoff:
        v2_status = "active"
        v2_reason = "canonical_activity_within_configured_window"
    else:
        v2_status = "inactive"
        v2_reason = (
            "inactive_despite_material_temporal_conflict"
            if material_conflict else "canonical_activity_outside_configured_window"
        )

    v1_created = str(base.get("v1_created_at") or "")
    v1_modified = str(base.get("v1_modified_at") or "")
    v2_created = _display_timestamp(created)
    v2_modified = _display_timestamp(modified)
    v1_created_comparison = parse_timestamp(v1_created)
    v1_modified_comparison = parse_timestamp(v1_modified)
    created_changed = (
        (created["comparison_at"] if created else None) != v1_created_comparison
    )
    modified_changed = (
        (modified["comparison_at"] if modified else None) != v1_modified_comparison
    )
    return {
        "schema_version": "temporal-canonical-impact-v1",
        "selection_rule_version": RULE_VERSION,
        "file_id": int(base["file_id"]),
        "content_group_id": str(base.get("content_group_id") or ""),
        "filename": str(base.get("filename") or ""),
        "extension": str(base.get("extension") or ""),
        "path": str(base.get("path") or ""),
        "v1_created_at": v1_created,
        "v2_canonical_created_at": v2_created,
        "created_changed": created_changed,
        "created_evidence_id": created["evidence_id"] if created else "",
        "created_source_type": created["source_type"] if created else "",
        "created_confidence": created["confidence"] if created else "",
        "created_timezone_status": created["timezone_status"] if created else "",
        "created_selection_reason": (
            "earliest_credible_document_created" if created else "insufficient_credible_evidence"
        ),
        "earliest_observed_created_at": min(created_values).isoformat() if created_values else "",
        "latest_observed_created_at": max(created_values).isoformat() if created_values else "",
        "v1_modified_at": v1_modified,
        "v2_canonical_modified_at": v2_modified,
        "modified_changed": modified_changed,
        "modified_evidence_id": modified["evidence_id"] if modified else "",
        "modified_source_type": modified["source_type"] if modified else "",
        "modified_confidence": modified["confidence"] if modified else "",
        "modified_timezone_status": modified["timezone_status"] if modified else "",
        "modified_selection_reason": (
            "latest_credible_document_modified" if modified else "insufficient_credible_evidence"
        ),
        "earliest_observed_modified_at": min(modified_values).isoformat() if modified_values else "",
        "latest_observed_modified_at": max(modified_values).isoformat() if modified_values else "",
        "credible_evidence_count": len(credible),
        "credible_evidence_ids": ",".join(sorted(row["evidence_id"] for row in credible)),
        "excluded_evidence_count": len(excluded),
        "excluded_evidence": ",".join(sorted(
            f"{row['evidence_id']}:{row['excluded_reason']}" for row in excluded
        )),
        "material_temporal_conflict": material_conflict,
        "lifecycle_conflict_effect": conflict_effect,
        "chronology_issue": "created_after_modified" if chronology_issue else "",
        "v1_workset_status": str(base.get("v1_workset_status") or ""),
        "v2_workset_status": v2_status,
        "lifecycle_changed": str(base.get("v1_workset_status") or "") != v2_status,
        "v2_lifecycle_reason": v2_reason,
        "canonical_activity_at": canonical_activity.isoformat() if canonical_activity else "",
        "activity_cutoff_at": cutoff.isoformat(),
        "activity_window_months": activity_window_months,
        "policy_version": str(base.get("policy_version") or ""),
        "policy_checksum": str(base.get("policy_checksum") or ""),
        "database_writes": False,
        "file_mutations": False,
    }


def assess_rows(
    rows: list[dict[str, Any]], *, as_of: datetime, limit: int | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["file_id"]), []).append(row)
    file_ids = sorted(grouped)
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        file_ids = file_ids[:limit]
    return [
        assess_file(
            grouped[file_id], as_of=as_of,
            activity_window_months=int(grouped[file_id][0]["activity_window_months"]),
        )
        for file_id in file_ids
    ]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    v1 = Counter(row["v1_workset_status"] for row in rows)
    v2 = Counter(row["v2_workset_status"] for row in rows)
    return {
        "documents": len(rows),
        "created_changed": sum(bool(row["created_changed"]) for row in rows),
        "modified_changed": sum(bool(row["modified_changed"]) for row in rows),
        "lifecycle_changed": sum(bool(row["lifecycle_changed"]) for row in rows),
        "material_conflicts": sum(bool(row["material_temporal_conflict"]) for row in rows),
        "decision_invariant_conflicts": sum(
            row["lifecycle_conflict_effect"] == "decision_invariant_temporal_conflict"
            for row in rows
        ),
        "decision_sensitive_conflicts": sum(
            row["lifecycle_conflict_effect"] == "decision_sensitive_temporal_conflict"
            for row in rows
        ),
        "chronology_issues": sum(bool(row["chronology_issue"]) for row in rows),
        "excluded_evidence": sum(int(row["excluded_evidence_count"]) for row in rows),
        "v1_statuses": dict(sorted(v1.items())),
        "v2_statuses": dict(sorted(v2.items())),
    }
