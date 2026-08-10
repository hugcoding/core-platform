from __future__ import annotations

import hashlib
import json
import logging
import re
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree


EXTRACTOR_VERSION = "date-evidence-v1"
SUPPORTED_EXTENSIONS = {"docx", "xlsx", "pdf"}
_DCTERMS = "http://purl.org/dc/terms/"
_PDF_DATE = re.compile(
    r"^(?:D:)?(?P<year>\d{4})(?P<month>\d{2})?(?P<day>\d{2})?"
    r"(?P<hour>\d{2})?(?P<minute>\d{2})?(?P<second>\d{2})?"
    r"(?:(?P<z>Z)(?:00'?00'?|')?|(?P<sign>[+-])(?P<offhour>\d{2})'?"
    r"(?P<offminute>\d{2})?'?)?$"
)


def _temporal_value(raw_value: str) -> dict[str, Any]:
    raw = raw_value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        match = _PDF_DATE.match(raw)
        if not match:
            raise ValueError(f"unsupported embedded date: {raw!r}")
        values = match.groupdict()
        parsed = datetime(
            int(values["year"]), int(values["month"] or 1),
            int(values["day"] or 1), int(values["hour"] or 0),
            int(values["minute"] or 0), int(values["second"] or 0),
        )
        if values["z"]:
            parsed = parsed.replace(tzinfo=timezone.utc)
        elif values["sign"]:
            minutes = int(values["offhour"]) * 60 + int(values["offminute"])
            if values["sign"] == "-":
                minutes *= -1
            parsed = parsed.replace(tzinfo=timezone(timedelta(minutes=minutes)))

    local_value = parsed.replace(tzinfo=None).isoformat()
    if parsed.tzinfo is None:
        return {
            "value_at": None,
            "local_value": local_value,
            "timezone_offset_minutes": None,
            "timezone_status": "absent",
            "confidence": "low",
        }
    offset = parsed.utcoffset() or timedelta(0)
    return {
        "value_at": parsed.astimezone(timezone.utc).isoformat(),
        "local_value": local_value,
        "timezone_offset_minutes": int(offset.total_seconds() / 60),
        "timezone_status": "utc" if offset == timedelta(0) else "explicit_offset",
        "confidence": "medium",
    }


def _evidence(date_type: str, source_type: str, source_field: str,
              raw_value: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    temporal = _temporal_value(raw_value)
    return {
        "evidence_scope": "content",
        "date_type": date_type,
        "source_type": source_type,
        "source_field": source_field,
        "raw_value": raw_value,
        **temporal,
        "extractor_version": EXTRACTOR_VERSION,
        "details": details or {},
    }


def _office_evidence(path: Path, extension: str) -> list[dict[str, Any]]:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("docProps/core.xml")
    root = ElementTree.fromstring(xml)
    source_type = "office_core_properties"
    result = []
    for date_type, field in (("created", "created"), ("modified", "modified")):
        node = root.find(f"{{{_DCTERMS}}}{field}")
        if node is not None and (node.text or "").strip():
            result.append(_evidence(
                date_type, source_type, f"dcterms:{field}", node.text.strip(),
                {"container": "ooxml", "extension": extension},
            ))
    return result


def _pdf_evidence(path: Path, pdf_reader_factory: Callable[[Path], Any] | None) -> list[dict[str, Any]]:
    # pypdf can recover useful metadata from damaged object streams, but emits
    # hundreds of warnings for a single file. CORE reports file-level failures.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    if pdf_reader_factory is None:
        from pypdf import PdfReader
        pdf_reader_factory = PdfReader
    reader = pdf_reader_factory(path)
    if getattr(reader, "is_encrypted", False):
        try:
            unlocked = reader.decrypt("")
        except Exception as exc:
            raise PermissionError("password-protected PDF") from exc
        if not unlocked:
            raise PermissionError("password-protected PDF")
    metadata = reader.metadata or {}
    result = []
    for date_type, key in (("created", "/CreationDate"), ("modified", "/ModDate")):
        raw = metadata.get(key)
        if raw is not None and str(raw).strip():
            result.append(_evidence(
                date_type, "pdf_info_dictionary", key, str(raw).strip(),
                {"container": "pdf"},
            ))
    try:
        xmp = getattr(reader, "xmp_metadata", None)
    except Exception:
        xmp = None
    if xmp:
        for date_type, attribute, field in (
            ("created", "xmp_create_date", "xmp:CreateDate"),
            ("modified", "xmp_modify_date", "xmp:ModifyDate"),
        ):
            try:
                value = getattr(xmp, attribute, None)
            except Exception:
                value = None
            values = value if isinstance(value, (list, tuple)) else [value]
            for item in values:
                if item is not None and str(item).strip():
                    raw = item.isoformat() if isinstance(item, datetime) else str(item).strip()
                    result.append(_evidence(
                        date_type, "pdf_xmp", field, raw,
                        {"container": "pdf", "metadata_packet": "xmp"},
                    ))
    return result


def extract_date_evidence(path: Path, *, extension: str | None = None,
                          pdf_reader_factory: Callable[[Path], Any] | None = None) -> list[dict[str, Any]]:
    ext = (extension or path.suffix.lstrip(".")).lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return []
    if ext in {"docx", "xlsx"}:
        return _office_evidence(path, ext)
    return _pdf_evidence(path, pdf_reader_factory)


def idempotency_key(file_id: int, content_sha256: str, evidence: dict[str, Any]) -> str:
    scope = evidence.get("evidence_scope", "content")
    identity = {
        "evidence_scope": scope,
        "subject": content_sha256 if scope == "content" else int(file_id),
        "date_type": evidence["date_type"],
        "source_type": evidence["source_type"],
        "source_field": evidence["source_field"],
        "raw_value": evidence["raw_value"],
        "extractor_version": evidence["extractor_version"],
    }
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
