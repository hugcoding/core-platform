#!/usr/bin/env python3
"""Build a non-mutating SCRUM-61 migration proposal from the review manifest."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

POINTER_EXTENSIONS = {"gdoc", "gform", "gsheet", "gtable"}


def propose(row: dict[str, str]) -> tuple[str, str, str]:
    """Return proposal action, readiness, and rationale."""
    extension = row["representative_extension"]
    review_class = row["review_class"]
    path = row["representative_path"].lower()

    if not row.get("hash_content"):
        return "manual_review", "blocked_missing_hash", "exact content identity is missing"
    if review_class == "personal_document":
        if row["sensitivity"] == "sensitive":
            return (
                "document_sensitive",
                "ready_for_copy_plan",
                "migrate separately; semantic indexing remains blocked pending policy",
            )
        return "document_standard", "ready_for_copy_plan", "eligible for the standard document copy plan"
    if review_class == "deferred_media":
        return "deferred_media", "deferred", "media migration belongs to a later phase"
    if review_class == "project_or_technical":
        return "retain_project_technical", "retain_in_source", "preserve in inventory; exclude from document wave"
    if extension == "eps" and "/cisco icons/" in path:
        return (
            "retain_project_technical",
            "retain_in_source",
            "Cisco icon-library asset; exclude from document wave",
        )
    if extension in POINTER_EXTENSIONS or extension == "gslides":
        return (
            "recover_cloud_pointer",
            "manual_recovery_required",
            "pointer file may not contain the original cloud document",
        )
    if row["category"] == "archive_review":
        return "inspect_archive", "manual_inspection_required", "archive contents require inspection"
    if row["category"] == "secret":
        return "secure_manual_review", "manual_security_review", "credential-like content requires secure handling"
    return "manual_review", "manual_classification_required", "intent remains uncertain"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a read-only migration proposal.")
    parser.add_argument("--manifest", default="latest", help="Review manifest CSV path, or 'latest'")
    parser.add_argument("--dry-run", action="store_true", required=True)
    return parser


def resolve_manifest(root: Path, value: str) -> Path:
    export_dir = root / "project" / "exports" / "migration-inventory"
    if value == "latest":
        manifests = sorted(export_dir.glob("review-manifest-*.csv"))
        if not manifests:
            raise FileNotFoundError("No document review manifest found.")
        return manifests[-1]
    path = Path(value)
    return path if path.is_absolute() else root / path


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    try:
        manifest_path = resolve_manifest(root, args.manifest)
        with manifest_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except (FileNotFoundError, OSError) as exc:
        print(f"Migration proposal failed: {exc}", file=sys.stderr)
        return 1

    required = {
        "hash_content",
        "category",
        "sensitivity",
        "representative_extension",
        "review_class",
        "representative_path",
    }
    if not rows or not required.issubset(rows[0]):
        print("Migration proposal failed: review manifest is empty or incompatible.", file=sys.stderr)
        return 1

    proposed: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    for row in rows:
        action, readiness, reason = propose(row)
        item = dict(row)
        item["proposal_action"] = action
        item["copy_readiness"] = readiness
        item["proposal_reason"] = reason
        proposed.append(item)
        counts[action] += 1

    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    export_dir = root / "project" / "exports" / "migration-inventory"
    export_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = list(proposed[0])

    proposal_path = export_dir / f"migration-proposal-{timestamp}.csv"
    standard_path = export_dir / f"document-standard-{timestamp}.csv"
    sensitive_path = export_dir / f"document-sensitive-{timestamp}.csv"
    manual_path = export_dir / f"manual-review-{timestamp}.csv"
    report_path = export_dir / f"migration-proposal-{timestamp}.md"

    write_csv(proposal_path, proposed, fieldnames)
    write_csv(
        standard_path,
        [row for row in proposed if row["proposal_action"] == "document_standard"],
        fieldnames,
    )
    write_csv(
        sensitive_path,
        [row for row in proposed if row["proposal_action"] == "document_sensitive"],
        fieldnames,
    )
    write_csv(
        manual_path,
        [
            row
            for row in proposed
            if row["proposal_action"]
            in {"manual_review", "inspect_archive", "recover_cloud_pointer", "secure_manual_review"}
        ],
        fieldnames,
    )

    report = [
        "# SCRUM-61 migration proposal",
        "",
        f"- Generated: `{datetime.now().astimezone().isoformat()}`",
        f"- Input: `{manifest_path.name}`",
        "- Mode: **read-only dry-run**",
        f"- Exact content groups: **{len(proposed)}**",
        f"- Standard documents: **{counts['document_standard']}**",
        f"- Sensitive documents: **{counts['document_sensitive']}**",
        f"- Retained project/technical: **{counts['retain_project_technical']}**",
        f"- Archives to inspect: **{counts['inspect_archive']}**",
        f"- Cloud pointers to recover: **{counts['recover_cloud_pointer']}**",
        f"- Secure manual review: **{counts['secure_manual_review']}**",
        f"- Other manual review: **{counts['manual_review']}**",
        f"- Deferred media: **{counts['deferred_media']}**",
        "",
        "Every input group remains represented. `ready_for_copy_plan` is not permission",
        "to copy: target paths, collision policy, verification, and approval are still required.",
        "",
        "No files or database records were changed.",
    ]
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    (export_dir / "proposal-latest.md").write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")

    print("SCRUM-61 read-only migration proposal complete")
    print(f"Report: {report_path.relative_to(root)}")
    print(f"Proposal: {proposal_path.relative_to(root)}")
    print(f"Standard documents: {standard_path.relative_to(root)}")
    print(f"Sensitive documents: {sensitive_path.relative_to(root)}")
    print(f"Manual review: {manual_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
