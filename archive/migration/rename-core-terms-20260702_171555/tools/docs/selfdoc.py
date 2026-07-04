def documentation_generator_page(analysis):
    md = []
    md.append("# Documentatiegenerator\n\n")
    md.append("De documentatiegenerator is onderdeel van het NAS Metadata Platform.\n\n")

    md.append("## Doel\n\n")
    md.append("- Python-bronbestanden analyseren.\n")
    md.append("- Wiki-pagina's genereren.\n")
    md.append("- Hoofddocumentatie genereren.\n")
    md.append("- JSON-analysebestanden opslaan.\n")
    md.append("- Zichzelf documenteren.\n\n")

    md.append("## Output\n\n")
    md.append("- `docs/DOCUMENTATIE.md`\n")
    md.append("- `docs/DOCUMENTATIE.docx`\n")
    md.append("- `docs/wiki/*.md`\n")
    md.append("- `docs/generated/python_analysis.json`\n\n")

    md.append("## Geanalyseerde generatorfuncties\n\n")
    for fn in analysis.get("functions", []):
        args = ", ".join(fn["args"])
        md.append("- `" + fn["name"] + "(" + args + ")` op regel `" + str(fn["line"]) + "`\n")

    md.append("\n## Ontwerpprincipe\n\n")
    md.append("De generator documenteert zichzelf. Nieuwe generatorfuncties verschijnen automatisch in deze pagina.\n")
    return "".join(md)
