from pathlib import Path
from tools.docs.io_utils import read_text


def parse_simple_yaml(text):
    data = {}
    stack = [(0, data)]

    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()

        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        while stack and indent < stack[-1][0]:
            stack.pop()

        parent = stack[-1][1]

        if value == "":
            node = {}
            parent[key] = node
            stack.append((indent + 2, node))
        else:
            if value.lower() == "true":
                parsed = True
            elif value.lower() == "false":
                parsed = False
            else:
                parsed = value
            parent[key] = parsed

    return data


def analyze_core(root):
    root = Path(root)
    core_dir = root / "core"
    manifest = core_dir / "core.yaml"

    text = read_text(manifest)
    parsed = parse_simple_yaml(text) if text else {}

    modules = parsed.get("modules", {}) if isinstance(parsed.get("modules", {}), dict) else {}
    engines = parsed.get("engines", {}) if isinstance(parsed.get("engines", {}), dict) else {}

    return {
        "core_dir_exists": core_dir.exists(),
        "manifest_exists": manifest.exists(),
        "manifest_file": "core/core.yaml",
        "platform": parsed.get("platform", {}),
        "paths": parsed.get("paths", {}),
        "redis": parsed.get("redis", {}),
        "database": parsed.get("database", {}),
        "modules": modules,
        "engines": engines,
        "raw": text,
    }
