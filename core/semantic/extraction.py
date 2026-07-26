from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable, Iterable


SUPPORTED_EXTENSIONS = {".docx", ".pdf"}


def _docx_text(path: Path) -> tuple[str, int]:
    from docx import Document

    document = Document(path)
    blocks = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            blocks.append("\t".join(cell.text for cell in row.cells))
    return "\n".join(blocks), 0


def _pdf_text(path: Path) -> tuple[str, int]:
    from pypdf import PdfReader

    reader = PdfReader(path)
    if reader.is_encrypted:
        raise ValueError("encrypted PDF")
    return "\n".join(page.extract_text() or "" for page in reader.pages), len(reader.pages)


def extract_statistics(
    path: Path,
    *,
    docx_loader: Callable[[Path], tuple[str, int]] = _docx_text,
    pdf_loader: Callable[[Path], tuple[str, int]] = _pdf_text,
) -> dict[str, Any]:
    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"unsupported extension: {extension or '[none]'}")
    if not path.is_file():
        raise FileNotFoundError(path)

    text, pages = (docx_loader if extension == ".docx" else pdf_loader)(path)
    normalized = " ".join(text.split())
    return {
        "extension": extension.removeprefix("."),
        "size_bytes": path.stat().st_size,
        "characters": len(normalized),
        "words": len(normalized.split()) if normalized else 0,
        "pages": pages or None,
        "has_extractable_text": bool(normalized),
    }


def run_manifest(
    manifest_path: Path,
    *,
    extractor: Callable[[Path], dict[str, Any]] = extract_statistics,
) -> Iterable[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("processing") != "local_only":
        raise ValueError("pilot manifest must require local_only processing")
    if manifest.get("embedding_enabled") is not False:
        raise ValueError("embeddings must be disabled for the extraction pilot")

    for item in manifest["files"]:
        if item["approval"] != "approved":
            yield {
                "file_id": item["file_id"],
                "status": "skipped",
                "reason": f"approval={item['approval']}",
            }
            continue

        try:
            statistics = extractor(Path(item["path"]))
        except Exception as exc:
            yield {
                "file_id": item["file_id"],
                "status": "error",
                "error_type": type(exc).__name__,
                "reason": str(exc),
            }
            continue

        yield {"file_id": item["file_id"], "status": "extracted", **statistics}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="semantic-pilot-extract")
    parser.add_argument(
        "--manifest",
        default="/app/project/pilots/scrum-57-documents-v1.json",
    )
    args = parser.parse_args(argv)

    errors = 0
    for result in run_manifest(Path(args.manifest)):
        print(json.dumps(result, ensure_ascii=False))
        errors += result["status"] == "error"
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
