import re
from pathlib import Path
from tools.docs.io_utils import read_text


def analyze_compose(root):
    path = Path(root) / "docker-compose.yml"
    text = read_text(path)

    services = []
    in_services = False

    for line in text.splitlines():
        if line.strip() == "services:":
            in_services = True
            continue

        if in_services:
            match = re.match(r"^  ([a-zA-Z0-9_-]+):\s*$", line)
            if match:
                services.append(match.group(1))

    env_vars = sorted(set(re.findall(r"\b[A-Z][A-Z0-9_]+\b", text)))
    env_vars = [e for e in env_vars if e not in {"CMD", "NULL", "TRUE", "FALSE"}]

    return {
        "file": "docker-compose.yml",
        "exists": path.exists(),
        "services": services,
        "environment_variables": env_vars,
        "line_count": len(text.splitlines()),
    }


def analyze_schema(root):
    path = Path(root) / "schema.sql"
    text = read_text(path)

    tables = sorted(set(re.findall(r"CREATE TABLE .*?public\.([a-zA-Z0-9_]+)", text)))
    unique_constraints = re.findall(r"UNIQUE \(([^\)]+)\)", text)
    foreign_keys = re.findall(r"FOREIGN KEY \(([^\)]+)\)", text)

    return {
        "file": "schema.sql",
        "exists": path.exists(),
        "tables": tables,
        "unique_constraints": sorted(set(unique_constraints)),
        "foreign_keys": sorted(set(foreign_keys)),
        "line_count": len(text.splitlines()),
    }


def analyze_scripts(root, scripts):
    result = {}

    for script in scripts:
        path = Path(root) / script
        text = read_text(path)
        result[script] = {
            "exists": path.exists(),
            "line_count": len(text.splitlines()),
            "uses_docker_compose": "docker compose" in text,
            "uses_redis": "redis-cli" in text,
            "content": text,
        }

    return result


def analyze_sources(root, files):
    result = {}
    for file in files:
        path = Path(root) / file
        text = read_text(path)
        result[file] = {
            "exists": path.exists(),
            "line_count": len(text.splitlines()),
        }
    return result
