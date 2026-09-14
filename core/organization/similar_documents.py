"""Conservative, explainable reuse of accepted document reviews."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import PurePosixPath
from typing import Any


RULE_VERSION = "similar-document-review-v2"
SUPPORTED_EXTENSIONS = {"docx", "pdf", "xlsx"}
GENERIC_IDENTITIES = {"bestand", "brief", "document", "formulier", "image", "lijst", "scan"}
SAFE_SHORT_IDENTITIES = {"tuin"}


def document_identity(filename: str) -> dict[str, Any]:
    """Return a conservative identity plus explainable normalization evidence."""
    stem = PurePosixPath(filename.replace("\\", "/")).stem.casefold()
    original = stem
    reasons: list[str] = []
    transforms = (
        (r"^\s*(?:signed|ondertekend|getekend)[-_ ]+", "signature_marker"),
        (r"\s*[-_ ]\s*(?:signed|ondertekend|getekend)\s*$", "signature_marker"),
        (r"\s*[-_ ]\s*(?:gecomprimeerd|compressed)\s*$", "compression_marker"),
        (r"\s*[-_ ]\s*(?:definitief|final)\s*$", "final_marker"),
        (r"\s*[-_ ]\s*(?:versie|version|vs?|rev)\s*\d+(?:[._-]\d+)*\s*$", "version_suffix"),
        (r"\s*[-_ ]\s*(?:en|nl|engels|nederlands)\s*$", "language_suffix"),
        (r"\s*[\[(](?:kopie|copy)?\s*\d+[\])]\s*$", "copy_suffix"),
        (r"\s*[-_ ]\s*(?:kopie|copy)\s*\d*\s*$", "copy_suffix"),
        (r"[-_ ]+\d{1,2}[.\-_]\d{1,2}[.\-_]\d{2,4}\s*$", "date_suffix"),
        (r"[-_ ]+\d{4}[.\-_]\d{1,2}[.\-_]\d{1,2}\s*$", "date_suffix"),
        (r"[-_ ]+\d{8}\s*$", "date_suffix"),
        (r"[-_ ]+(?:19|20)\d{2}\s*$", "year_suffix"),
        (r"[-_ ]+\d{6,}\s*$", "reference_suffix"),
    )
    changed = True
    while changed:
        changed = False
        for pattern, reason in transforms:
            updated = re.sub(pattern, "", stem)
            if updated != stem:
                stem = updated
                if reason not in reasons:
                    reasons.append(reason)
                changed = True
    identity = re.sub(r"[^a-z0-9]+", " ", stem).strip()
    safe = (len(identity) >= 5 or identity in SAFE_SHORT_IDENTITIES) and identity not in GENERIC_IDENTITIES
    identity_key = f"short:{identity}" if identity in SAFE_SHORT_IDENTITIES else identity
    return {
        "identity": identity_key if safe else "",
        "raw_identity": identity,
        "rule_version": RULE_VERSION,
        "normalization_reasons": reasons,
        "is_safe": safe,
        "is_exact_stem": stem == original,
    }


def normalized_document_identity(filename: str) -> str:
    """Return a cautious document-pattern identity for similar-review reuse."""
    return str(document_identity(filename)["identity"])


def apply_similar_review_proposals(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach review-based proposals; never changes stored reviews or privacy labels."""
    groups: dict[str, list[dict[str, Any]]] = {}

    for item in items:
        extension = str(item.get("extension") or "").casefold().lstrip(".")
        identity_details = document_identity(str(item.get("filename") or ""))
        identity = str(identity_details["identity"])

        if extension in SUPPORTED_EXTENSIONS and len(identity) >= 5:
            groups.setdefault(identity, []).append(item)

    for identity, members in groups.items():
        accepted = [
            item
            for item in members
            if (
                item.get("latest_review_decision") == "accepted"
                and item.get("latest_review_category")
                and item.get("latest_review_family")
                and item.get("latest_review_id")
            )
        ]

        if not accepted:
            continue

        judgment_counts = Counter(
            (
                str(item["latest_review_category"]),
                str(item["latest_review_family"]),
            )
            for item in accepted
        )

        most_common = judgment_counts.most_common()

        for item in members:
            if item.get("latest_review_decision") == "accepted":
                continue

            peers = [peer for peer in members if peer is not item]
            evidence_peers = accepted + [peer for peer in peers if peer not in accepted]

            (category, family), count = most_common[0]
            total = len(accepted)

            second_count = most_common[1][1] if len(most_common) > 1 else 0
            has_clear_winner = count > second_count

            evidence = {
                "rule_version": RULE_VERSION,
                "normalized_identity": identity,
                "normalization_reasons": identity_details["normalization_reasons"],
                "match_kind": "normalized_filename_cross_format",
                "score": 1.0 if any(
                    PurePosixPath(str(peer.get("filename") or "")).stem.casefold()
                    == PurePosixPath(str(item.get("filename") or "")).stem.casefold()
                    for peer in accepted
                ) else 0.95,
                "related_file_ids": [
                    int(peer["file_id"])
                    for peer in evidence_peers[:10]
                ],
                "source_review_event_ids": [
                    str(peer["latest_review_id"])
                    for peer in accepted[:10]
                ],
                "documents": [
                    {
                        "file_id": int(peer["file_id"]),
                        "filename": str(peer.get("filename") or ""),
                        "extension": str(peer.get("extension") or ""),
                        "human_reviewed": peer in accepted,
                        "source_review_event_id": (
                            str(peer["latest_review_id"]) if peer in accepted else None
                        ),
                    }
                    for peer in evidence_peers[:5]
                ],
                "conflicting_human_judgments": len(judgment_counts) > 1,
                "support_count": count,
                "review_count": total,
                "support_ratio": round(count / total, 2),
            }

            if has_clear_winner:
                evidence.update(
                    {
                        "status": "consensus_proposal",
                        "proposed_category_code": category,
                        "proposed_document_family_code": family,
                    }
                )
            else:
                evidence["status"] = "conflicting_reviews_require_review"

            item["similar_document_proposal"] = evidence

    return items
