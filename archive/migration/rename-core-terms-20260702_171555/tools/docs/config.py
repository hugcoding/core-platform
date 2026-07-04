from pathlib import Path

ROOT = Path("/volume1/docker/nas-stack")
DOCS_DIR = ROOT / "docs"
WIKI_DIR = DOCS_DIR / "wiki"
GENERATED_DIR = DOCS_DIR / "generated"
DIAGRAMS_DIR = DOCS_DIR / "diagrams"

PYTHON_FILES = [
    "scanner.py",
    "metadata_worker.py",
    "generate_docs.py",
    "tools/docs/config.py",
    "tools/docs/analyze_python.py",
    "tools/docs/analyze_project.py",
    "tools/docs/render_markdown.py",
    "tools/docs/render_docx.py",
    "tools/docs/pages.py",
    "tools/docs/generate_docs.py",
]

CONFIG_FILES = [
    "docker-compose.yml",
    "Dockerfile.base",
    "Dockerfile.scanner",
    "Dockerfile.metadata",
    "schema.sql",
]

SCRIPT_FILES = [
    "rebuild",
    "rebuildall",
    "logs",
    "status",
    "dlq",
    "redis",
    "cleanlocks",
    "watch",
    "gendocs",
]

ALL_SOURCE_FILES = PYTHON_FILES + CONFIG_FILES + SCRIPT_FILES
