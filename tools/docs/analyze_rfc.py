import re
from pathlib import Path
from tools.docs.io_utils import read_text


def _extract_status(text):
    match = re.search(r"## Status\s+(.+?)(?:\n## |\Z)", text, re.S)
    if not match:
        return "Unknown"
    lines = [line.strip() for line in match.group(1).splitlines() if line.strip()]
    return lines[0] if lines else "Unknown"


def _extract_title(text, fallback):
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def analyze_rfc(root):
    root = Path(root)
    rfc_dir = root / "docs" / "rfc"

    items = []

    if not rfc_dir.exists():
        return {"rfc_dir_exists": False, "count": 0, "items": []}

    for path in sorted(rfc_dir.glob("RFC-*.md")):
        text = read_text(path)
        items.append({
            "file": str(path.relative_to(root)),
            "id": path.stem,
            "title": _extract_title(text, path.stem),
            "status": _extract_status(text),
            "line_count": len(text.splitlines()),
            "content": text,
        })

    return {"rfc_dir_exists": True, "count": len(items), "items": items}
