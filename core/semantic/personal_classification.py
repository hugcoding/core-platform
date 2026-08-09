from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from core.semantic.pilot_selection import parse_timestamp, size_bucket


SCHEMA_VERSION = "personal-golden-classification-v2"
SELECTION_VERSION = "personal-onedrive-golden-v1"
PROMPT_VERSION = "scrum-85-personal-classification-v2"
SUPPORTED_EXTENSIONS = {"pdf", "docx"}
CATEGORIES = {"personal", "administration", "finance", "home", "work", "study", "projects", "other"}
LIFECYCLES = {"active_candidate", "archive_candidate", "needs_review", "quarantine"}
SENSITIVITY = {"normal", "personal", "sensitive", "highly_sensitive"}
SENSITIVITY_SIGNALS = {
    "identity", "government_identifier", "financial", "health", "employment",
    "education", "relationship", "address", "none",
}
TARGET_ROOTS = {
    "active_candidate": "Active", "archive_candidate": "Archive",
    "needs_review": "Review", "quarantine": "Quarantine",
}
SELECTION_ORDER = ("administration", "finance", "home", "work", "study", "projects", "personal")
CATEGORY_PATHS = {
    "personal": "Personal", "administration": "Administration", "finance": "Finance",
    "home": "Home", "work": "Work", "study": "Study", "projects": "Projects",
    "other": "Other",
}
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
SENSITIVITY_ORDER = {"normal": 0, "personal": 1, "sensitive": 2, "highly_sensitive": 3}


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


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return normalized[:80] or "unclassified"


def _safe_filename(value: str, file_id: int) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", PurePosixPath(value).name).strip(" .")
    return sanitized or f"file_{file_id}"


def canonical_category(document_type: str, family: str, topics: list[str], proposed: str) -> str:
    evidence = " ".join([document_type, family, *topics]).casefold()
    if any(term in evidence for term in ("belasting", "income_tax", "factuur", "invoice", "financial")):
        return "finance"
    if any(term in evidence for term in ("curriculum", "cv", "vacature", "interview", "sollicit", "career")):
        return "work"
    if any(term in evidence for term in ("diploma", "certificate", "certificaat", "education")):
        return "study"
    if any(term in evidence for term in ("vve", "riolering", "woning", "building", "maintenance")):
        return "home"
    return proposed


def canonical_family(document_type: str, family: str, topics: list[str]) -> str:
    evidence = " ".join([document_type, family, *topics]).casefold()
    mappings = (
        (("riolering", "memo"), "vve_technical_memos"),
        (("interview",), "interview_preparation"),
        (("vacaturekrant",), "vacancy_publications"),
        (("vacature_publicatie",), "vacancy_publications"),
        (("newsletter", "vacature"), "vacancy_publications"),
        (("vacaturetekst",), "vacancies"),
        (("curriculum",), "curriculum_vitae"),
        (("cv_",), "curriculum_vitae"),
        (("motivatie",), "motivation_letters"),
        (("belastingaangifte",), "income_tax"),
        (("belastingaanslag",), "income_tax"),
        (("invoice",), "invoices"),
        (("factuur",), "invoices"),
        (("diploma",), "diplomas"),
        (("certificate",), "certificates"),
        (("reglement",), "vve_regulations"),
        (("werkbon",), "maintenance_work_orders"),
        (("werkplan", "uwv"), "uwv_work_plans"),
        (("government_form",), "government_forms"),
        (("gemeentelijk",), "government_forms"),
    )
    for required, result in mappings:
        if all(term in evidence for term in required):
            return result
    return _slug(family)


def sensitivity_floor(category: str, evidence: str, signals: set[str]) -> str:
    if signals.intersection({"identity", "government_identifier", "health"}) or any(
        term in evidence for term in ("paspoort", "bsn", "diagnose", "medisch")
    ):
        return "highly_sensitive"
    if "financial" in signals or category == "finance" or any(
        term in evidence for term in ("belasting", "inkomen", "salaris", "uwv")
    ):
        return "sensitive"
    if signals.difference({"none"}) or any(
        term in evidence for term in ("curriculum", "cv", "diploma", "persoonlijke brief")
    ):
        return "personal"
    return "normal"


