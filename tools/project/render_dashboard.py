#!/usr/bin/env python3
from pathlib import Path
import json
from datetime import datetime, timezone

ROOT = Path("/volume1/docker/nas-stack")
PROJECT_JSON = ROOT / "project" / "generated" / "project.json"
DASHBOARD_JSON = ROOT / "project" / "generated" / "dashboard.json"
DASHBOARD_MD = ROOT / "project" / "generated" / "dashboard.md"


def load_project():
    return json.loads(PROJECT_JSON.read_text(encoding="utf-8"))


def count_by_status(items):
    result = {}
    for item in items:
        status = item.get("status", "Unknown")
        result[status] = result.get(status, 0) + 1
    return result


def build_dashboard(project):
    stats = project.get("statistics", {})
    roadmap = project.get("roadmap", [])
    sprints = project.get("sprints", [])
    epics = project.get("epics", [])
    features = project.get("features", [])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": project.get("project", {}),
        "current": project.get("current", {}),
        "summary": {
            "roadmap_items": stats.get("roadmap_items", len(roadmap)),
            "sprints": stats.get("sprints", len(sprints)),
            "epics": stats.get("epics", len(epics)),
            "features": stats.get("features", len(features)),
            "components": stats.get("components", 0),
            "labels": stats.get("labels", 0),
            "definition_of_done_items": stats.get("definition_of_done_items", 0),
        },
        "status": {
            "roadmap": count_by_status(roadmap),
            "sprints": count_by_status(sprints),
            "epics": count_by_status(epics),
            "features": count_by_status(features),
        },
        "active": {
            "release": project.get("current", {}).get("release"),
            "sprint": project.get("current", {}).get("sprint"),
        },
    }


def render_markdown(dashboard):
    lines = []
    lines.append("# CORE Project Dashboard\n\n")

    project = dashboard["project"]
    current = dashboard["current"]
    summary = dashboard["summary"]
    status = dashboard["status"]

    lines.append("## Project\n\n")
    lines.append(f"- Naam: `{project.get('name', 'Unknown')}`\n")
    lines.append(f"- Key: `{project.get('key', 'Unknown')}`\n")
    lines.append(f"- Methodology: `{project.get('methodology', 'Unknown')}`\n")
    lines.append(f"- Source of Truth: `{project.get('source_of_truth', 'Unknown')}`\n\n")

    lines.append("## Current\n\n")
    lines.append(f"- Release: `{current.get('release', 'Unknown')}`\n")
    lines.append(f"- Sprint: `{current.get('sprint', 'Unknown')}`\n\n")

    lines.append("## Summary\n\n")
    for key, value in summary.items():
        lines.append(f"- `{key}`: `{value}`\n")

    lines.append("\n## Status Overview\n\n")
    for group, values in status.items():
        lines.append(f"### {group.title()}\n\n")
        if not values:
            lines.append("_Geen items._\n\n")
            continue
        for status_name, count in values.items():
            lines.append(f"- `{status_name}`: `{count}`\n")
        lines.append("\n")

    lines.append("## Generated\n\n")
    lines.append(f"`{dashboard['generated_at']}`\n")

    return "".join(lines)


def main():
    if not PROJECT_JSON.exists():
        raise FileNotFoundError("project.json ontbreekt. Run eerst ./genproject")

    project = load_project()
    dashboard = build_dashboard(project)

    DASHBOARD_JSON.write_text(json.dumps(dashboard, indent=2, ensure_ascii=False), encoding="utf-8")
    DASHBOARD_MD.write_text(render_markdown(dashboard), encoding="utf-8")

    print("Project Dashboard klaar.")
    print(f"- {DASHBOARD_JSON}")
    print(f"- {DASHBOARD_MD}")


if __name__ == "__main__":
    main()
