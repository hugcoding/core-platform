# Documentatiegenerator

De documentatiegenerator maakt documentatie op basis van bronbestanden.

## Output

- `docs/DOCUMENTATIE.md`
- `docs/DOCUMENTATIE.docx`
- `docs/wiki/*.md`
- `docs/generated/*.json`

## Self-documentation

De generator analyseert ook zichzelf. Daardoor verschijnt nieuwe generatorcode automatisch in deze documentatie.

## Functies

- `build_analysis()` op regel `42`
- `render_json_outputs(analysis)` op regel `66`
- `render_wiki_pages(analysis)` op regel `78`
- `main()` op regel `110`
