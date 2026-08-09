from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from core.semantic.pilot_selection import parse_timestamp, size_bucket


SCHEMA_VERSION = "personal-golden-classification-v1"
SELECTION_VERSION = "personal-onedrive-golden-v1"
PROMPT_VERSION = "scrum-85-personal-classification-v1"
SUPPORTED_EXTENSIONS = {"pdf", "docx"}
CATEGORIES = {"personal", "administration", "finance", "home", "work", "study", "projects", "other"}
LIFECYCLES = {"active_candidate", "archive_candidate", "needs_review", "quarantine"}
SENSITIVITY = {"normal", "personal", "sensitive", "highly_sensitive"}
TARGET_ROOTS = {
    "active_candidate": "Active", "archive_candidate": "Archive",
    "needs_review": "Review", "quarantine": "Quarantine",
}
SELECTION_ORDER = ("administration", "finance", "home", "work", "study", "projects", "personal")


def selection_stratum(path: str) -> str:
    searchable = re.sub(r"[\W_]+", " ", path.casefold(), flags=re.UNICODE)
    terms = set(searchable.split())
    if terms.intersection({"belasting", "bank", "factuur", "financien", "inkomen", "salaris", "hypotheek"}):
        return "finance"
    if terms.intersection({"woning", "wonen", "huis", "vve", "riolering", "energie"}):
        return "home"
    if terms.intersection({"sollicitaties", "sollicitatie", "cv", "vacature", "werk", "loopbaan"}):
        return "work"
    if terms.intersection({"studie", "opleiding", "training", "school", "cursus"}):
        return "study"
    if terms.intersection({"project", "projecten", "projects"}):
        return "projects"
    if terms.intersection({"administratie", "verzekering", "overheid", "gemeente", "contract"}):
        return "administration"
    return "personal"


