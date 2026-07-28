#!/usr/bin/env python3
"""Locally extract and classify modern golden documents without retaining raw text."""

from __future__ import annotations

import argparse
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from core.exports.csv_format import dict_reader, write_dict_rows


CATEGORY_TERMS = {
    "gevoelig/financiën": (
        "belasting", "aanslag", "bankrekening", "rekeningnummer", "hypotheek",
        "verzekering", "jaaropgave", "pensioen", "financieel",
    ),
    "gevoelig/gezondheid": (
        "huisarts", "ziekenhuis", "diagnose", "medisch", "medicatie",
        "gezondheid", "behandeling", "zorgverlener", "wmo",
    ),
    "gevoelig/identiteit": (
        "paspoort", "rijbewijs", "identiteitskaart", "burgerservicenummer", "bsn",
    ),
    "gevoelig/werk_en_inkomen": (
        "arbeidsovereenkomst", "werkgever", "salaris", "loonstrook",
        "sollicitatie", "curriculum vitae", "functioneringsgesprek",
    ),
    "documenten/studie": (
        "opleiding", "studie", "module", "les", "opdracht", "examen",
        "scriptie", "hoofdstuk", "student", "docent", "ncoi",
    ),
    "documenten/werk": (
        "projectplan", "vergadering", "notulen", "werkoverleg", "organisatie",
        "management", "proces", "klant", "offerte",
    ),
    "documenten/wonen": (
        "woning", "verbouwing", "energieleverancier", "gevel", "keuken",
        "badkamer", "huur", "koopakte", "kadaster",
    ),
    "documenten/administratie": (
        "factuur", "aankoop", "garantie", "abonnement", "overeenkomst",
        "bevestiging", "betaling", "bon", "nota",
    ),
    "documenten/persoonlijk": (
        "familie", "verjaardag", "vakantie", "persoonlijk", "uitnodiging",
        "wensenlijst", "reis", "ticket",
    ),
    "projecten": (
        "source code", "database", "software", "server", "netwerk",
        "openvpn", "uml", "xml", "api", "configuratie",
    ),
}


def normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def extract_text(path: Path, route: str) -> tuple[str, int | None]:
    if route == "plain-text":
        try:
            return path.read_text(encoding="utf-8"), None
        except UnicodeDecodeError:
            return path.read_text(encoding="cp1252"), None
    if route == "pypdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("encrypted PDF")
        return "\n".join(page.extract_text() or "" for page in reader.pages), len(reader.pages)
    if route == "python-docx":
        from docx import Document

        document = Document(path)
        blocks = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                blocks.append(" ".join(cell.text for cell in row.cells))
        return "\n".join(blocks), None
    if route == "openpyxl":
        from openpyxl import load_workbook

        workbook = load_workbook(path, read_only=True, data_only=True)
        values = []
        for sheet in workbook.worksheets:
            values.append(sheet.title)
            for row in sheet.iter_rows(values_only=True):
                values.extend(str(value) for value in row if value is not None)
        workbook.close()
        return "\n".join(values), None
    if route == "python-pptx":
        from pptx import Presentation

        presentation = Presentation(path)
        values = []
        for slide in presentation.slides:
            values.extend(
                shape.text for shape in slide.shapes
                if hasattr(shape, "text") and shape.text
            )
        return "\n".join(values), len(presentation.slides)
    if route == "rtf":
        from striprtf.striprtf import rtf_to_text

        return rtf_to_text(path.read_text(encoding="cp1252")), None
    if route == "odf":
        from odf import teletype
        from odf.opendocument import load

        document = load(str(path))
        return teletype.extractText(document), None
    raise ValueError(f"unsupported extraction route: {route}")


def term_hits(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if re.search(rf"\b{re.escape(term)}\b", text)]