def _maximum_sensitivity(proposed: str, floor: str) -> str:
    return max((proposed, floor), key=lambda item: SENSITIVITY_ORDER[item])


def _cap_confidence(proposed: str, cap: str) -> str:
    return min((proposed, cap), key=lambda item: CONFIDENCE_ORDER[item])


def deterministic_path(lifecycle: str, category: str, family: str, filename: str, file_id: int) -> str:
    return "/".join((
        TARGET_ROOTS[lifecycle], CATEGORY_PATHS[category], family,
        _safe_filename(filename, file_id),
    ))


def validate_classification(content: str, file_id: int, filename: str = "document") -> dict[str, Any]:
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
    signals = value.get("sensitivity_signals")
    if not all(isinstance(item, str) and item.strip() for item in (document_type, family, reason)):
        return review_result(file_id, "missing_required_text")
    if not isinstance(topics, list) or len(topics) > 5 or not all(isinstance(item, str) for item in topics):
        return review_result(file_id, "invalid_topics")
    if not isinstance(signals, list) or not signals or not set(signals).issubset(SENSITIVITY_SIGNALS):
        return review_result(file_id, "invalid_sensitivity_signals")
    if "none" in signals and len(set(signals)) > 1:
        return review_result(file_id, "conflicting_sensitivity_signals")
    normalized_topics = [item.strip() for item in topics if item.strip()]
    normalized_category = canonical_category(document_type, family, normalized_topics, category)
    normalized_family = canonical_family(document_type, family, normalized_topics)
    evidence = " ".join([filename, document_type, family, reason, *normalized_topics]).casefold()
    normalized_sensitivity = _maximum_sensitivity(
        sensitivity, sensitivity_floor(normalized_category, evidence, set(signals)),
    )
    warnings = []
    if normalized_category != category:
        warnings.append(f"category_normalized:{category}->{normalized_category}")
    if normalized_family != _slug(family):
        warnings.append(f"family_normalized:{_slug(family)}->{normalized_family}")
    if normalized_sensitivity != sensitivity:
        warnings.append(f"sensitivity_raised:{sensitivity}->{normalized_sensitivity}")
    confidence_cap = "low" if normalized_category == "other" or normalized_family == "unknown" else "medium" if warnings or lifecycle == "needs_review" else "high"
    normalized_confidence = _cap_confidence(confidence, confidence_cap)
    if normalized_confidence != confidence:
        warnings.append(f"confidence_capped:{confidence}->{normalized_confidence}")
    path = deterministic_path(
        lifecycle, normalized_category, normalized_family, filename, file_id,
    )
    return {
        "file_id": file_id, "status": "classified", "document_type": document_type.strip(),
        "model_category": category, "category": normalized_category,
        "model_document_family": family.strip(), "document_family": normalized_family,
        "topics": normalized_topics, "lifecycle": lifecycle,
        "suggested_path": path, "model_sensitivity": sensitivity,
        "sensitivity": normalized_sensitivity, "sensitivity_signals": signals,
        "model_confidence": confidence, "confidence": normalized_confidence,
        "normalization_warnings": warnings,
        "reason": reason.strip(), "needs_review": True,
    }


def review_result(file_id: int, reason: str) -> dict[str, Any]:
    return {
        "file_id": file_id, "status": "needs_review", "document_type": "unknown",
        "category": "other", "document_family": "unknown", "topics": [],
        "lifecycle": "needs_review", "suggested_path": "Review/Unclassified",
        "sensitivity": "personal", "confidence": "low", "reason": reason,
        "model_category": "other", "model_document_family": "unknown",
        "model_sensitivity": "personal", "sensitivity_signals": [],
        "model_confidence": "low", "normalization_warnings": [], "needs_review": True,
    }
