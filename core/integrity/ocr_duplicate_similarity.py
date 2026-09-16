"""Conservative near-duplicate evidence derived from existing OCR artifacts."""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ANALYZER_VERSION = "ocr-near-duplicate-v1"
MIN_CHARACTERS = 500
MIN_LENGTH_RATIO = 0.98
MIN_TOKEN_JACCARD = 0.95
MIN_FIVEGRAM_JACCARD = 0.90


def normalized_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())


def _jaccard(left: set[Any], right: set[Any]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def compare_ocr_text(left: str, right: str) -> dict[str, Any]:
    """Return bounded similarity metrics; never returns or stores source text."""
    left_tokens, right_tokens = normalized_tokens(left), normalized_tokens(right)
    left_characters = sum(map(len, left_tokens))
    right_characters = sum(map(len, right_tokens))
    longest = max(left_characters, right_characters, 1)
    length_ratio = min(left_characters, right_characters) / longest
    left_fivegrams = set(zip(*(left_tokens[offset:] for offset in range(5))))
    right_fivegrams = set(zip(*(right_tokens[offset:] for offset in range(5))))
    token_jaccard = _jaccard(set(left_tokens), set(right_tokens))
    fivegram_jaccard = _jaccard(left_fivegrams, right_fivegrams)
    qualifies = (
        min(left_characters, right_characters) >= MIN_CHARACTERS
        and length_ratio >= MIN_LENGTH_RATIO
        and token_jaccard >= MIN_TOKEN_JACCARD
        and fivegram_jaccard >= MIN_FIVEGRAM_JACCARD
    )
    return {
        "qualifies": qualifies,
        "length_ratio": round(length_ratio, 6),
        "token_jaccard": round(token_jaccard, 6),
        "fivegram_jaccard": round(fivegram_jaccard, 6),
        "left_characters": left_characters,
        "right_characters": right_characters,
        "thresholds": {
            "length_ratio": MIN_LENGTH_RATIO,
            "token_jaccard": MIN_TOKEN_JACCARD,
            "fivegram_jaccard": MIN_FIVEGRAM_JACCARD,
        },
    }


def compare_ocr_artifacts(left: Path, right: Path) -> dict[str, Any]:
    with gzip.open(left, "rt", encoding="utf-8") as handle:
        left_text = handle.read()
    with gzip.open(right, "rt", encoding="utf-8") as handle:
        right_text = handle.read()
    return compare_ocr_text(left_text, right_text)


def group_key(identity: str, left_hash: str, right_hash: str) -> str:
    hashes = sorted((left_hash, right_hash))
    return hashlib.sha256(
        f"{ANALYZER_VERSION}\n{identity}\n{hashes[0]}\n{hashes[1]}".encode("utf-8")
    ).hexdigest()


def evidence_metadata(identity: str, peer_file_id: int, metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": "ocr_near_duplicate",
        "normalized_document_identity": identity,
        "peer_file_id": peer_file_id,
        "similarity": metrics,
        "raw_text_stored_in_database": False,
        "requires_human_review": True,
        "automatic_deletion_allowed": False,
    }


def metadata_json(identity: str, peer_file_id: int, metrics: dict[str, Any]) -> str:
    return json.dumps(evidence_metadata(identity, peer_file_id, metrics), ensure_ascii=False)
