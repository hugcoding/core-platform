"""Pure queue ordering and bounded selection for SCRUM-116."""
from __future__ import annotations

from typing import Iterable, Mapping, Any

MAX_BATCH_SIZE = 25
ACTION_PRIORITY = {
    "quarantine_exact_duplicate": 10,
    "quarantine_content_similar": 20,
    "quarantine_deletion_review": 30,
    "migrate_active": 40,
    "migrate_inactive": 50,
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
    return order_candidates(valid), blocked


def select_batch(candidates: Iterable[Mapping[str, Any]], limit: int = MAX_BATCH_SIZE) -> list[dict[str, Any]]:
    if not 1 <= limit <= MAX_BATCH_SIZE:
        raise ValueError("batch limit must be between 1 and 25")
    return order_candidates(candidates)[:limit]
