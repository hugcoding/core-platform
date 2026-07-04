from tools.docs.io_utils import code_block


def page_core(core):
    md = ["# CORE Manifest\n\n"]

    if not core["manifest_exists"]:
        md.append("`core/core.yaml` ontbreekt.\n")
        return "".join(md)

    platform = core.get("platform", {})
    md.append("## Platform\n\n")
    for key, value in platform.items():
        md.append("- `" + str(key) + "`: `" + str(value) + "`\n")

    md.append("\n## Modules\n\n")
    modules = core.get("modules", {})
    if modules:
        for name, cfg in modules.items():
            md.append("### `" + str(name) + "`\n\n")
            if isinstance(cfg, dict):
                for key, value in cfg.items():
                    md.append("- `" + str(key) + "`: `" + str(value) + "`\n")
            md.append("\n")
    else:
        md.append("_Geen modules gevonden._\n\n")

    md.append("## Engines\n\n")
    engines = core.get("engines", {})
    if engines:
        for name, cfg in engines.items():
            md.append("### `" + str(name) + "`\n\n")
            if isinstance(cfg, dict):
                for key, value in cfg.items():
                    md.append("- `" + str(key) + "`: `" + str(value) + "`\n")
            md.append("\n")
    else:
        md.append("_Geen engines gevonden._\n\n")

    md.append("## Bron: core/core.yaml\n\n")
    md.append(code_block(core.get("raw", ""), "yaml"))
    return "".join(md)


def page_rfc(rfc):
    md = ["# RFC's\n\n"]

    if not rfc["rfc_dir_exists"]:
        md.append("`docs/rfc` ontbreekt.\n")
        return "".join(md)

    md.append("Aantal RFC's: `" + str(rfc["count"]) + "`\n\n")

    for item in rfc["items"]:
        md.append("## " + item["id"] + "\n\n")
        md.append("- Titel: `" + item["title"] + "`\n")
        md.append("- Status: `" + item["status"] + "`\n")
        md.append("- Bestand: `" + item["file"] + "`\n")
        md.append("- Regels: `" + str(item["line_count"]) + "`\n\n")
        md.append(code_block(item["content"], "markdown"))
        md.append("\n")

    return "".join(md)


def page_database_views(views):
    md = ["# Database Views\n\n"]

    if not views["views_dir_exists"]:
        md.append("`database/views` ontbreekt.\n")
        return "".join(md)

    md.append("Aantal SQL-viewbestanden: `" + str(views["count"]) + "`\n\n")

    for item in views["items"]:
        md.append("## `" + item["file"] + "`\n\n")
        md.append("- Regels: `" + str(item["line_count"]) + "`\n")
        if item["views"]:
            md.append("- Views:\n")
            for view in item["views"]:
                md.append("  - `" + view + "`\n")
        if item["drops"]:
            md.append("- Drops:\n")
            for drop in item["drops"]:
                md.append("  - `" + drop + "`\n")
        md.append("\n")
        md.append(code_block(item["content"], "sql"))
        md.append("\n")

    return "".join(md)


def page_standards(standards):
    from tools.docs.io_utils import code_block

    md = ["# CORE Standards\n\n"]

    if not standards["standards_dir_exists"]:
        md.append("`docs/standards` ontbreekt.\n")
        return "".join(md)

    md.append("Aantal standaarden: `" + str(standards["count"]) + "`\n\n")

    for item in standards["items"]:
        md.append("## " + item["title"] + "\n\n")
        md.append("- Bestand: `" + item["file"] + "`\n")
        md.append("- Regels: `" + str(item["line_count"]) + "`\n\n")
        md.append(code_block(item["content"], "markdown"))
        md.append("\n")

    return "".join(md)
