"""Validated local-LLM proposals for explicitly selected workset documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.organization.review_taxonomy import taxonomy
from core.semantic.extraction import extract_document


SCHEMA_VERSION = "workset-llm-proposal-v1"
PROMPT_VERSION = "scrum-101-workset-llm-v1"
MAX_DOCUMENTS = 5
MAX_TEXT_CHARACTERS = 12_000
LIFECYCLES = {"active", "archive", "needs_review"}
PRIVACY = {"low", "medium", "high"}
RELATIONS = {"none", "source_document", "exported_representation", "version", "related_document"}


def extract_bounded_context(path: str) -> dict[str, Any]:
    text, pages = extract_document(Path(path))
    normalized = " ".join(text.split())
    if not normalized:
        return {"status": "needs_review", "reason": "no_extractable_text", "text": "", "pages": pages}
    truncated = len(normalized) > MAX_TEXT_CHARACTERS
    return {
        "status": "ready", "reason": "bounded_local_extraction", "pages": pages,
        "text": normalized[:MAX_TEXT_CHARACTERS], "characters": min(len(normalized), MAX_TEXT_CHARACTERS),
        "truncated": truncated,
    }


def build_prompt(document: dict[str, Any], context: dict[str, Any],
                 examples: list[dict[str, Any]], system_prompt: str) -> tuple[str, str]:
    contract = taxonomy()
    categories = ", ".join(item["code"] for item in contract["categories"])
    families = ", ".join(item["code"] for item in contract["families"])
    example_text = "\n".join(
        f"- {item['filename']} => category={item['category_code']}, family={item['family_code']}"
        for item in examples[:3]
    ) or "- geen passende bevestigde voorbeelden"
    user = f"""prompt_version: {PROMPT_VERSION}
file_id: {document['file_id']}
filename: {document['filename']}
source_path: {document['path']}
current_core_category: {document.get('core_category') or 'unknown'}
current_core_family: {document.get('core_family') or 'unknown'}
allowed_categories: {categories}
allowed_families: {families}

HUMAN_CONFIRMED_EXAMPLES:
{example_text}

DOCUMENT_TEXT:
{context['text']}
"""
    return system_prompt, user


def abstention(file_id: int, reason: str) -> dict[str, Any]:
    return {
        "file_id": file_id, "status": "abstained", "abstained": True,
        "category_code": None, "family_code": None, "lifecycle": "needs_review",
        "privacy_advice": None, "confidence": "low", "relation_kind": "none",
        "related_file_ids": [], "reason": reason,
    }


def validate_proposal(content: str, file_id: int) -> dict[str, Any]:
    try:
        value = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return abstention(file_id, "provider_response_not_valid_json")
    if not isinstance(value, dict) or int(value.get("file_id") or 0) != file_id:
        return abstention(file_id, "file_id_mismatch")
    if value.get("abstained") is True:
        return abstention(file_id, str(value.get("reason") or "model_abstained"))
    categories = {item["code"] for item in taxonomy()["categories"]}
    families = {item["code"] for item in taxonomy()["families"]}
    category, family = value.get("category_code"), value.get("family_code")
    lifecycle, privacy = value.get("lifecycle"), value.get("privacy_advice")
    confidence, relation = value.get("confidence"), value.get("relation_kind", "none")
    reason, related = value.get("reason"), value.get("related_file_ids", [])
    if category not in categories or family not in families:
        return abstention(file_id, "unknown_taxonomy_value")
    if lifecycle not in LIFECYCLES or privacy not in PRIVACY:
        return abstention(file_id, "invalid_lifecycle_or_privacy")
    if confidence not in {"low", "medium", "high"} or relation not in RELATIONS:
        return abstention(file_id, "invalid_confidence_or_relation")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 600:
        return abstention(file_id, "invalid_reason")
    if not isinstance(related, list) or len(related) > 5:
        return abstention(file_id, "invalid_related_files")
    try:
        related_ids = [int(item) for item in related]
    except (TypeError, ValueError):
        return abstention(file_id, "invalid_related_files")
    return {
        "file_id": file_id, "status": "ready", "abstained": False,
        "category_code": category, "family_code": family, "lifecycle": lifecycle,
        "privacy_advice": privacy, "confidence": confidence, "relation_kind": relation,
        "related_file_ids": sorted(set(related_ids)), "reason": reason.strip(),
    }
