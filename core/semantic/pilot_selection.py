from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any


SUPPORTED_EXTENSIONS = {"pdf", "docx"}
SENSITIVE_TERMS = {
    "belasting", "bank", "salaris", "loon", "factuur", "financien", "financiën",
    "paspoort", "rijbewijs", "identiteit", "bsn", "medisch", "gezondheid",
    "diagnose", "wmo", "sollicitatie", "arbeidscontract", "personeel",
    "password", "wachtwoord", "secret", "secrets", "credential", "credentials",
}


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def sensitivity_reason(path: str) -> str | None:
    parts = [part.casefold() for part in PurePosixPath(path).parts]
    searchable = " ".join(parts)
    for term in sorted(SENSITIVE_TERMS):
        if term.casefold() in searchable:
            return f"sensitive_path_term:{term}"
    return None


def select_candidates(
    rows: list[dict[str, Any]], *, cutoff: datetime, limit: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    ordered = sorted(
        rows,
        key=lambda row: (
            -parse_timestamp(str(row["modified_at_fs"])).timestamp()
            if row.get("modified_at_fs") else float("inf"),
            str(row.get("path", "")).casefold(),
            int(row["file_id"]),
        ),
    )
    seen_groups: set[str] = set()
    for row in ordered:
        reason = None
        extension = str(row.get("extension") or "").lower().lstrip(".")
        modified = parse_timestamp(str(row["modified_at_fs"])) if row.get("modified_at_fs") else None
        group_id = str(row.get("content_group_id") or "")
        if int(row.get("size_bytes") or 0) <= 0:
            reason = "empty_file"
        elif not row.get("content_sha256"):
            reason = "missing_full_sha256"
        elif not group_id or str(row.get("golden_file_id")) != str(row.get("file_id")):
            reason = "not_persisted_golden"
        elif extension not in SUPPORTED_EXTENSIONS:
            reason = "unsupported_extension"
        elif modified is None:
            reason = "missing_filesystem_modification_time"
        elif modified < cutoff:
            reason = "outside_recent_window"
        elif (sensitive := sensitivity_reason(str(row.get("path") or ""))):
            reason = sensitive
        elif group_id in seen_groups:
            reason = "duplicate_content_group"
        elif len(selected) >= limit:
            reason = "pilot_limit"

        if reason:
            excluded.append({**row, "selection_status": "excluded", "selection_reason": reason})
            continue
        seen_groups.add(group_id)
        selected.append({**row, "selection_status": "selected", "selection_reason": "recent_onedrive_golden"})
    return selected, excluded


def build_manifest(
    selected: list[dict[str, Any]], *, source: str, cutoff: datetime, generated_at: datetime
) -> dict[str, Any]:
    return {
        "schema_version": "semantic-pilot-manifest-v2",
        "selection_version": "onedrive-golden-v1",
        "generated_at": generated_at.astimezone(timezone.utc).isoformat(),
        "source": source,
        "cutoff": cutoff.astimezone(timezone.utc).isoformat(),
        "processing": "local_only",
        "embedding_enabled": False,
        "external_ai_enabled": False,
        "database_writes_enabled": False,
        "files": [
            {
                "file_id": int(row["file_id"]),
                "content_group_id": str(row["content_group_id"]),
                "content_sha256": str(row["content_sha256"]),
                "size_bytes": int(row["size_bytes"]),
                "modified_at_fs": str(row["modified_at_fs"]),
                "path": str(row["path"]),
                "approval": "approved",
                "selection_reason": "recent_onedrive_golden",
            }
            for row in selected
        ],
    }
