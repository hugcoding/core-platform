#!/usr/bin/env python3
"""Create a second, document-focused review manifest from SCRUM-61 inventory."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from core.exports.csv_format import dict_reader, write_dict_rows

DOCUMENT_EXTENSIONS = {
    "doc",
    "docm",
    "docx",
    "eml",
    "htm",
    "html",
    "md",
    "msg",
    "odp",
    "ods",
    "odt",
    "pdf",
    "ppt",
    "pptm",
    "pptx",
    "rtf",
    "txt",
    "vsd",
    "vsdx",
    "xls",
    "xlsm",
    "xlsx",
    "xml",
}

TECHNICAL_EXTENSIONS = {
    "bat",
    "class",
    "cmd",
    "com",
    "dll",
    "dmp",
    "dump",
    "exe",
    "ibd",
    "img",
    "iso",
    "java",
    "jcd",
    "jcp",
    "jcu",
    "jcw",
    "msi",
    "properties",
    "pyc",
    "pyo",
    "sql",
    "sys",
    "vdi",
    "vmdk",
    "vss",
    "vst",
}

POINTER_EXTENSIONS = {"gdoc", "gform", "gsheet", "gtable"}


def extension_for(path: str) -> str:
    filename = path.rsplit("/", 1)[-1]
    if "." not in filename or filename.endswith("."):
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def classify_review(row: dict[str, str]) -> tuple[str, str]:
    category = row["category"]
    action = row["migration_action"]
    extension = extension_for(row["representative_path"])

    if category == "personal_media_candidate":
        return "deferred_media", "media is retained for a later migration phase"
    if category == "personal_document_candidate" or extension in DOCUMENT_EXTENSIONS:
        return "personal_document", "recognized document or communication format"
    if category == "secret":
        return "manual_review", "credential-like content requires explicit handling"
    if category == "archive_review":
        return "manual_review", "archive contents must be inspected before migration"
    if extension in POINTER_EXTENSIONS:
        return "manual_review", "cloud pointer may not contain the original document"
    if category in {"system_or_temporary", "software_or_system_artifact"}:
        return "project_or_technical", "known technical or temporary artifact"
    if extension in TECHNICAL_EXTENSIONS:
        return "project_or_technical", "recognized development, software, or system format"
    if action == "already_in_target":
        return "manual_review", "exact content already exists in the target"
    return "manual_review", "format or intent is not yet reliable enough to classify"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a document-focused review manifest.")
    parser.add_argument(
        "--manifest",
        default="latest",
        help="First manifest CSV path, or 'latest' (default)",
    )
    parser.add_argument("--dry-run", action="store_true", required=True)
    return parser


def resolve_manifest(root: Path, value: str) -> Path:
    export_dir = root / "project" / "exports" / "migration-inventory"
    if value == "latest":
        manifests = sorted(export_dir.glob("manifest-*.csv"))
        if not manifests:
            raise FileNotFoundError("No first migration manifest found.")
        return manifests[-1]
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    try:
        manifest_path = resolve_manifest(root, args.manifest)
        with manifest_path.open(newline="", encoding="utf-8") as handle:
            rows = list(dict_reader(handle))
    except (FileNotFoundError, OSError) as exc:
        print(f"Migration review failed: {exc}", file=sys.stderr)
        return 1

    required = {
        "representative_file_id",
        "category",
        "sensitivity",
        "migration_action",
        "representative_path",
    }
    if not rows or not required.issubset(rows[0]):
        print("Migration review failed: the first manifest is empty or incompatible.", file=sys.stderr)
        return 1

    reviewed: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    for row in rows:
        review_class, review_reason = classify_review(row)
        item = dict(row)
        item["representative_extension"] = extension_for(row["representative_path"]) or "[none]"
        item["review_class"] = review_class
        item["review_reason"] = review_reason
        reviewed.append(item)
        counts[review_class] += 1

    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    export_dir = root / "project" / "exports" / "migration-inventory"
    export_dir.mkdir(parents=True, exist_ok=True)
    review_path = export_dir / f"review-manifest-{timestamp}.csv"
    report_path = export_dir / f"review-manifest-{timestamp}.md"
    fieldnames = list(reviewed[0])
    write_dict_rows(review_path, reviewed, fieldnames)

    report = [
        "# SCRUM-61 document review manifest",
        "",
        f"- Generated: `{datetime.now().astimezone().isoformat()}`",
        f"- Input: `{manifest_path.name}`",
        "- Mode: **read-only dry-run**",
        f"- Exact content groups: **{len(reviewed)}**",
        f"- Personal documents: **{counts['personal_document']}**",
        f"- Project or technical: **{counts['project_or_technical']}**",
        f"- Manual review: **{counts['manual_review']}**",
        f"- Deferred media: **{counts['deferred_media']}**",
        "",
        "Every input group remains present. Folder names such as `backup`, `archive`,",
        "or `CloudStation` do not determine the review class.",
        "",
        "No target paths are proposed and no files or database records were changed.",
    ]
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    (export_dir / "review-latest.md").write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")

    print("SCRUM-61 read-only document review manifest complete")
    print(f"Report: {report_path.relative_to(root)}")
    print(f"Manifest: {review_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
