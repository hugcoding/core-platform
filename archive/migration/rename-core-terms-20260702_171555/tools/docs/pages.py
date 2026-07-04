from tools.docs.io_utils import read_text, code_block


def page_index():
    return """# NAS Metadata Platform Wiki

Deze wiki wordt automatisch gegenereerd door de documentatiegenerator.

## Hoofdstukken

- [Architectuur](architecture.md)
- [Scanner](scanner.md)
- [Metadata Worker](metadata-worker.md)
- [Docker](docker.md)
- [PostgreSQL](postgres.md)
- [Redis](redis.md)
- [Scripts](scripts.md)
- [Troubleshooting](troubleshooting.md)
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


def page_architecture():
    return """# Architectuur

De NAS Metadata Stack bestaat uit een polling scanner, Redis Streams, een metadata worker en PostgreSQL.

## Ontwerpkeuzes

- Geen host watcher meer.
- Geen inotify-afhankelijkheid.
- Scanner draait in Docker.
- Redis Streams koppelen scanner en worker los van elkaar.
- Consumer Groups maken gecontroleerde verwerking mogelijk.
- PostgreSQL bewaart de permanente metadata-index.
- Heartbeats en locks voorkomen dubbele processen.
- DLQ voorkomt dat slechte events de worker blokkeren.
"""


def page_python_component(title, analysis, source_text):
    md = []
    md.append("# " + title + "\n\n")
    md.append("Bronbestand: `" + analysis["file"] + "`\n\n")

    if not analysis["exists"]:
        md.append("Bestand ontbreekt.\n")
        return "".join(md)

    md.append(f"- Regels: `{analysis['line_count']}`\n")
    md.append(f"- Functies: `{len(analysis['functions'])}`\n")
    md.append(f"- Classes: `{len(analysis['classes'])}`\n")
    md.append(f"- Imports: `{len(analysis['imports'])}`\n\n")

    if analysis.get("syntax_error"):
        md.append("## Syntaxfout\n\n")
        md.append("`" + analysis["syntax_error"] + "`\n\n")

    md.append("## Imports\n\n")
    for item in analysis["imports"]:
        md.append("- `" + item + "`\n")
    md.append("\n")

    md.append("## Constanten\n\n")
    for item in analysis["constants"]:
        md.append("- `" + item["name"] + "` op regel `" + str(item["line"]) + "`\n")
    md.append("\n")

    md.append("## Redis keys / streams\n\n")
    if analysis["redis_keys"]:
        for key in analysis["redis_keys"]:
            md.append("- `" + key + "`\n")
    else:
        md.append("_Geen Redis-keys automatisch herkend._\n")
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

    md.append("## SQL statements\n\n")
    if analysis["sql_statements"]:
        for stmt in analysis["sql_statements"]:
            md.append("### Statement regel `" + str(stmt["line"]) + "`\n\n")
            md.append(code_block(stmt["snippet"], "sql"))
            md.append("\n")
    else:
        md.append("_Geen SQL-statements automatisch herkend._\n\n")

    md.append("## Broncode\n\n")
    md.append(code_block(source_text, "python"))

    return "".join(md)


def page_docker(compose, root):
    md = ["# Docker\n\n"]

    md.append("## Services\n\n")
    for service in compose["services"]:
        md.append("- `" + service + "`\n")

    md.append("\n## Environment variables\n\n")
    for env in compose["environment_variables"]:
        md.append("- `" + env + "`\n")

    md.append("\n## docker-compose.yml\n\n")
    md.append(code_block(read_text(root / "docker-compose.yml"), "yaml"))

    for dockerfile in ["Dockerfile.base", "Dockerfile.scanner", "Dockerfile.metadata"]:
        md.append("\n## " + dockerfile + "\n\n")
        md.append(code_block(read_text(root / dockerfile), "dockerfile"))

    return "".join(md)


def page_postgres(schema, root):
    md = ["# PostgreSQL\n\n"]

    md.append("## Tabellen\n\n")
    for table in schema["tables"]:
        md.append("- `" + table + "`\n")

    md.append("\n## Unique constraints\n\n")
    for constraint in schema["unique_constraints"]:
        md.append("- `" + constraint + "`\n")

    md.append("\n## Foreign keys\n\n")
    for fk in schema["foreign_keys"]:
        md.append("- `" + fk + "`\n")

    md.append("\n## schema.sql\n\n")
    md.append(code_block(read_text(root / "schema.sql"), "sql"))

    return "".join(md)


def page_redis():
    return """# Redis

