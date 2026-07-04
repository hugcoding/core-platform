#!/usr/bin/env python3
from pathlib import Path
import json

ROOT = Path("/volume1/docker/nas-stack")
PROJECT_YAML = ROOT / "project" / "meta" / "project.yaml"
OUTPUT = ROOT / "project" / "generated" / "project.json"


def parse_simple_yaml(text):
    """
    Minimal YAML parser voor onze project.yaml.
    Geen externe dependency nodig.
    Ondersteunt:
    - key: value
    - nested dictionaries
    - lists met '- key: value'
    """
    import re

    lines = text.splitlines()
    result = {}
    stack = [(0, result)]

    for raw in lines:
        if not raw.strip() or raw.strip().startswith("#"):
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()

        while stack and indent < stack[-1][0]:
            stack.pop()

        parent = stack[-1][1]

        if line.startswith("- "):
            item_line = line[2:]

            if not isinstance(parent, list):
                continue

            item = {}

            if ":" in item_line:
                key, value = item_line.split(":", 1)
                item[key.strip()] = parse_value(value.strip())

            parent.append(item)
            stack.append((indent + 2, item))
            continue

        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if value == "":
            # Kijk vooruit: wordt dit een lijst?
            next_is_list = False
            for nxt in lines[lines.index(raw) + 1:]:
                if not nxt.strip() or nxt.strip().startswith("#"):
                    continue
                next_indent = len(nxt) - len(nxt.lstrip(" "))
                if next_indent <= indent:
                    break
                if nxt.strip().startswith("- "):
                    next_is_list = True
                break

            node = [] if next_is_list else {}
            parent[key] = node
            stack.append((indent + 2, node))
        else:
            parent[key] = parse_value(value)

    return result


def parse_value(value):
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() in ("null", "none"):
        return None
    return value


def parse_markdown_issue(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    item = {
        "file": str(path.relative_to(ROOT)),
        "key": path.stem,
        "summary": path.stem,
        "type": "Story",
        "epic": "",
        "status": "To Do",
        "labels": "",
        "description": "",
    }

    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
        if " - " in title:
            item["key"], item["summary"] = title.split(" - ", 1)
        else:
            item["summary"] = title

    for line in lines:
        if line.startswith("Type:"):
            item["type"] = line.split(":", 1)[1].strip()
        elif line.startswith("Epic:"):
            item["epic"] = line.split(":", 1)[1].strip()
        elif line.startswith("Status:"):
            item["status"] = line.split(":", 1)[1].strip()
        elif line.startswith("Labels:"):
            item["labels"] = line.split(":", 1)[1].strip()

    if "## Description" in text:
        item["description"] = text.split("## Description", 1)[1].split("##", 1)[0].strip()

    return item


def read_markdown_issues():
    issues_dir = ROOT / "project" / "issues"
    if not issues_dir.exists():
        return []

    return [
        parse_markdown_issue(path)
        for path in sorted(issues_dir.glob("*.md"))
    ]


def analyze_project():
    if not PROJECT_YAML.exists():
        raise FileNotFoundError(PROJECT_YAML)

    text = PROJECT_YAML.read_text(encoding="utf-8", errors="replace")
    data = parse_simple_yaml(text)

    project = data.get("project", {})
    roadmap = data.get("roadmap", [])
    sprints = data.get("sprints", [])
    epics = data.get("epics", [])
    features = data.get("features", [])
    components = data.get("components", [])
    labels = data.get("labels", [])
    dod = data.get("definition_of_done", [])

    markdown_issues = read_markdown_issues()

    return {
        "source": str(PROJECT_YAML.relative_to(ROOT)),
        "project": project,
        "current": data.get("current", {}),
        "roadmap": roadmap,
        "sprints": sprints,
        "epics": epics,
        "features": features,
        "issues": markdown_issues,
        "components": components,
        "labels": labels,
        "definition_of_done": dod,
        "statistics": {
            "roadmap_items": len(roadmap),
            "sprints": len(sprints),
            "epics": len(epics),
            "features": len(features),
            "issues": len(markdown_issues),
            "components": len(components),
            "labels": len(labels),
            "definition_of_done_items": len(dod),
        },
    }


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    analysis = analyze_project()
    OUTPUT.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Project Analyzer klaar.")
    print(f"- {OUTPUT}")


if __name__ == "__main__":
    main()
