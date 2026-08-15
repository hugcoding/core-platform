"""Safe, proposal-only filename normalization for managed documents."""

from __future__ import annotations

import re
from pathlib import PurePosixPath


INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10))}


def normalize_proposed_filename(value: str, *, current_filename: str) -> dict[str, object]:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("proposed filename is required")
    current_suffix = PurePosixPath(current_filename).suffix
    entered_suffix = PurePosixPath(raw).suffix
    entered_stem = raw[:-len(entered_suffix)] if entered_suffix else raw
    reasons = []
    if entered_suffix and entered_suffix.casefold() != current_suffix.casefold():
        reasons.append("original_extension_preserved")
    elif not entered_suffix and current_suffix:
        reasons.append("original_extension_appended")
    stem = INVALID.sub("_", entered_stem)
    stem = re.sub(r"\s+", " ", stem)
    stem = re.sub(r"_+", "_", stem).strip(" ._")
    if stem != entered_stem.strip(" ."):
        reasons.append("invalid_filename_characters_normalized")
    if not stem:
        raise ValueError("proposed filename has no usable name")
    if stem.upper() in RESERVED:
        stem = "_" + stem
        reasons.append("reserved_filename_normalized")
    maximum_stem = 180 - len(current_suffix)
    if len(stem) > maximum_stem:
        stem = stem[:maximum_stem].rstrip(" ._")
        reasons.append("filename_length_limited")
    normalized = stem + current_suffix
    if normalized.casefold() == current_filename.casefold():
        reasons.append("filename_unchanged")
    return {
        "raw": raw,
        "original_filename": current_filename,
        "normalized": normalized,
        "changed": normalized != raw,
        "reason_codes": list(dict.fromkeys(reasons)),
    }


def target_with_filename(target_path: str, filename: str) -> str:
    return str(PurePosixPath(target_path).parent / filename)