Redis is de event- en statuslaag.

## Belangrijke keys

- `scan_stream`
- `scan_stream_dlq`
- `metadata_group`
- `scanner:lock:event`
- `metadata_worker:lock`
- heartbeat keys

## Checks

```bash
docker exec -it nas-redis-1 redis-cli XLEN scan_stream
docker exec -it nas-redis-1 redis-cli XINFO GROUPS scan_stream
docker exec -it nas-redis-1 redis-cli XINFO CONSUMERS scan_stream metadata_group
docker exec -it nas-redis-1 redis-cli XLEN scan_stream_dlq
```
"""


def page_scripts(script_analysis):
    md = ["# Scripts\n\n"]

    descriptions = {
        "rebuild": "Bouwt scanner en metadata_worker opnieuw.",
        "rebuildall": "Bouwt de volledige stack opnieuw.",
        "logs": "Toont live logs.",
        "status": "Toont status, locks, heartbeats en streaminfo.",
        "dlq": "Toont DLQ-informatie.",
        "redis": "Opent redis-cli.",
        "cleanlocks": "Verwijdert locks handmatig.",
        "watch": "Live monitor.",
        "docs": "Genereert documentatie.",
    }

    for name, info in script_analysis.items():
        md.append("## `" + name + "`\n\n")
        md.append(descriptions.get(name, "Script") + "\n\n")
        md.append("- Bestaat: `" + str(info["exists"]) + "`\n")
        md.append("- Regels: `" + str(info["line_count"]) + "`\n")
        md.append("- Gebruikt docker compose: `" + str(info["uses_docker_compose"]) + "`\n")
        md.append("- Gebruikt Redis: `" + str(info["uses_redis"]) + "`\n\n")
        if info["content"]:
            md.append(code_block(info["content"], "bash"))
        md.append("\n")

    return "".join(md)


def page_troubleshooting():
    return """# Troubleshooting

## Worker is unhealthy

```bash
docker inspect nas-metadata_worker-1 --format '{{json .State.Health}}'
```

Controleer of de healthcheck `python3` gebruikt.

## Scanner doet niets

```bash
./logs
./status
```

## Worker zegt dat er al een worker draait

Controleer locks en heartbeats:

```bash
./status
```

## DLQ groeit

```bash
./dlq
```

## Noodoplossing locks

```bash
./cleanlocks
```
"""


def page_documentation_generator(generator_analysis):
    md = ["# Documentatiegenerator\n\n"]

    md.append("De documentatiegenerator maakt documentatie op basis van bronbestanden.\n\n")

    md.append("## Output\n\n")
    md.append("- `docs/DOCUMENTATIE.md`\n")
    md.append("- `docs/DOCUMENTATIE.docx`\n")
    md.append("- `docs/wiki/*.md`\n")
    md.append("- `docs/generated/*.json`\n\n")

    md.append("## Self-documentation\n\n")
    md.append("De generator analyseert ook zichzelf. Daardoor verschijnt nieuwe generatorcode automatisch in deze documentatie.\n\n")

    md.append("## Functies\n\n")
    for fn in generator_analysis["functions"]:
        args = ", ".join(fn["args"])
        md.append("- `" + fn["name"] + "(" + args + ")` op regel `" + str(fn["line"]) + "`\n")

    return "".join(md)


def page_sources(root, files):
    md = ["# Bronbestanden\n\n"]

    for file in files:
        text = read_text(root / file)
        md.append("## `" + file + "`\n\n")
        if not text:
            md.append("_Bestand ontbreekt of is leeg._\n\n")
            continue

        lang = ""
        if file.endswith(".py"):
            lang = "python"
        elif file.endswith(".yml") or file.endswith(".yaml"):
            lang = "yaml"
        elif file.endswith(".sql"):
            lang = "sql"
        elif "Dockerfile" in file:
            lang = "dockerfile"
        else:
            lang = "bash"

        md.append(code_block(text, lang))
        md.append("\n")

    return "".join(md)