def classify_content(text: str, filename: str, source_path: str) -> tuple[str, str, str]:
    normalized = normalize(text)
    name = normalize(filename)
    path = normalize(source_path)
    scores = {}
    evidence = {}
    for category, terms in CATEGORY_TERMS.items():
        content_hits = term_hits(normalized, terms)
        name_hits = term_hits(name, terms)
        path_hits = term_hits(path, terms)
        score = len(content_hits) * 5 + len(name_hits) * 2 + len(path_hits)
        scores[category] = score
        evidence[category] = {
            "inhoud": content_hits,
            "bestandsnaam": name_hits,
            "bronpad": path_hits,
        }
    ordered = sorted(scores, key=lambda category: (-scores[category], category))
    best = ordered[0]
    margin = scores[best] - scores[ordered[1]]
    if scores[best] == 0:
        return "documenten/uitzoeken", "low", "geen inhoudssignalen"
    confidence = "high" if scores[best] >= 10 and margin >= 3 else "medium" if margin > 0 else "low"
    reasons = evidence[best]
    return best, confidence, (
        f"score={scores[best]}; margin={margin}; "
        f"inhoud={','.join(reasons['inhoud']) or '-'}; "
        f"bestandsnaam={','.join(reasons['bestandsnaam']) or '-'}; "
        f"bronpad={','.join(reasons['bronpad']) or '-'}"
    )


def process_row(row: dict[str, str]) -> dict[str, str]:
    result = {
        **row,
        "extraction_result": "",
        "extraction_error": "",
        "characters": "",
        "words": "",
        "pages_or_slides": "",
    }
    if row["extraction_status"] != "ready_for_local_extraction":
        result["extraction_result"] = "skipped"
        return result
    try:
        text, pages = extract_text(Path(row["golden_path"]), row["extraction_route"])
        normalized = normalize(text)
        category, confidence, reasons = classify_content(
            normalized, row["filename"], row["golden_path"]
        )
        needs_ocr = row["extraction_route"] == "pypdf" and not normalized and bool(pages)
        result.update(
            {
                "extraction_result": "needs_ocr" if needs_ocr else "extracted",
                "extraction_error": "",
                "characters": str(len(normalized)),
                "words": str(len(normalized.split())) if normalized else "0",
                "pages_or_slides": str(pages or ""),
                "content_category": category,
                "category_confidence": confidence,
                "category_reasons": reasons,
                "proposed_target_path": "",
            }
        )
    except Exception as exc:
        result.update(
            {
                "extraction_result": "error",
                "extraction_error": f"{type(exc).__name__}: {exc}",
                "characters": "0",
                "words": "0",
                "pages_or_slides": "",
            }
        )
    return result


def resolve_manifest(root: Path, value: str) -> Path:
    export_dir = root / "project" / "exports" / "migration-inventory"
    if value == "latest":
        manifests = sorted(export_dir.glob("classification-inventory-*.csv"))
        if not manifests:
            raise FileNotFoundError("No classification inventory found.")
        return manifests[-1]
    path = Path(value)
    return path if path.is_absolute() else root / path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract and classify golden documents locally.")
    parser.add_argument("--manifest", default="latest")
    parser.add_argument("--dry-run", action="store_true", required=True)
    args = parser.parse_args(argv)
    root = Path("/app")
    try:
        manifest_path = resolve_manifest(root, args.manifest)
        with manifest_path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(dict_reader(handle))
    except (FileNotFoundError, OSError) as exc:
        print(f"Classification extraction failed: {exc}")
        return 1

    results = [process_row(row) for row in rows]
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    export_dir = root / "project" / "exports" / "migration-inventory"
    output_path = export_dir / f"classification-results-{timestamp}.csv"
    report_path = export_dir / f"classification-results-{timestamp}.md"
    write_dict_rows(output_path, results, list(results[0]))
    outcomes = Counter(row.get("extraction_result", "") for row in results)
    categories = Counter(row.get("content_category", "") for row in results)
    report = [
        "# SCRUM-61 lokale inhoudsclassificatie", "",
        f"- Gegenereerd: `{datetime.now().astimezone().isoformat()}`",
        "- Modus: **lokaal, alleen-lezen, zonder embeddings**",
        f"- Extracted: **{outcomes['extracted']}**",
        f"- OCR vereist: **{outcomes['needs_ocr']}**",
        f"- Conversie/overgeslagen: **{outcomes['skipped']}**",
        f"- Fouten: **{outcomes['error']}**",
        "", "## Voorgestelde categorieën", "", "| Categorie | Bestanden |", "|---|---:|",
    ]
    report.extend(
        f"| `{category}` | {count} |"
        for category, count in sorted(categories.items())
        if category
    )
    report.extend([
        "", "Volledige documenttekst is niet opgeslagen.",
        "Er zijn geen bestanden, mappen of databaserecords gewijzigd.",
    ])
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("SCRUM-61 local classification extraction complete")
    print(f"Report: {report_path.relative_to(root)}")
    print(f"Results: {output_path.relative_to(root)}")
    return 0 if not outcomes["error"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
