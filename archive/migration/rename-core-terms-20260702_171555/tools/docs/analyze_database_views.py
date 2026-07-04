import re
from pathlib import Path
from tools.docs.io_utils import read_text


def analyze_database_views(root):
    root = Path(root)
    views_dir = root / "database" / "views"
    items = []

    if not views_dir.exists():
        return {"views_dir_exists": False, "count": 0, "items": []}

    for path in sorted(views_dir.glob("*.sql")):
        text = read_text(path)
        view_names = re.findall(r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+([a-zA-Z0-9_\.]+)", text, re.I)
        drops = re.findall(r"DROP\s+VIEW\s+IF\s+EXISTS\s+([a-zA-Z0-9_\.]+)", text, re.I)
        items.append({
            "file": str(path.relative_to(root)),
            "line_count": len(text.splitlines()),
            "views": view_names,
            "drops": drops,
            "content": text,
        })

    return {"views_dir_exists": True, "count": len(items), "items": items}
