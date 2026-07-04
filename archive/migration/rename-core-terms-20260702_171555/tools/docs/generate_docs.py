#!/usr/bin/env python3
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
ROOT = CURRENT.parents[2]
sys.path.insert(0, str(ROOT))

from tools.docs.config import (
    ROOT as STACK_ROOT,
    DOCS_DIR,
    WIKI_DIR,
    GENERATED_DIR,
    PYTHON_FILES,
    CONFIG_FILES,
    SCRIPT_FILES,
    ALL_SOURCE_FILES,
)
from tools.docs.analyze_standards import analyze_standards
from tools.docs.io_utils import write_text, write_json, read_text
from tools.docs.analyze_python import analyze_python_files
from tools.docs.analyze_project import analyze_compose, analyze_schema, analyze_scripts, analyze_sources
from tools.docs.analyze_core import analyze_core
from tools.docs.analyze_rfc import analyze_rfc
from tools.docs.analyze_database_views import analyze_database_views
from tools.docs.pages import (
    page_index,
    page_architecture,
    page_python_component,
    page_docker,
    page_postgres,
    page_redis,
    page_scripts,
    page_troubleshooting,
    page_documentation_generator,
    page_sources,
)
from tools.docs.pages_core import page_core, page_rfc, page_database_views, page_standards
from tools.docs.render_markdown import render_main_document
from tools.docs.render_docx import render_docx

def build_analysis():
    python_analysis = analyze_python_files(STACK_ROOT, PYTHON_FILES)
    compose_analysis = analyze_compose(STACK_ROOT)
    schema_analysis = analyze_schema(STACK_ROOT)
    script_analysis = analyze_scripts(STACK_ROOT, SCRIPT_FILES)
    source_analysis = analyze_sources(STACK_ROOT, ALL_SOURCE_FILES)
    core_analysis = analyze_core(STACK_ROOT)
    rfc_analysis = analyze_rfc(STACK_ROOT)
    database_views_analysis = analyze_database_views(STACK_ROOT)
    standards_analysis = analyze_standards(STACK_ROOT)

    return {
        "python": python_analysis,
        "compose": compose_analysis,
        "schema": schema_analysis,
        "scripts": script_analysis,
        "sources": source_analysis,
        "core": core_analysis,
        "rfc": rfc_analysis,
        "database_views": database_views_analysis,
        "standards": standards_analysis,
    }


def render_json_outputs(analysis):
    write_json(GENERATED_DIR / "python_analysis.json", analysis["python"])
    write_json(GENERATED_DIR / "docker_analysis.json", analysis["compose"])
    write_json(GENERATED_DIR / "sql_analysis.json", analysis["schema"])
    write_json(GENERATED_DIR / "scripts_analysis.json", analysis["scripts"])
    write_json(GENERATED_DIR / "project_index.json", analysis["sources"])
    write_json(GENERATED_DIR / "core_analysis.json", analysis["core"])
    write_json(GENERATED_DIR / "rfc_analysis.json", analysis["rfc"])
    write_json(GENERATED_DIR / "database_views_analysis.json", analysis["database_views"])
    write_json(GENERATED_DIR / "standards_analysis.json", analysis["standards"])


def render_wiki_pages(analysis):
    write_text(WIKI_DIR / "index.md", page_index())
    write_text(WIKI_DIR / "architecture.md", page_architecture())
    write_text(WIKI_DIR / "core.md", page_core(analysis["core"]))
    write_text(WIKI_DIR / "rfc.md", page_rfc(analysis["rfc"]))
    write_text(WIKI_DIR / "database-views.md", page_database_views(analysis["database_views"]))
    write_text(WIKI_DIR / "standards.md", page_standards(analysis["standards"]))

    write_text(WIKI_DIR / "scanner.md", page_python_component(
        "Scanner",
        analysis["python"]["scanner.py"],
        read_text(STACK_ROOT / "scanner.py"),
    ))

    write_text(WIKI_DIR / "metadata-worker.md", page_python_component(
        "Metadata Worker",
        analysis["python"]["metadata_worker.py"],
        read_text(STACK_ROOT / "metadata_worker.py"),
    ))

    write_text(WIKI_DIR / "docker.md", page_docker(analysis["compose"], STACK_ROOT))
    write_text(WIKI_DIR / "postgres.md", page_postgres(analysis["schema"], STACK_ROOT))
    write_text(WIKI_DIR / "redis.md", page_redis())
    write_text(WIKI_DIR / "scripts.md", page_scripts(analysis["scripts"]))
    write_text(WIKI_DIR / "troubleshooting.md", page_troubleshooting())

    write_text(WIKI_DIR / "documentation-generator.md", page_documentation_generator(
        analysis["python"]["tools/docs/generate_docs.py"]
    ))

    write_text(WIKI_DIR / "sources.md", page_sources(STACK_ROOT, ALL_SOURCE_FILES))

def main():
    DOCS_DIR.mkdir(exist_ok=True)
    WIKI_DIR.mkdir(exist_ok=True)
    GENERATED_DIR.mkdir(exist_ok=True)

    analysis = build_analysis()

    render_json_outputs(analysis)
    render_wiki_pages(analysis)
    render_main_document(DOCS_DIR, WIKI_DIR)

    docx_done = render_docx(DOCS_DIR / "DOCUMENTATIE.md", DOCS_DIR / "DOCUMENTATIE.docx")

    print("Documentatiegenerator CORE klaar.")
    print("- docs/DOCUMENTATIE.md")

    if docx_done:
        print("- docs/DOCUMENTATIE.docx")
    else:
        print("- DOCX overgeslagen: python-docx ontbreekt")

    print("- docs/wiki/")
    print("- docs/generated/")


if __name__ == "__main__":
    main()
