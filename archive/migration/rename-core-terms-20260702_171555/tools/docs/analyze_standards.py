from pathlib import Path
from tools.docs.io_utils import read_text


def analyze_standards(root):
    root = Path(root)
    standards_dir = root / "docs" / "standards"

    items = []

    if not standards_dir.exists():
        return {
            "standards_dir_exists": False,
            "count": 0,
            "items": [],
        }

    for path in sorted(standards_dir.glob("*.md")):
        text = read_text(path)
        title = path.stem

        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break

        items.append({
            "file": str(path.relative_to(root)),
            "name": path.stem,
            "title": title,
            "line_count": len(text.splitlines()),
            "content": text,
        })

    return {
        "standards_dir_exists": True,
        "count": len(items),
        "items": items,
    }
