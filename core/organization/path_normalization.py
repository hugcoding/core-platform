"""Safe, deterministic normalization for managed CORE target paths."""

from __future__ import annotations

import re
from pathlib import PurePosixPath


ALLOWED_ROOTS = ("/volume1/data/Persoonlijk", "/volume1/data/CORE")
CONTROL = re.compile(r"[\x00-\x1f]")


def normalize_target_path(value: str) -> dict[str, object]:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw.startswith("/"):
        raise ValueError("target path must be absolute")
    normalized = re.sub(r"/{2,}", "/", raw).rstrip("/")
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
        "changed": raw != normalized,
        "reason_codes": ["duplicate_separator_collapsed"] if raw != normalized else [],
    }
