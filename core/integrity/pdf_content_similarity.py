"""Read-only evidence for PDF files that are not exact byte duplicates."""

from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path
from typing import Any, Callable, Iterable


SCHEMA_VERSION = "pdf-content-similarity-v1"
METADATA_FIELDS = ("/Title", "/Author", "/Creator", "/Producer", "/CreationDate", "/ModDate")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalized_text(value: str) -> str:
    return " ".join(value.split())


def _pdf_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return [_pdf_value(item) for item in value]
    return str(value)


def _has_signature(reader: Any) -> bool:
    try:
        fields = reader.get_fields() or {}
    except Exception:
        return False
    return any(str(field.get("/FT") or "") == "/Sig" for field in fields.values())


def analyze_pdf(
    path: Path,
    *,
    reader_factory: Callable[[io.BytesIO], Any] | None = None,
) -> dict[str, Any]:
    """Create bounded evidence without exposing extracted document text."""
    source = Path(path)
    if source.suffix.casefold() != ".pdf":
        raise ValueError("only PDF files are supported")
    content = source.read_bytes()
    if reader_factory is None:
        logging.getLogger("pypdf").setLevel(logging.ERROR)
        from pypdf import PdfReader

        reader_factory = PdfReader
    reader = reader_factory(io.BytesIO(content))
    if bool(getattr(reader, "is_encrypted", False)):
        try:
            unlocked = reader.decrypt("")
        except Exception as exc:
            raise PermissionError("password-protected PDF") from exc
        if not unlocked:
            raise PermissionError("password-protected PDF")

    page_hashes: list[str] = []
    page_characters: list[int] = []
    warnings: list[str] = []
    normalized_pages: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            normalized = _normalized_text(page.extract_text() or "")
        except Exception as exc:
            normalized = ""
            warnings.append(f"page_{page_number}:{type(exc).__name__}")
        normalized_pages.append(normalized)
        page_hashes.append(_sha256(normalized.encode("utf-8")))
        page_characters.append(len(normalized))

    normalized_document = "\n".join(normalized_pages)
    metadata = getattr(reader, "metadata", None) or {}
    trailer = getattr(reader, "trailer", None) or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "path": str(source),
        "filename": source.name,
        "size_bytes": len(content),
        "content_sha256": _sha256(content),
        "page_count": len(normalized_pages),
        "page_text_sha256": page_hashes,
        "page_text_characters": page_characters,
        "normalized_text_sha256": _sha256(normalized_document.encode("utf-8")),
        "normalized_text_characters": len(normalized_document),
        "has_extractable_text": bool(normalized_document.strip()),
        "metadata": {field.removeprefix("/"): _pdf_value(metadata.get(field)) for field in METADATA_FIELDS},
        "document_id": _pdf_value(trailer.get("/ID")),
        "has_digital_signature": _has_signature(reader),
        "extraction_warnings": warnings,
        "visual_comparison_performed": False,
        "file_mutations": False,
        "database_writes": False,
    }


def _metadata_differences(documents: list[dict[str, Any]]) -> dict[str, list[Any]]:
    fields = list(field.removeprefix("/") for field in METADATA_FIELDS) + ["document_id"]
    differences: dict[str, list[Any]] = {}
    for field in fields:
        values = [document.get(field) if field == "document_id" else document["metadata"].get(field)
                  for document in documents]
        if len({repr(value) for value in values}) > 1:
            differences[field] = values
    return differences


def _byte_differences(documents: list[dict[str, Any]], contents: list[bytes]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for left in range(len(contents)):
        for right in range(left + 1, len(contents)):
            same_size = len(contents[left]) == len(contents[right])
            pairs.append({
                "left": documents[left]["filename"],
                "right": documents[right]["filename"],
                "same_size": same_size,
                "different_byte_positions": (
                    sum(a != b for a, b in zip(contents[left], contents[right])) if same_size else None
                ),
            })
    return pairs


def analyze_pdf_group(
    paths: Iterable[Path],
    *,
    reader_factory: Callable[[io.BytesIO], Any] | None = None,
) -> dict[str, Any]:
    """Classify a group as exact, textual candidate, or non-equivalent."""
    sources = [Path(path) for path in paths]
    if len(sources) < 2:
        raise ValueError("at least two PDF files are required")
    documents = [analyze_pdf(path, reader_factory=reader_factory) for path in sources]
    contents = [path.read_bytes() for path in sources]
    full_hashes = {document["content_sha256"] for document in documents}
    page_counts = {document["page_count"] for document in documents}
    page_hashes = {tuple(document["page_text_sha256"]) for document in documents}
    text_hashes = {document["normalized_text_sha256"] for document in documents}
    safe_text_evidence = all(
        document["has_extractable_text"]
        and not document["extraction_warnings"]
        and not document["has_digital_signature"]
        for document in documents
    )
    if len(full_hashes) == 1:
        relationship, confidence = "exact_duplicate", "exact"
    elif safe_text_evidence and len(page_counts) == len(page_hashes) == len(text_hashes) == 1:
        relationship, confidence = "textually_identical_pdf_candidate", "high"
    else:
        relationship, confidence = "not_proven_equivalent", "low"
    return {
        "schema_version": SCHEMA_VERSION,
        "relationship": relationship,
        "confidence": confidence,
        "documents": documents,
        "metadata_differences": _metadata_differences(documents),
        "byte_comparisons": _byte_differences(documents, contents),
        "requires_human_review": relationship != "exact_duplicate",
        "automatic_deletion_allowed": False,
        "visual_comparison_performed": False,
        "file_mutations": False,
        "database_writes": False,
    }
