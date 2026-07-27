#!/usr/bin/env python3
"""Generate a read-only document copy plan for SCRUM-61."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path, PurePosixPath


TARGET_BUCKETS = {
    "documents/administration",
    "documents/home",
    "documents/personal",
    "documents/study",
    "documents/unsorted",
    "documents/work",
    "projects",
    "sensitive/employment",
    "sensitive/finance",
    "sensitive/health",
    "sensitive/identity",
    "sensitive/other",
}

SOURCE_ROOT = "/volume1/backup/NITRO/D/data/hugo/Documents/"
TECHNICAL_FILENAMES = {
    "build.xml",
    "build-impl.xml",
    "filelist.xml",
    "manifest.mf",
    "pom.xml",
    "private.xml",
    "project.xml",
}


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def choose_bucket(row: dict[str, str]) -> tuple[str, str]:
    evidence = f"{row['representative_path']} {row.get('source_paths', '')}".casefold()
    sensitive = row["proposal_action"] == "document_sensitive"

    if sensitive or contains_any(
        evidence,
        (
            "geldzaken",
            "gezondheid & voeding",
            "officiële documenten",
            "officiele documenten",
        ),
    ):
        if contains_any(
            evidence,
            (
                "paspoort",
                "identiteit",
                "rijbewijs",
                "id-kaart",
                "idkaart",
                "officiële documenten",
                "officiele documenten",
            ),
        ):
            return "sensitive/identity", "identity keyword in source evidence"
        if contains_any(
            evidence,
            ("medisch", "gezondheid", "huisarts", "ziekenhuis", "zorg", "hapto"),
        ):
            return "sensitive/health", "health keyword in source evidence"
        if contains_any(
            evidence,
            ("arbeid", "werkgever", "salaris", "jaaropgave", "sollicit", "curriculum", "/cv", "contract"),
        ):
            return "sensitive/employment", "employment keyword in source evidence"
        if contains_any(
            evidence,
            (
                "financi",
                "geldzaken",
                "belasting",
                "bank",
                "rekening",
                "pensioen",
                "hypotheek",
                "verzekering",
            ),
        ):
            return "sensitive/finance", "financial keyword in source evidence"
        return "sensitive/other", "sensitive document without a reliable subcategory"

    if contains_any(evidence, ("/studie/", "/study/", "opleiding", "school", "ncoi", "cursus")):
        return "documents/study", "study keyword in source evidence"
    if contains_any(evidence, ("/werk/", "/work/", "werkgever", "sollicit", "curriculum", "/cv")):
        return "documents/work", "work keyword in source evidence"
    if contains_any(evidence, ("woning", "verbouwing", "huis", "home", "hypotheek")):
        return "documents/home", "home keyword in source evidence"
    if contains_any(
        evidence,
        (
            "administratie",
            "abonnement",
            "factuur",
            "facturen",
            "bonnen",
            "aankoop",
            "garantie",
            "verzekering",
            "belasting",
        ),
    ):
        return "documents/administration", "administration keyword in source evidence"
    if contains_any(
        evidence,
        (
            "persoonlijk",
            "personal",
            "familie",
            "family",
            "adressen",
            "adresboek",
            "contactpersonen",
            "/tabitha/",
            "/opvang/",
        ),
    ):
        return "documents/personal", "personal keyword in source evidence"
    return "documents/unsorted", "no reliable target category"


def safe_filename(path: str) -> str:
    name = PurePosixPath(path).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).rstrip(" .")
    if not name:
        return "unnamed"
    stem = name.split(".", 1)[0].casefold()
    if stem in {"con", "prn", "aux", "nul"} or re.fullmatch(r"(com|lpt)[1-9]", stem):
        name = "_" + name
    return name


def source_paths(row: dict[str, str]) -> list[str]:
    try:
        values = json.loads(row.get("source_paths", "[]"))
    except json.JSONDecodeError:
        values = []
    paths = [value for value in values if isinstance(value, str)]
    if row["representative_path"] not in paths:
        paths.append(row["representative_path"])
    return paths


def meaningful_relative_path(row: dict[str, str]) -> PurePosixPath:
    candidates: list[tuple[tuple[int, int, int], PurePosixPath]] = []
    for full_path in source_paths(row):
        if full_path.startswith(SOURCE_ROOT):
            relative = PurePosixPath(full_path[len(SOURCE_ROOT) :])
        else:
            relative = PurePosixPath(full_path).name
            relative = PurePosixPath(relative)
        parts = list(relative.parts)
        wrapper = bool(parts and parts[0].casefold() == "cloudstation")
        if wrapper:
            parts = parts[1:]
        if not parts:
            continue
        cleaned = PurePosixPath(*parts)
        # Prefer a non-CloudStation source, then the path with most context.
        score = (0 if wrapper else 1, len(parts), len(str(cleaned)))
        candidates.append((score, cleaned))
    if not candidates:
        return PurePosixPath(safe_filename(row["representative_path"]))
    return max(candidates, key=lambda item: item[0])[1]


def is_technical_document(row: dict[str, str]) -> bool:
    filename = PurePosixPath(row["representative_path"]).name.casefold()
    evidence = " ".join(source_paths(row)).casefold()
    if filename in TECHNICAL_FILENAMES:
        return True
    if "/documents/systeem/" in evidence:
        return True
    return contains_any(evidence, ("/nbproject/", "/.idea/", "/.vscode/")) and filename.endswith(
        (".xml", ".properties", ".html", ".htm")
    )


def remove_bucket_marker(relative: PurePosixPath, bucket: str) -> PurePosixPath:
    parts = list(relative.parts)
    aliases = {
        "documents/study": {"studie", "study", "opleiding", "school"},
        "documents/work": {"werk", "work"},
        "documents/home": {"woning", "huis", "home"},
        "documents/administration": {"administratie", "administratie (archief)"},
        "sensitive/finance": {"financiën", "financien", "finance"},
        "sensitive/employment": {"werk", "work", "personeel"},
        "sensitive/health": {"zorg", "medisch", "gezondheid"},
        "sensitive/identity": {"identiteit", "identity"},
    }.get(bucket, set())
    for index, part in enumerate(parts[:-1]):
        if part.casefold() in aliases:
            parts = parts[index + 1 :]
            break
    return PurePosixPath(*parts)


def proposed_target(row: dict[str, str], target_root: str, bucket: str) -> str:
    relative = remove_bucket_marker(meaningful_relative_path(row), bucket)
    safe_parts = [safe_filename(part) for part in relative.parts]
    return str(PurePosixPath(target_root) / bucket / PurePosixPath(*safe_parts))


def plan_rows(rows: list[dict[str, str]], target_root: str) -> list[dict[str, str]]:
    planned: list[dict[str, str]] = []
    for row in rows:
        if row["proposal_action"] not in {"document_standard", "document_sensitive"}:
            continue
        if is_technical_document(row):
            bucket, bucket_reason = "projects", "recognized build or project metadata"
        else:
            bucket, bucket_reason = choose_bucket(row)
        target_path = proposed_target(row, target_root, bucket)
        item = dict(row)
        item["target_bucket"] = bucket
        item["target_bucket_reason"] = bucket_reason
        item["proposed_target_path"] = target_path
        item["collision_status"] = "clear"
        if bucket == "projects":
            item["copy_action"] = "retain_project_technical"
        elif bucket == "documents/unsorted":
            item["copy_action"] = "manual_target_review"
        else:
            item["copy_action"] = "copy_candidate"
        item["semantic_scope"] = (
            "blocked_sensitive_policy" if bucket.startswith("sensitive/") else "not_yet_authorized"
        )
        planned.append(item)

    by_target: dict[str, list[dict[str, str]]] = defaultdict(list)
    for item in planned:
        by_target[item["proposed_target_path"].casefold()].append(item)

    for group in by_target.values():
        hashes = {item["hash_content"] for item in group}
        if len(hashes) > 1:
            for item in group:
                item["collision_status"] = "name_collision"
                item["copy_action"] = "blocked_name_collision"

    for item in planned:
        if Path(item["proposed_target_path"]).exists():
            item["collision_status"] = "target_path_exists"
            item["copy_action"] = "blocked_existing_target"

    return planned


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a read-only document copy plan.")
    parser.add_argument("--manifest", default="latest", help="Migration proposal CSV, or 'latest'")
    parser.add_argument("--target", default="/volume1/data", help="Canonical target root")
    parser.add_argument("--dry-run", action="store_true", required=True)
    return parser


def resolve_manifest(root: Path, value: str) -> Path:
    export_dir = root / "project" / "exports" / "migration-inventory"
    if value == "latest":
        manifests = sorted(export_dir.glob("migration-proposal-*.csv"))
        if not manifests:
            raise FileNotFoundError("No migration proposal found.")
        return manifests[-1]
    path = Path(value)
    return path if path.is_absolute() else root / path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target_root = args.target.rstrip("/")
    if target_root != "/volume1/data":
        print("Copy plan target must be exactly /volume1/data.", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parents[2]
    try:
        manifest_path = resolve_manifest(root, args.manifest)
        with manifest_path.open(newline="", encoding="utf-8") as handle:
            source_rows = list(csv.DictReader(handle))
    except (FileNotFoundError, OSError) as exc:
        print(f"Copy plan failed: {exc}", file=sys.stderr)
        return 1

    required = {
        "representative_file_id",
        "hash_content",
        "representative_path",
        "source_paths",
        "proposal_action",
        "copy_readiness",
    }
    if not source_rows or not required.issubset(source_rows[0]):
        print("Copy plan failed: migration proposal is empty or incompatible.", file=sys.stderr)
        return 1

    planned = plan_rows(source_rows, target_root)
    if not planned:
        print("Copy plan failed: no document groups found.", file=sys.stderr)
        return 1

    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    export_dir = root / "project" / "exports" / "migration-inventory"
    export_dir.mkdir(parents=True, exist_ok=True)
    plan_path = export_dir / f"copy-plan-{timestamp}.csv"
    collisions_path = export_dir / f"copy-plan-collisions-{timestamp}.csv"
    report_path = export_dir / f"copy-plan-{timestamp}.md"
    fields = list(planned[0])

    def write_csv(path: Path, selected: list[dict[str, str]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(selected)

    write_csv(plan_path, planned)
    collisions = [row for row in planned if row["collision_status"] != "clear"]
    write_csv(collisions_path, collisions)

    bucket_counts = Counter(row["target_bucket"] for row in planned)
    action_counts = Counter(row["copy_action"] for row in planned)
    report = [
        "# SCRUM-61 read-only document copy plan",
        "",
        f"- Generated: `{datetime.now().astimezone().isoformat()}`",
        f"- Input: `{manifest_path.name}`",
        f"- Target root: `{target_root}`",
        "- Mode: **read-only dry-run**",
        f"- Document groups: **{len(planned)}**",
        f"- Copy candidates: **{action_counts['copy_candidate']}**",
        f"- Retained project/technical: **{action_counts['retain_project_technical']}**",
        f"- Unsorted manual review: **{action_counts['manual_target_review']}**",
        f"- Name collisions blocked: **{action_counts['blocked_name_collision']}**",
        f"- Existing targets blocked: **{action_counts['blocked_existing_target']}**",
        "",
        "## Proposed buckets",
        "",
        "| Bucket | Content groups |",
        "|---|---:|",
    ]
    for bucket in sorted(TARGET_BUCKETS):
        report.append(f"| `{bucket}` | {bucket_counts[bucket]} |")
    report.extend(
        [
            "",
            "No directories or files were created, copied, moved, overwritten, or deleted.",
            "Sensitive documents remain excluded from semantic processing.",
        ]
    )
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    (export_dir / "copy-plan-latest.md").write_text(
        report_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    print("SCRUM-61 read-only document copy plan complete")
    print(f"Report: {report_path.relative_to(root)}")
    print(f"Plan: {plan_path.relative_to(root)}")
    print(f"Collisions: {collisions_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
