"""Canonical Dutch target-path contract for SCRUM-96."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any


CONTRACT_VERSION = "canonical-dutch-target-path-v1"
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


def contract_checksum() -> str:
    payload = {"version": CONTRACT_VERSION, "root": TARGET_ROOT, "zones": ZONE_LABELS,
               "categories": CATEGORY_LABELS, "rules": KEYWORD_RULES}
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


def propose_target(row: dict[str, Any]) -> dict[str, Any]:
    category, reason, confidence = canonical_category(row)
    zone = "active" if category != "needs_review" else "needs_review"
    family = safe_component(str(row.get("accepted_document_family") or ""), fallback="Algemeen")
    filename = safe_component(str(row.get("filename") or ""), fallback=f"Bestand {row.get('file_id', '')}")
    parts = [TARGET_ROOT, ZONE_LABELS[zone]]
    if zone == "active":
        parts.extend((CATEGORY_LABELS[category], family))
    parts.append(filename)
    return {
        **row, "contract_version": CONTRACT_VERSION, "contract_checksum": contract_checksum(),
        "zone_code": zone, "zone_label": ZONE_LABELS[zone],
        "category_code": category, "category_label": CATEGORY_LABELS[category],
        "folder_label": family, "suggested_target_path": str(PurePosixPath(*parts)),
        "proposal_reason_code": reason, "proposal_confidence": confidence,
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
