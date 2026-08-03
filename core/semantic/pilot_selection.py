from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
import re
from typing import Any


SUPPORTED_EXTENSIONS = {"pdf", "docx"}
SENSITIVE_TERMS = {
    "secrets": {"password", "wachtwoord", "secret", "secrets", "credential", "credentials"},
    "identity": {"paspoort", "rijbewijs", "identiteit", "identiteitsbewijs", "bsn", "inschrijving"},
    "finance": {"belasting", "bank", "salaris", "loon", "factuur", "financien", "financiën", "inkomen", "offerte", "uwv"},
    "health": {"medisch", "gezondheid", "diagnose", "wmo", "zorgverzekering"},
    "employment": {"sollicitatie", "arbeidscontract", "contractvoorstel", "werkgeversverklaring", "vacature", "cv"},
    "personal": {"ticket", "ticketorder", "relatie"},
}
SENSITIVE_PHRASES = {
    "employment": {"employer s certificate", "curriculum vitae", "werkplan ww"},
    "personal": {"gezamenlijke documenten inkomen", "ticketorder"},
}
CATEGORY_ORDER = ("study", "work", "project", "administration", "general")
SIZE_BUCKET_ORDER = ("small", "medium", "large")


def parse_timestamp(value: str) -> datetime:
    normalized = value.strip()
    try:
        epoch_seconds = float(normalized)
    except ValueError:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    else:
        parsed = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def sensitivity_reason(path: str) -> str | None:
    searchable = re.sub(r"[\W_]+", " ", path.casefold(), flags=re.UNICODE).strip()
    tokens = set(searchable.split())
    filename = PurePosixPath(path).stem.casefold()
    if filename == "key":
        return "sensitive_path_category:secrets"
    for category, terms in SENSITIVE_TERMS.items():
        if tokens.intersection(term.casefold() for term in terms):
            return f"sensitive_path_category:{category}"
    for category, phrases in SENSITIVE_PHRASES.items():
        if any(phrase.casefold() in searchable for phrase in phrases):
            return f"sensitive_path_category:{category}"
    return None


def pilot_category(path: str) -> str:
    parts = {part.casefold() for part in PurePosixPath(path).parts}
    searchable = "/".join(parts)
    if parts.intersection({"studie", "opleiding", "training"}) or "datacamp" in parts:
        return "study"
    if parts.intersection({"projecten", "projects"}) or "project" in searchable:
        return "project"
    if "werk" in parts:
        return "work"
    if parts.intersection({"administratie", "administration", "vve"}):
        return "administration"
    return "general"


def size_bucket(size_bytes: int) -> str:
    if size_bytes < 256 * 1024:
        return "small"
    if size_bytes < 2 * 1024 * 1024:
        return "medium"
    return "large"


def select_candidates(
    rows: list[dict[str, Any]], *, cutoff: datetime, limit: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    eligible: list[dict[str, Any]] = []
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
        category = pilot_category(str(row.get("path") or ""))
        if extension not in SUPPORTED_EXTENSIONS:
            reason = "unsupported_extension"
        elif int(row.get("size_bytes") or 0) <= 0:
            reason = "empty_file"
        elif not row.get("content_sha256"):
            reason = "missing_full_sha256"
        elif not group_id or str(row.get("golden_file_id")) != str(row.get("file_id")):
            reason = "not_persisted_golden"
        elif modified is None:
            reason = "missing_filesystem_modification_time"
        elif modified < cutoff:
            reason = "outside_recent_window"
        elif (sensitive := sensitivity_reason(str(row.get("path") or ""))):
            reason = sensitive
        elif group_id in seen_groups:
            reason = "duplicate_content_group"

        if reason:
            excluded.append({**row, "pilot_category": category, "selection_status": "excluded", "selection_reason": reason})
            continue
        seen_groups.add(group_id)
        eligible.append({
            **row,
            "pilot_category": category,
            "pilot_size_bucket": size_bucket(int(row["size_bytes"])),
        })

    bucket_keys = [
        (category, extension, bucket)
        for category in CATEGORY_ORDER
        for extension in sorted(SUPPORTED_EXTENSIONS)
        for bucket in SIZE_BUCKET_ORDER
    ]
    buckets = {
        key: [
            row for row in eligible
            if (row["pilot_category"], str(row["extension"]).lower().lstrip("."), row["pilot_size_bucket"]) == key
        ]
        for key in bucket_keys
    }
    selected: list[dict[str, Any]] = []
    while len(selected) < limit and any(buckets.values()):
        for key in bucket_keys:
            if buckets[key] and len(selected) < limit:
                selected.append({**buckets[key].pop(0), "selection_status": "selected", "selection_reason": "representative_recent_onedrive_golden"})
    for key in bucket_keys:
        excluded.extend(
            {**row, "selection_status": "excluded", "selection_reason": "pilot_limit"}
            for row in buckets[key]
        )
    return selected, excluded


def build_manifest(
    selected: list[dict[str, Any]], *, source: str, cutoff: datetime, generated_at: datetime
) -> dict[str, Any]:
    return {
        "schema_version": "semantic-pilot-manifest-v3",
        "selection_version": "onedrive-golden-representative-v2",
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
                "pilot_category": str(row["pilot_category"]),
                "pilot_size_bucket": str(row["pilot_size_bucket"]),
                "selection_reason": "representative_recent_onedrive_golden",
            }
            for row in selected
        ],
    }
