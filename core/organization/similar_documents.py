"""Conservative, explainable reuse of accepted document reviews."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any


RULE_VERSION = "similar-document-review-v1"
SUPPORTED_EXTENSIONS = {"docx", "pdf", "xlsx"}


def normalized_document_identity(filename: str) -> str:
    """Return a cautious identity key across source/export and common copy suffixes."""
    stem = PurePosixPath(filename.replace("\\", "/")).stem.casefold()
    stem = re.sub(r"\s*[-_ ]\s*(en|nl|engels|nederlands)\s*$", "", stem)
    stem = re.sub(r"\s*[\[(](?:kopie|copy)?\s*\d+[\])]\s*$", "", stem)
    stem = re.sub(r"\s*[-_ ]\s*(?:kopie|copy)\s*\d*\s*$", "", stem)
    return re.sub(r"[^a-z0-9]+", " ", stem).strip()


def apply_similar_review_proposals(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach consensus proposals; never changes stored reviews or privacy labels."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        extension = str(item.get("extension") or "").casefold().lstrip(".")
        identity = normalized_document_identity(str(item.get("filename") or ""))
        if extension in SUPPORTED_EXTENSIONS and len(identity) >= 5:
            groups.setdefault(identity, []).append(item)

    for identity, members in groups.items():
        accepted = [item for item in members if (
            item.get("latest_review_decision") == "accepted"
            and item.get("latest_review_category")
            and item.get("latest_review_family")
            and item.get("latest_review_id")
        )]
        judgments = {
            (str(item["latest_review_category"]), str(item["latest_review_family"]))
            for item in accepted
        }
        for item in members:
            if item.get("latest_review_decision") == "accepted" or not accepted:
                continue
            peers = [peer for peer in members if peer is not item]
            evidence = {
                "rule_version": RULE_VERSION,
                "normalized_identity": identity,
                "match_kind": "normalized_filename_cross_format",
                "score": 1.0 if any(
                    PurePosixPath(str(peer.get("filename") or "")).stem.casefold()
                    == PurePosixPath(str(item.get("filename") or "")).stem.casefold()
                    for peer in accepted
                ) else 0.95,
                "related_file_ids": [int(peer["file_id"]) for peer in peers[:10]],
                "source_review_event_ids": [str(peer["latest_review_id"]) for peer in accepted[:10]],
                "documents": [{
                    "file_id": int(peer["file_id"]),
                    "filename": str(peer.get("filename") or ""),
                    "extension": str(peer.get("extension") or ""),
                    "human_reviewed": peer in accepted,
                } for peer in peers[:5]],
                "conflicting_human_judgments": len(judgments) > 1,
            }
            if len(judgments) == 1:
                category, family = next(iter(judgments))
                evidence.update({
                    "status": "consensus_proposal",
                    "proposed_category_code": category,
                    "proposed_document_family_code": family,
                })
            else:
                evidence["status"] = "conflicting_reviews_require_review"
            item["similar_document_proposal"] = evidence
    return items
