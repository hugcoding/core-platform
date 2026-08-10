from __future__ import annotations

import calendar
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any


POLICY_SCHEMA_VERSION = "active-workset-policy-v1"
RESULT_SCHEMA_VERSION = "active-workset-result-v2"
REQUIRED_EXTENSIONS = {"docx", "xlsx"}


def parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromtimestamp(int(text), tz=timezone.utc)
    except (ValueError, TypeError, OSError, OverflowError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def subtract_months(value: datetime, months: int) -> datetime:
    month_index = value.year * 12 + value.month - 1 - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def validate_policy(policy: dict[str, Any]) -> dict[str, Any]:
    if policy.get("schema_version") != POLICY_SCHEMA_VERSION:
        raise ValueError("unsupported active-workset policy schema")
    source = str(policy.get("source") or "").rstrip("/")
    if not source.startswith("/volume1/") or source == "/volume1/data":
        raise ValueError("policy source must be a scoped path below /volume1")
    extensions = {str(value).lower().lstrip(".") for value in policy.get("extensions", [])}
    if extensions != REQUIRED_EXTENSIONS:
        raise ValueError("active-workset-v1 pilot requires exactly docx and xlsx")
    months = int(policy.get("activity_window_months") or 0)
    if not 1 <= months <= 24:
        raise ValueError("activity_window_months must be between 1 and 24")
    review = policy.get("review_selection") or {}
    for key in ("active_per_extension", "outside_near_cutoff", "duplicate_groups"):
        if int(review.get(key, -1)) < 0:
            raise ValueError(f"review_selection.{key} must be zero or greater")
    if int(review.get("temporal_conflicts", 20)) < 0:
        raise ValueError("review_selection.temporal_conflicts must be zero or greater")
    return {
        **policy,
        "source": source,
        "extensions": sorted(extensions),
        "activity_window_months": months,
        "review_selection": {
            **{key: int(review[key]) for key in (
                "active_per_extension", "outside_near_cutoff", "duplicate_groups"
            )},
            "temporal_conflicts": int(review.get("temporal_conflicts", 20)),
        },
    }


def _integer(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "t", "true", "yes"}


def _confidence(value: object, default: str = "low") -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in {"low", "medium", "high"} else default


def evaluate_rows(
    rows: list[dict[str, Any]], *, policy: dict[str, Any], as_of: datetime,
) -> list[dict[str, Any]]:
    policy = validate_policy(policy)
    as_of = as_of.astimezone(timezone.utc)
    cutoff = subtract_months(as_of, policy["activity_window_months"])
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ungrouped: list[dict[str, Any]] = []
    for row in rows:
        group_id = str(row.get("content_group_id") or "")
        (groups[group_id] if group_id else ungrouped).append(row)

    evaluated: list[dict[str, Any]] = []
    for group_id, members in sorted(groups.items()):
        def modified_sort_value(row: dict[str, Any]) -> float:
            parsed = parse_timestamp(row.get("modified_at_fs"))
            return -parsed.timestamp() if parsed else float("inf")

        ordered = sorted(members, key=lambda row: (
            modified_sort_value(row),
            str(row.get("source_path") or "").casefold(),
            _integer(row.get("source_file_id")),
        ))
        signal = ordered[0]
        evaluated.append(_evaluate(signal, ordered, cutoff, as_of, policy))
    for row in sorted(ungrouped, key=lambda item: str(item.get("source_path") or "").casefold()):
        evaluated.append(_evaluate(row, [row], cutoff, as_of, policy))
    return sorted(evaluated, key=lambda row: (
        {"active_candidate": 0, "needs_review": 1, "inactive": 2}.get(row["workset_status"], 9),
        row["extension"], row["source_path"].casefold(), row["source_file_id"],
    ))


def _evaluate(
    row: dict[str, Any], members: list[dict[str, Any]], cutoff: datetime,
    as_of: datetime, policy: dict[str, Any],
) -> dict[str, Any]:
    modified = parse_timestamp(row.get("modified_at_fs"))
    source_created = parse_timestamp(row.get("temporal_source_created_at"))
    source_modified = parse_timestamp(row.get("temporal_source_modified_at"))
    size_bytes = _integer(row.get("size_bytes"))
    full_hash = str(row.get("content_sha256") or "")
    group_id = str(row.get("content_group_id") or "")
    golden_id = _integer(row.get("golden_file_id"))
    created_conflict = _boolean(row.get("created_has_conflict"))
    modified_conflict = _boolean(row.get("modified_has_conflict"))
    reason = ""
    confidence = "low"
    within: bool | None = None
    signals = [
        (source_modified, "source_metadata_modified", _confidence(row.get("modified_confidence"))),
        (source_created, "source_metadata_created", _confidence(row.get("created_confidence"))),
        (modified, "filesystem_mtime", "low"),
    ]
    valid_signals = [signal for signal in signals if signal[0] is not None]
    activity_at, activity_source, activity_confidence = max(
        valid_signals, key=lambda signal: signal[0]
    ) if valid_signals else (None, "none", "low")
    if size_bytes <= 0:
        status, reason = "needs_review", "empty_file"
    elif not full_hash:
        status, reason = "needs_review", "missing_full_content_hash"
    elif not group_id or not golden_id:
        status, reason = "needs_review", "missing_persisted_golden_record"
    elif created_conflict or modified_conflict:
        status, reason = "needs_review", "conflicting_temporal_evidence"
    elif activity_at is None or activity_at > as_of:
        status, reason = "needs_review", "invalid_or_missing_activity_timestamp"
    elif activity_at >= cutoff:
        status, reason, within = "active_candidate", f"{activity_source}_within_configured_window", True
        confidence = activity_confidence
    else:
        status, reason, within = "inactive", "no_qualifying_activity_within_configured_window", False
        confidence = activity_confidence
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "policy_version": str(policy["policy_version"]),
        "candidate_file_id": golden_id or "",
        "source_file_id": _integer(row.get("source_file_id")),
        "golden_file_id": golden_id or "",
        "content_group_id": group_id,
        "content_sha256": full_hash,
        "source_path": str(row.get("source_path") or ""),
        "golden_path": str(row.get("golden_path") or ""),
        "filename": str(row.get("golden_filename") or row.get("filename") or ""),
        "extension": str(row.get("golden_extension") or row.get("extension") or "").lower(),
        "size_bytes": _integer(row.get("golden_size_bytes") or size_bytes),
        "source_copy_count": len(members),
        "duplicate_represented_by_golden": len(members) > 1 or (
            bool(golden_id) and golden_id != _integer(row.get("source_file_id"))
        ),
        "core_first_observed_at": str(row.get("core_created_at") or ""),
        "source_modified_at": modified.isoformat() if modified else "",
        "temporal_source_created_at": source_created.isoformat() if source_created else "",
        "temporal_created_confidence": _confidence(row.get("created_confidence"), ""),
        "temporal_created_source_type": str(row.get("created_source_type") or ""),
        "temporal_source_modified_at": source_modified.isoformat() if source_modified else "",
        "temporal_modified_confidence": _confidence(row.get("modified_confidence"), ""),
        "temporal_modified_source_type": str(row.get("modified_source_type") or ""),
        "temporal_evidence_count": _integer(row.get("evidence_count")),
        "created_has_conflict": created_conflict,
        "modified_has_conflict": modified_conflict,
        "activity_at": activity_at.isoformat() if activity_at else "",
        "activity_basis_source": activity_source,
        "within_activity_window": "" if within is None else within,
        "activity_window_months": policy["activity_window_months"],
        "workset_status": status,
        "reason": reason,
        "confidence": confidence,
        "missing_evidence": ",".join(
            name for name, present in (
                ("source_created_at", source_created is not None),
                ("source_modified_at", source_modified is not None),
                ("content_changed_at", False),
                ("last_human_activity_at", False),
            ) if not present
        ),
        "database_writes": False,
        "file_mutations": False,
    }


