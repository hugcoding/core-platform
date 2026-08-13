"""Canonical Dutch target-path contract for SCRUM-96."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any

from core.organization.review_taxonomy import taxonomy


CONTRACT_VERSION = "canonical-dutch-target-path-v3"
TARGET_ROOT = "/volume1/data/Persoonlijk"
ZONE_LABELS = {
    "active": "Actief", "archive": "Archief",
    "needs_review": "Te beoordelen", "quarantine": "Quarantaine",
}
CATEGORY_LABELS = {
    "work_career": "Werk & Loopbaan",
    "home_living": "Wonen",
    "finance": "Geldzaken",
    "health": "Gezondheid",
    "family_relationships": "Gezin & Relaties",
    "learning_development": "Leren & Ontwikkelen",
    "identity_personal": "Persoonlijk & Identiteit",
    "legal": "Juridisch",
    "needs_review": "Te beoordelen",
}
CATEGORY_ALIASES = {
    "work": "work_career", "study": "learning_development",
    "home": "home_living", "personal": "identity_personal",
    "other": "needs_review", "administration": "needs_review",
}
KEYWORD_RULES = (
    ("work_career", ("sollicit", "vacature", "curriculum vitae", "cv", "werkgever", "arbeidscontract")),
    ("finance", ("belasting", "factuur", "bank", "salaris", "hypotheek", "inkomen")),
    ("home_living", ("woning", "vve", "huur", "energie", "riolering")),
    ("health", ("gezondheid", "medisch", "huisarts", "ziekenhuis", "zorgverzekering")),
    ("learning_development", ("opleiding", "studie", "cursus", "certificaat", "diploma")),
    ("legal", ("juridisch", "rechtbank", "bezwaar", "beroep", "advocaat")),
    ("identity_personal", ("paspoort", "identiteit", "geboorteakte", "rijbewijs")),
)
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
FAMILY_RULES = (
    ("vacancies", "Vacatures", ("vacature", "functieprofiel")),
    ("resumes", "CV's", ("curriculum vitae", "_cv_", " cv ")),
    ("motivation_letters", "Motivatiebrieven", ("motivatie", "sollicitatiebrief")),
    ("interview_preparation", "Gespreksvoorbereiding", ("gesprek", "voorbereiding", "pitch")),
    ("supporting_analysis", "Ondersteunende analyses", ("analyse", "advies", "feedback", "stress", "afwijzing")),
    ("certificates", "Certificaten", ("certificate", "certificaat", "diploma")),
)
FAMILY_LABELS = {code: label for code, label, _ in FAMILY_RULES}
FAMILY_LABELS.update({
    "course_data": "Cursusdata", "secrets": "Geheimen", "general": "Algemeen",
})
FAMILY_LABELS.update({item["code"]: item["label"] for item in taxonomy()["families"]})
SECRET_TERMS = ("wachtwoord", "password", "passwords", "credentials", "api key", "secret")


def contract_checksum() -> str:
    payload = {"version": CONTRACT_VERSION, "root": TARGET_ROOT, "zones": ZONE_LABELS,
               "categories": CATEGORY_LABELS, "rules": KEYWORD_RULES, "families": FAMILY_RULES,
               "family_labels": FAMILY_LABELS,
               "secret_terms": SECRET_TERMS}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def safe_component(value: str, *, fallback: str = "Bestand", max_length: int = 120) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"_+", "_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value:
        value = fallback
    stem = value.split(".", 1)[0].upper()
    if stem in RESERVED_NAMES:
        value = "_" + value
    if len(value) > max_length:
        suffix = PurePosixPath(value).suffix
        value = value[: max_length - len(suffix)].rstrip(" .") + suffix
    return value


def canonical_category(row: dict[str, Any]) -> tuple[str, str, str]:
    accepted = str(row.get("accepted_category") or "").strip().casefold()
    accepted = CATEGORY_ALIASES.get(accepted, accepted)
    if accepted in CATEGORY_LABELS and accepted != "needs_review":
        return accepted, "accepted_human_classification", "high"
    evidence = " ".join(str(row.get(key) or "") for key in
                        ("filename", "path", "accepted_document_family")).casefold()
    for code, terms in KEYWORD_RULES:
        if any(term in evidence for term in terms):
            return code, "deterministic_keyword_rule", "medium"
    return "needs_review", "insufficient_classification_evidence", "low"


def _evidence(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(key) or "") for key in
                    ("filename", "path", "accepted_document_family")).casefold()


def is_secret_candidate(row: dict[str, Any]) -> bool:
    evidence = _evidence(row)
    return any(term in evidence for term in SECRET_TERMS)


def is_supporting_dataset(row: dict[str, Any]) -> bool:
    path = str(row.get("path") or "").replace("\\", "/").casefold()
    extension = str(row.get("extension") or "").casefold().lstrip(".")
    return extension == "xlsx" and "/notebook" in path and "/data/" in path


def document_family(row: dict[str, Any]) -> tuple[str, str]:
    accepted = str(row.get("accepted_document_family") or "").strip().casefold()
    if accepted in FAMILY_LABELS:
        return accepted, FAMILY_LABELS[accepted]
    evidence = " " + _evidence(row).replace("-", " ") + " "
    filename_stem = PurePosixPath(str(row.get("filename") or "")).stem.casefold()
    filename_tokens = {token for token in re.split(r"[^a-z0-9]+", filename_stem) if token}
    if "cv" in filename_tokens or "curriculum vitae" in evidence:
        return "resumes", FAMILY_LABELS["resumes"]
    for code, label, terms in FAMILY_RULES:
        if any(term in evidence for term in terms):
            return code, label
    if is_supporting_dataset(row):
        return "course_data", "Cursusdata"
    return "general", "Algemeen"


def application_trajectory(row: dict[str, Any]) -> tuple[str, str]:
    path = PurePosixPath(str(row.get("path") or "").replace("\\", "/"))
    directories = list(path.parts[:-1])
    marker = next((i for i, value in enumerate(directories)
                   if value.casefold() in {"cv & sollicitaties", "cv en sollicitaties"}), None)
    if marker is None:
        return "general_work", "Algemeen werk"
    context = directories[marker + 1:]
    if context and context[0].casefold() in {"ai-chat_history", "ai chat history"}:
        return "general_preparation", "Algemene voorbereiding"
    labels = [safe_component(value, fallback="") for value in context[:2] if value.strip()]
    if not labels:
        return "general_applications", "Algemene sollicitaties"
    label = " – ".join(labels)
    code = re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_") or "general_applications"
    return code[:80], label


def propose_target(row: dict[str, Any]) -> dict[str, Any]:
    category, reason, confidence = canonical_category(row)
    family_code, family = document_family(row)
    trajectory_code, trajectory_label = "", ""
    if is_secret_candidate(row):
        zone, category, reason, confidence = (
            "quarantine", "needs_review", "secret_candidate_requires_restricted_review", "high"
        )
        family_code, family = "secrets", "Geheimen"
    elif is_supporting_dataset(row):
        zone, category, reason, confidence = (
            "needs_review", "learning_development", "supporting_dataset_requires_review", "medium"
        )
    else:
        zone = "active" if category != "needs_review" else "needs_review"
    accepted_lifecycle = str(row.get("accepted_lifecycle") or "")
    if accepted_lifecycle in {"archive_candidate", "needs_review"}:
        zone, reason, confidence = "needs_review", "accepted_lifecycle_conflicts_with_active_workset", "high"
    elif accepted_lifecycle == "quarantine":
        zone, reason, confidence = "quarantine", "accepted_quarantine_classification", "high"
    filename = safe_component(str(row.get("filename") or ""), fallback=f"Bestand {row.get('file_id', '')}")
    parts = [TARGET_ROOT, ZONE_LABELS[zone]]
    path_reductions = []
    if zone == "quarantine":
        parts.append(family)
    elif category != "needs_review":
        parts.append(CATEGORY_LABELS[category])
        if category == "work_career" and "sollicit" in _evidence(row):
            trajectory_code, trajectory_label = application_trajectory(row)
            parts.append("Sollicitaties")
            generic_trajectory = trajectory_code in {
                "general_work", "general_preparation", "general_applications", "algemeen", "general"
            } or trajectory_label.strip().casefold() in {
                "algemeen", "algemeen werk", "algemene sollicitaties", "general"
            }
            if not generic_trajectory:
                parts.append(trajectory_label)
            else:
                path_reductions.append("generic_trajectory_omitted")
            if family_code != "general":
                parts.append(family)
            else:
                path_reductions.append("generic_family_omitted")
        else:
            if family_code != "general":
                parts.append(family)
            else:
                path_reductions.append("generic_family_omitted")
    parts.append(filename)
    return {
        **row, "contract_version": CONTRACT_VERSION, "contract_checksum": contract_checksum(),
        "zone_code": zone, "zone_label": ZONE_LABELS[zone],
        "category_code": category, "category_label": CATEGORY_LABELS[category],
        "trajectory_code": trajectory_code, "trajectory_label": trajectory_label,
        "document_family_code": family_code, "folder_label": family,
        "suggested_target_path": str(PurePosixPath(*parts)),
        "proposal_reason_code": reason, "proposal_confidence": confidence,
        "path_reduction_reason_codes": path_reductions,
        "database_writes": False, "file_mutations": False,
    }


def select_representative(rows: list[dict[str, Any]], limit: int = 50) -> list[dict[str, Any]]:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    ordered = sorted(rows, key=lambda row: (
        str(row.get("extension") or ""),
        str(row.get("last_qualifying_activity_at") or ""),
        str(row.get("path") or "").casefold(), int(row["file_id"]),
    ), reverse=True)
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in ordered:
        buckets.setdefault(str(row.get("extension") or "unknown"), []).append(row)
    selected: list[dict[str, Any]] = []
    while len(selected) < limit and any(buckets.values()):
        for extension in sorted(buckets):
            if buckets[extension] and len(selected) < limit:
                selected.append(buckets[extension].pop(0))
    return selected


def mark_collisions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row["suggested_target_path"]).casefold()
        counts[key] = counts.get(key, 0) + 1
    return [{**row, "collision_status": (
        "batch_target_collision" if counts[str(row["suggested_target_path"]).casefold()] > 1 else "none"
    )} for row in rows]
