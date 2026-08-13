"""Safe, deterministic normalization for managed CORE target paths."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import PurePosixPath
from typing import Iterable, Optional, Tuple


ALLOWED_ROOTS = ("/volume1/data/Persoonlijk", "/volume1/data/CORE")
CONTROL = re.compile(r"[\x00-\x1f]")


def normalize_target_path(value: str, *, filename: Optional[str] = None) -> dict[str, object]:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw.startswith("/"):
        raise ValueError("target path must be absolute")
    normalized_input = re.sub(r"/{2,}", "/", raw).rstrip("/")
    input_path = PurePosixPath(normalized_input)
    input_kind = "full_path"
    if filename and input_path.name.casefold() != filename.casefold():
        # Portal input without the current filename is an explicit destination
        # directory. A differently named file with a suffix remains a full path.
        if not input_path.suffix:
            input_kind = "directory"
            normalized = str(input_path / filename)
        else:
            normalized = normalized_input
    else:
        normalized = normalized_input
    parts = PurePosixPath(normalized).parts
    if ".." in raw.split("/") or "." in raw.split("/"):
        raise ValueError("relative path segments are not allowed")
    if CONTROL.search(normalized):
        raise ValueError("control characters are not allowed")
    if not any(normalized == root or normalized.startswith(root + "/") for root in ALLOWED_ROOTS):
        raise ValueError("target path is outside an allowed managed root")
    if len(parts) < 5 or not PurePosixPath(normalized).name:
        raise ValueError("target path must contain a filename")
    if len(normalized) > 500:
        raise ValueError("target path exceeds 500 characters")
    return {
        "raw": raw,
        "normalized": normalized,
        "normalized_input": normalized_input,
        "input_kind": input_kind,
        "changed": raw != normalized,
        "reason_codes": (
            (["duplicate_separator_collapsed"] if raw != normalized_input else [])
            + (["filename_appended_to_destination_directory"] if input_kind == "directory" else [])
        ),
    }


def suggest_known_target_path(
    value: str, *, filename: str, known_paths: Iterable[str], threshold: float = 0.84,
) -> dict[str, object]:
    """Suggest, but never silently apply, a close human-confirmed path."""
    entered = normalize_target_path(value, filename=filename)
    entered_path = PurePosixPath(str(entered["normalized"]))
    entered_directory = entered_path.parent
    best: Optional[Tuple[float, PurePosixPath]] = None
    technical_case_match = False
    for candidate in known_paths:
        try:
            known = normalize_target_path(candidate, filename=filename)
        except ValueError:
            continue
        candidate_directory = PurePosixPath(str(known["normalized"])).parent
        if len(candidate_directory.parts) != len(entered_directory.parts):
            continue
        differing = [
            (left, right) for left, right in zip(entered_directory.parts, candidate_directory.parts)
            if left.casefold() != right.casefold()
        ]
        if not differing and str(candidate_directory) != str(entered_directory):
            best = (1.0, candidate_directory / filename)
            technical_case_match = True
            break
        if len(differing) != 1:
            continue
        left, right = differing[0]
        score = SequenceMatcher(None, left.casefold(), right.casefold()).ratio()
        if score >= threshold and (best is None or score > best[0]):
            best = (score, candidate_directory / filename)
    if not best:
        return {**entered, "suggestion": None, "requires_confirmation": False}
    suggestion = str(best[1])
    return {
        **entered, "suggestion": suggestion, "similarity": round(best[0], 4),
        "requires_confirmation": not technical_case_match,
        "technical_normalization": technical_case_match,
        "suggestion_reason_code": (
            "confirmed_path_casing_normalized" if technical_case_match
            else "close_confirmed_path_segment"
        ),
    }
