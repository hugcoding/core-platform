from datetime import datetime


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def code_block(content, lang=""):
    return "```" + lang + "\n" + content.rstrip() + "\n```\n"


def read_file(root, relative_path):
    path = root / relative_path
    if not path.exists():
        return ""
    return path.read_text(errors="replace")


def page_index():
    return """# NAS Metadata Platform Wiki

Deze wiki wordt automatisch gegenereerd.

## Pagina's

- [Scanner](scanner.md)
- [Metadata Worker](metadata-worker.md)
- [Documentatiegenerator](documentation-generator.md)
- [Bronbestanden](sources.md)

## Datastroom

```text
/volume1
  |
  v
Polling Scanner
  |
  v
Redis Stream: scan_stream
  |
  v
Metadata Worker
  |
  v
PostgreSQL

Fouten -> scan_stream_dlq
```
"""


def page_python_component(title, analysis, source_text):
    md = []
    md.append("# " + title + "\n\n")
    md.append("Bronbestand: `" + analysis["file"] + "`\n\n")

    if not analysis["exists"]:
        md.append("Bestand ontbreekt.\n")
        return "".join(md)

    if analysis.get("syntax_error"):
        md.append("Syntaxfout: `" + analysis["syntax_error"] + "`\n\n")

    md.append("## Imports\n\n")
    for item in analysis["imports"]:
        md.append("- `" + item + "`\n")
    md.append("\n")

    md.append("## Constanten\n\n")
    for item in analysis["constants"]:
        md.append("- `" + item + "`\n")
    md.append("\n")

    md.append("## Functies\n\n")
    for fn in analysis["functions"]:
        args = ", ".join(fn["args"])
        md.append("### `" + fn["name"] + "(" + args + ")`\n\n")
        md.append("- Regel: `" + str(fn["line"]) + "`\n")
        if fn["docstring"]:
            md.append("- Docstring: " + fn["docstring"] + "\n")
        else:
            md.append("- Docstring: _niet aanwezig_\n")
        md.append("\n")

    md.append("## Classes\n\n")
    for cls in analysis["classes"]:
        md.append("- `" + cls["name"] + "` op regel `" + str(cls["line"]) + "`\n")
    md.append("\n")

    md.append("## Broncode\n\n")
    md.append(code_block(source_text, "python"))
    return "".join(md)


def page_sources(root, files):
    md = ["# Bronbestanden\n\n"]
    for f in files:
        text = read_file(root, f)
        md.append("## `" + f + "`\n\n")
        if not text:
            md.append("_Bestand ontbreekt of is leeg._\n\n")
            continue
        lang = ""
        if f.endswith(".py"):
            lang = "python"
        elif f.endswith(".yml") or f.endswith(".yaml"):
            lang = "yaml"
        elif f.endswith(".sql"):
            lang = "sql"
        elif "Dockerfile" in f:
            lang = "dockerfile"
        elif f in ["rebuild", "rebuildall", "logs", "status", "dlq", "redis", "cleanlocks", "watch", "docs"]:
            lang = "bash"
        md.append(code_block(text, lang))
        md.append("\n")
    return "".join(md)


def main_document(root, wiki_dir):
    pages = [
        "index.md",
        "scanner.md",
        "metadata-worker.md",
        "documentation-generator.md",
        "sources.md",
        "standards.md",
    ]

    md = []
    md.append("# NAS Metadata Platform Documentatie\n\n")
    md.append("_Automatisch gegenereerd op " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "_\n\n")

    for page in pages:
        path = wiki_dir / page
        if path.exists():
            md.append("\n---\n\n")
            md.append(path.read_text(errors="replace"))
            md.append("\n")

    return "".join(md)
