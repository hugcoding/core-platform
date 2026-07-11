from __future__ import annotations

from typing import Any


def _field_name(value: dict[str, Any] | None) -> str:
    if not value:
        return ""
    return str(value.get("name") or value.get("displayName") or "")


def map_issue(issue: dict[str, Any]) -> dict[str, Any]:
    fields = issue.get("fields", {})
    parent = fields.get("parent") or {}
    assignee = fields.get("assignee") or {}
    return {
        "id": str(issue.get("id", "")),
        "key": str(issue.get("key", "")),
        "summary": str(fields.get("summary", "")),
        "issue_type": _field_name(fields.get("issuetype")),
        "status": _field_name(fields.get("status")),
        "priority": _field_name(fields.get("priority")),
        "assignee": str(assignee.get("displayName", "")) if assignee else "",
        "labels": list(fields.get("labels") or []),
        "parent_key": str(parent.get("key", "")) if parent else "",
        "created": str(fields.get("created", "")),
        "updated": str(fields.get("updated", "")),
    }


def map_search_results(payload: dict[str, Any]) -> dict[str, Any]:
    issues = [map_issue(issue) for issue in payload.get("issues", [])]
    return {
        "start_at": int(payload.get("startAt", 0)),
        "max_results": int(payload.get("maxResults", len(issues))),
        "total": int(payload.get("total", len(issues))),
        "issues": issues,
    }
