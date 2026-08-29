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
    if not item["source_path"].startswith("/volume1/data/") or not item["target_path"].startswith("/volume1/data/"):
        raise ValueError("execution path outside /volume1/data")
    if item["source_path"] == item["target_path"]:
        raise ValueError("source equals target")
    return item


def select_batch(candidates: Iterable[Mapping[str, Any]], limit: int = MAX_BATCH_SIZE) -> list[dict[str, Any]]:
    if not 1 <= limit <= MAX_BATCH_SIZE:
        raise ValueError("batch limit must be between 1 and 25")
    unique: dict[int, dict[str, Any]] = {}
    for candidate in candidates:
        item = normalize_candidate(candidate)
        current = unique.get(item["file_id"])
        if current is None or (item["priority"], item["target_path"]) < (current["priority"], current["target_path"]):
            unique[item["file_id"]] = item
    return sorted(unique.values(), key=lambda item: (
        item["priority"], item.get("reviewed_at") or "", item["target_path"].casefold(), item["file_id"]
    ))[:limit]
