"""Pure queue ordering and bounded selection for SCRUM-116."""
from __future__ import annotations

from typing import Iterable, Mapping, Any, Optional, Tuple
from pathlib import PurePosixPath

MAX_BATCH_SIZE = 50
ACTION_PRIORITY = {
    "quarantine_exact_duplicate": 10,
    "quarantine_content_similar": 20,
    "quarantine_deletion_review": 30,
    "migrate_active": 40,
    "migrate_inactive": 50,
}

SUCCESSFUL_ITEM_STATUSES = {"verified", "completed", "event_correlated"}
ACTIVE_BATCH_STATUSES = {"approved", "queued", "started", "paused", "rollback_pending"}


def flat_personal_correction(path: str) -> Optional[Tuple[str, str]]:
    """Return the safe corrective action/target for a file flat in a lifecycle zone."""
    source = PurePosixPath(str(path))
    for zone, action in (("Actief", "migrate_active"), ("Inactief", "migrate_inactive")):
        root = PurePosixPath("/volume1/data/Persoonlijk") / zone
        if source.parent == root:
            return action, str(root / "Te beoordelen" / source.name)
    return None


def build_flat_golden_correction(
    duplicate: Mapping[str, Any], metadata: Mapping[str, Any]
) -> Optional[dict]:
    """Build an executable correction even when the leader left the Workset projection."""
    correction = flat_personal_correction(str(duplicate["leader_path"]))
    if not correction:
        return None
    action_type, target_path = correction
    return {
        "file_id": int(duplicate["leader_file_id"]),
        "action_type": action_type,
        "source_path": str(duplicate["leader_path"]),
        "target_path": target_path,
        "content_sha256": metadata["content_sha256"],
        "size_bytes": metadata["size_bytes"],
        "reviewed_at": duplicate.get("reviewed_at"),
        "target_path_basis": "zone_fallback",
        "target_path_fallback_reason": "missing_taxonomy_subdirectory",
        "evidence_snapshot": {
            "kind": "flat_golden_record_correction",
            "duplicate_file_id": int(duplicate["file_id"]),
            "original_target_path": str(duplicate["leader_path"]),
            "target_path_fallback_reason": "missing_taxonomy_subdirectory",
        },
    }


def build_flat_file_correction(file_row: Mapping[str, Any]) -> Optional[dict]:
    """Build a controlled fallback move for every file flat below a lifecycle root."""
    source_path = str(file_row["source_path"])
    correction = flat_personal_correction(source_path)
    if not correction:
        return None
    action_type, target_path = correction
    return {
        "file_id": int(file_row["file_id"]),
        "action_type": action_type,
        "source_path": source_path,
        "target_path": target_path,
        "content_sha256": file_row["content_sha256"],
        "size_bytes": file_row["size_bytes"],
        "reviewed_at": file_row.get("location_changed_at") or file_row.get("updated_at"),
        "target_path_basis": "zone_fallback",
        "target_path_fallback_reason": "missing_taxonomy_subdirectory",
        "evidence_snapshot": {
            "kind": "flat_personal_root_correction",
            "original_target_path": source_path,
            "target_path_fallback_reason": "missing_taxonomy_subdirectory",
        },
    }


def normalize_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(candidate)
    action = str(item["action_type"])
    if action not in ACTION_PRIORITY:
        raise ValueError(f"unsupported action_type: {action}")
    item["file_id"] = int(item["file_id"])
    item["priority"] = ACTION_PRIORITY[action]
    item["source_path"] = str(item["source_path"])
    item["target_path"] = str(item["target_path"])
    reviewed_at = item.get("reviewed_at")
    item["reviewed_at"] = (
        reviewed_at.isoformat() if hasattr(reviewed_at, "isoformat")
        else "" if reviewed_at is None
        else str(reviewed_at)
    )
    if not item["source_path"].startswith("/volume1/data/") or not item["target_path"].startswith("/volume1/data/"):
        raise ValueError("execution path outside /volume1/data")
    if item["source_path"] == item["target_path"]:
        raise ValueError("source equals target")
    return item


def order_candidates(candidates: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[int, dict[str, Any]] = {}
    for candidate in candidates:
        item = normalize_candidate(candidate)
        current = unique.get(item["file_id"])
        if current is None or (item["priority"], item["target_path"]) < (current["priority"], current["target_path"]):
            unique[item["file_id"]] = item
    return sorted(unique.values(), key=lambda item: (
        item["priority"], item["reviewed_at"], item["target_path"].casefold(), item["file_id"]
    ))


def partition_candidates(candidates: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep invalid evidence visible without allowing it to disable the queue."""
    valid: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            valid.append(normalize_candidate(candidate))
        except (KeyError, TypeError, ValueError) as exc:
            blocked.append({**dict(candidate), "blocked_reason": str(exc)})
    ordered = order_candidates(valid)
    target_counts: dict[str, int] = {}
    for item in ordered:
        key = item["target_path"].casefold()
        target_counts[key] = target_counts.get(key, 0) + 1
    ready: list[dict[str, Any]] = []
    for item in ordered:
        if target_counts[item["target_path"].casefold()] > 1:
            blocked.append({**item, "blocked_reason": "batch_target_collision"})
        else:
            ready.append(item)
    return ready, blocked


def select_batch(candidates: Iterable[Mapping[str, Any]], limit: int = MAX_BATCH_SIZE) -> list[dict[str, Any]]:
    if not 1 <= limit <= MAX_BATCH_SIZE:
        raise ValueError(f"batch limit must be between 1 and {MAX_BATCH_SIZE}")
    return order_candidates(candidates)[:limit]


def exclude_already_controlled(
    candidates: Iterable[Mapping[str, Any]],
    controlled_items: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Suppress active work and already reached targets, not a file forever.

    A previously successful move to another target must remain eligible for a
    later corrective migration when policy now resolves a safer target.
    """
    active_file_ids: set[int] = set()
    completed_targets: set[tuple[int, str]] = set()
    for row in controlled_items:
        file_id = int(row["file_id"])
        if str(row.get("batch_status") or "") in ACTIVE_BATCH_STATUSES:
            active_file_ids.add(file_id)
        if str(row.get("current_status") or "") in SUCCESSFUL_ITEM_STATUSES:
            completed_targets.add((file_id, str(row.get("target_path") or "").casefold()))
    return [
        dict(candidate) for candidate in candidates
        if int(candidate["file_id"]) not in active_file_ids
        and (int(candidate["file_id"]), str(candidate["target_path"]).casefold()) not in completed_targets
    ]
