from pathlib import Path
from datetime import datetime
from tools.docs.io_utils import write_text, read_text


WIKI_LINKS = [
    "architecture.md",
    "core.md",
    "rfc.md",
    "database-views.md",
    "scanner.md",
    "metadata-worker.md",
    "docker.md",
    "postgres.md",
    "redis.md",
    "scripts.md",
    "troubleshooting.md",
    "documentation-generator.md",
    "sources.md",
]


def _fix_links_for_docs_root(content):
    for link in WIKI_LINKS:
        content = content.replace("](" + link + ")", "](wiki/" + link + ")")
    return content


def render_main_document(docs_dir, wiki_dir):
    pages = [
        "index.md",
        "architecture.md",
        "core.md",
        "rfc.md",
        "database-views.md",
        "scanner.md",
        "metadata-worker.md",
        "docker.md",
        "postgres.md",
        "redis.md",
        "scripts.md",
        "troubleshooting.md",
        "documentation-generator.md",
        "sources.md",
    ]

    md = []
    md.append("# NAS Metadata Platform Documentatie\n\n")
    md.append("_Automatisch gegenereerd op " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "_\n\n")

    for page in pages:
        path = Path(wiki_dir) / page
        if path.exists():
            md.append("\n---\n\n")
            md.append(_fix_links_for_docs_root(read_text(path)))
            md.append("\n")

    write_text(Path(docs_dir) / "DOCUMENTATIE.md", "".join(md))