def select_personal_candidates(
    rows: list[dict[str, Any]], *, cutoff: datetime, limit: int = 25,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    eligible, excluded = [], []
    seen_groups: set[str] = set()
    ordered = sorted(rows, key=lambda row: (
        -parse_timestamp(str(row["modified_at_fs"])).timestamp()
        if row.get("modified_at_fs") else float("inf"),
        str(row.get("path", "")).casefold(), int(row["file_id"]),
    ))
    for row in ordered:
        path = str(row.get("path") or "")
        extension = str(row.get("extension") or "").lower().lstrip(".")
        modified = parse_timestamp(str(row["modified_at_fs"])) if row.get("modified_at_fs") else None
        group_id = str(row.get("content_group_id") or "")
        reason = None
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
        elif PurePosixPath(path).stem.casefold() in {"key", "password", "passwords", "wachtwoorden"}:
            reason = "secret_candidate"
        elif group_id in seen_groups:
            reason = "duplicate_content_group"
        stratum = selection_stratum(path)
        enriched = {**row, "selection_stratum": stratum}
        if reason:
            excluded.append({**enriched, "selection_status": "excluded", "selection_reason": reason})
            continue
        seen_groups.add(group_id)
        eligible.append({
            **enriched, "selection_size_bucket": size_bucket(int(row["size_bytes"])),
        })

    keys = [
        (stratum, extension, bucket)
        for stratum in SELECTION_ORDER
        for extension in sorted(SUPPORTED_EXTENSIONS)
        for bucket in ("small", "medium", "large")
    ]
    buckets = {key: [row for row in eligible if (
        row["selection_stratum"], str(row["extension"]).lower().lstrip("."),
        row["selection_size_bucket"],
    ) == key] for key in keys}
    selected = []
    while len(selected) < limit and any(buckets.values()):
        for key in keys:
            if buckets[key] and len(selected) < limit:
                selected.append({
                    **buckets[key].pop(0), "selection_status": "selected",
                    "selection_reason": "representative_recent_personal_golden",
                })
    for key in keys:
        excluded.extend({
            **row, "selection_status": "excluded", "selection_reason": "pilot_limit",
        } for row in buckets[key])
    return selected, excluded


def build_manifest(selected: list[dict[str, Any]], *, source: str, cutoff: datetime) -> dict[str, Any]:
    return {
        "schema_version": "personal-classification-manifest-v1",
        "selection_version": SELECTION_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source, "cutoff": cutoff.astimezone(timezone.utc).isoformat(),
        "processing": "local_only", "database_writes_enabled": False,
        "file_mutations_enabled": False, "external_ai_enabled": False,
        "files": [{
            "file_id": int(row["file_id"]), "content_group_id": str(row["content_group_id"]),
            "content_sha256": str(row["content_sha256"]), "path": str(row["path"]),
            "filename": str(row["filename"]), "extension": str(row["extension"]),
            "size_bytes": int(row["size_bytes"]), "modified_at_fs": str(row["modified_at_fs"]),
            "selection_stratum": row["selection_stratum"],
            "selection_size_bucket": row["selection_size_bucket"],
            "approval": "pending_review",
        } for row in selected],
    }


def approved_manifest(manifest: dict[str, Any], current_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if manifest.get("schema_version") != "personal-classification-manifest-v1":
        raise ValueError("unsupported personal classification manifest")
    if manifest.get("processing") != "local_only":
        raise ValueError("manifest must require local_only processing")
    for flag in ("database_writes_enabled", "file_mutations_enabled", "external_ai_enabled"):
        if manifest.get(flag) is not False:
            raise ValueError(f"manifest must keep {flag}=false")
    files = manifest.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= 25:
        raise ValueError("manifest must contain between 1 and 25 selected files")
    ids = [int(item["file_id"]) for item in files]
    if len(ids) != len(set(ids)):
        raise ValueError("manifest contains duplicate file IDs")
    approvals = {str(item.get("approval") or "") for item in files}
    if not approvals.issubset({"approved", "excluded", "pending_review"}):
        raise ValueError("approval must be approved, excluded, or pending_review")
    if "pending_review" in approvals:
        raise ValueError("manifest review is incomplete; resolve every pending_review")
    approved = [item for item in files if item["approval"] == "approved"]
    if not approved:
        raise ValueError("manifest must approve at least one file")

    current = {int(row["file_id"]): row for row in current_rows}
    for item in approved:
        row = current.get(int(item["file_id"]))
        if row is None:
            raise ValueError(f"approved file_id={item['file_id']} is no longer an active golden record")
        comparisons = (
            ("content_group_id", str), ("content_sha256", str), ("path", str),
        )
        for field, cast in comparisons:
            if cast(row.get(field) or "") != cast(item.get(field) or ""):
                raise ValueError(f"approved file_id={item['file_id']} changed field {field}")
        if str(row.get("golden_file_id")) != str(item["file_id"]):
            raise ValueError(f"approved file_id={item['file_id']} is no longer golden")
    return {**manifest, "files": approved}


def build_classification_prompt(document: dict[str, Any], system_prompt: str) -> tuple[str, str]:
    chunks = "\n\n".join(
        f"CHUNK {chunk['ordinal']}:\n{chunk['text']}" for chunk in document["chunks"]
    )
    user = (
        f"prompt_version: {PROMPT_VERSION}\nfile_id: {document['file_id']}\n"
        f"filename: {document['filename']}\nmodified_at_fs: {document['modified_at_fs']}\n"
        f"selection_stratum_hint: {document['selection_stratum']}\n\nCONTENT:\n{chunks}"
    )
    return system_prompt, user


def validate_classification(content: str, file_id: int) -> dict[str, Any]:
    try:
        value = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return review_result(file_id, "provider_response_not_valid_json")
    try:
        returned_file_id = int(value.get("file_id") or 0) if isinstance(value, dict) else 0
    except (TypeError, ValueError):
        returned_file_id = 0
    if not isinstance(value, dict) or returned_file_id != file_id:
        return review_result(file_id, "file_id_mismatch")
    category, lifecycle = value.get("category"), value.get("lifecycle")
    confidence, sensitivity = value.get("confidence"), value.get("sensitivity")
    if category not in CATEGORIES:
        return review_result(file_id, "invalid_category")
    if lifecycle not in LIFECYCLES:
        return review_result(file_id, "invalid_lifecycle")
    if confidence not in {"low", "medium", "high"} or sensitivity not in SENSITIVITY:
        return review_result(file_id, "invalid_confidence_or_sensitivity")
    document_type = value.get("document_type")
    family = value.get("document_family")
    reason = value.get("reason")
    topics = value.get("topics")
    if not all(isinstance(item, str) and item.strip() for item in (document_type, family, reason)):
        return review_result(file_id, "missing_required_text")
    if not isinstance(topics, list) or len(topics) > 5 or not all(isinstance(item, str) for item in topics):
        return review_result(file_id, "invalid_topics")
    path = str(value.get("suggested_path") or "").replace("\\", "/").strip("/")
    parts = PurePosixPath(path).parts
    if not path or ".." in parts or parts[0] != TARGET_ROOTS[lifecycle]:
        return review_result(file_id, "invalid_suggested_path")
    return {
        "file_id": file_id, "status": "classified", "document_type": document_type.strip(),
        "category": category, "document_family": family.strip(),
        "topics": [item.strip() for item in topics if item.strip()], "lifecycle": lifecycle,
        "suggested_path": path, "sensitivity": sensitivity, "confidence": confidence,
        "reason": reason.strip(), "needs_review": True,
    }


def review_result(file_id: int, reason: str) -> dict[str, Any]:
    return {
        "file_id": file_id, "status": "needs_review", "document_type": "unknown",
        "category": "other", "document_family": "unknown", "topics": [],
        "lifecycle": "needs_review", "suggested_path": "Review/Unclassified",
        "sensitivity": "personal", "confidence": "low", "reason": reason,
        "needs_review": True,
    }