def select_review(rows: list[dict[str, Any]], policy: dict[str, Any]) -> list[dict[str, Any]]:
    policy = validate_policy(policy)
    limits = policy["review_selection"]
    chosen: dict[int, dict[str, Any]] = {}

    def add(row: dict[str, Any], reason: str) -> None:
        file_id = int(row["source_file_id"])
        if file_id in chosen:
            existing = str(chosen[file_id]["review_reason"])
            if reason not in existing.split(","):
                chosen[file_id]["review_reason"] = f"{existing},{reason}"
        else:
            chosen[file_id] = {**row, "review_reason": reason}

    for extension in policy["extensions"]:
        active = [row for row in rows if row["extension"] == extension and row["workset_status"] == "active_candidate"]
        for row in active[:limits["active_per_extension"]]:
            add(row, "active_sample")

    inactive = sorted(
        (row for row in rows if row["workset_status"] == "inactive"),
        key=lambda row: row["activity_at"], reverse=True,
    )
    for row in inactive[:limits["outside_near_cutoff"]]:
        add(row, "outside_near_cutoff")

    duplicates = [row for row in rows if row["duplicate_represented_by_golden"]]
    for row in duplicates[:limits["duplicate_groups"]]:
        add(row, "duplicate_group")

    conflicts = [row for row in rows if row["reason"] == "conflicting_temporal_evidence"]
    for row in conflicts[:limits["temporal_conflicts"]]:
        add(row, "temporal_conflict")
    return list(chosen.values())


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(row["workset_status"] for row in rows)
    extensions = Counter(row["extension"] for row in rows)
    return {
        "content_groups": len(rows),
        "active_candidates": statuses["active_candidate"],
        "inactive": statuses["inactive"],
        "needs_review": statuses["needs_review"],
        "duplicate_groups": sum(bool(row["duplicate_represented_by_golden"]) for row in rows),
        "by_extension": dict(sorted(extensions.items())),
    }
