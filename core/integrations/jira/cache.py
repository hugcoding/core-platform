from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_cache(base_path: Path, name: str, data: dict[str, Any]) -> Path:
    cache_dir = base_path / "core" / "cache" / "jira"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{name}.json"
    with cache_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return cache_path
