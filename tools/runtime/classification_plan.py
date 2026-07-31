#!/usr/bin/env python3
"""Turn SCRUM-61 classification output into a non-mutating reviewed copy plan."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.exports.csv_format import dict_reader, write_dict_rows

SOURCE_ROOT = "/volume1/backup/NITRO/D/data/hugo/Documents/"
CATEGORY_BUCKETS = {
    "documenten/administratie": "documents/administration",
    "documenten/persoonlijk": "documents/personal",
    "documenten/studie": "documents/study",
    "documenten/werk": "documents/work",
    "documenten/wonen": "documents/home",
    "projecten": "projects",
    "gevoelig/financiën": "sensitive/finance",
    "gevoelig/gezondheid": "sensitive/health",
    "gevoelig/identiteit": "sensitive/identity",
    "gevoelig/werk_en_inkomen": "sensitive/employment",
}
REQUIRED_FIELDS = {
    "content_group_id", "content_sha256", "golden_file_id", "filename",
    "golden_path", "extraction_status", "extraction_result",
    "content_category", "category_confidence", "temporal_inconsistencies",
}


def json_list(value: str) -> list:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return ["invalid_json"]
    return parsed if isinstance(parsed, list) else ["invalid_json"]


def safe_name(value: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).rstrip(" .") or "unnamed"
    stem = name.split(".", 1)[0].casefold()
    if stem in {"con", "prn", "aux", "nul"} or re.fullmatch(r"(?:com|lpt)[1-9]", stem):
        name = "_" + name
    return name


def relative_path(row: dict[str, str]) -> PurePosixPath:
    source = row["golden_path"]
    value = source[len(SOURCE_ROOT):] if source.startswith(SOURCE_ROOT) else row["filename"]
    parts = list(PurePosixPath(value).parts)
    if parts and parts[0].casefold() == "cloudstation":
        parts = parts[1:]
    return PurePosixPath(*(safe_name(part) for part in parts))


def review_decision(row: dict[str, str]) -> tuple[str, str, str]:
    result = row["extraction_result"]
    if result == "needs_ocr":
        return "blocked_ocr", "ocr_required", ""
    if row["extraction_status"] != "ready_for_local_extraction" or result == "skipped":
        return "blocked_conversion", "content_conversion_required", ""
    if result == "password_required":
        return "blocked_password", "password_required", ""
    if result in {"error", "extraction_timeout", "partial_extraction", "empty_file"}:
        return "manual_extraction_review", result, ""
    inconsistencies = json_list(row["temporal_inconsistencies"])
    if inconsistencies:
        return "manual_temporal_review", ",".join(map(str, inconsistencies)), ""
    category = row["content_category"]
    bucket = CATEGORY_BUCKETS.get(category, "")
    if not bucket or category in {"documenten/uitzoeken", "pending_content_extraction"}:
        return "manual_category_review", "category_not_actionable", ""
    if row["category_confidence"] != "high":
        return "manual_category_review", f"confidence_{row['category_confidence'] or 'missing'}", bucket
    if bucket.startswith("sensitive/"):
        return "blocked_sensitive_policy", "sensitive_requires_explicit_approval", bucket
    return "review_ready", "high_confidence_local_classification", bucket


def add_hash_suffix(path: str, digest: str) -> str:
    value = PurePosixPath(path)
    suffix = value.suffix
    stem = value.name[:-len(suffix)] if suffix else value.name
    return str(value.with_name(f"{stem}__{digest[:8]}{suffix}"))


def build_plan(rows: list[dict[str, str]], target_root: str) -> list[dict[str, str]]:
    planned = []
    for source in rows:
        row = dict(source)
        status, reason, bucket = review_decision(row)
        row.update({
            "review_status": status, "review_reason": reason,
            "target_bucket": bucket,
            "reviewed_target_path": str(PurePosixPath(target_root) / bucket / relative_path(row)) if bucket else "",
            "collision_status": "not_applicable" if not bucket else "clear",
            "execution_authorized": "false",
        })
        planned.append(row)
    by_target = defaultdict(list)
    for row in planned:
        if row["reviewed_target_path"]:
            by_target[row["reviewed_target_path"].casefold()].append(row)
    for group in by_target.values():
        if len({row["content_sha256"] for row in group}) > 1:
            for row in group:
                row["reviewed_target_path"] = add_hash_suffix(row["reviewed_target_path"], row["content_sha256"])
                row["collision_status"] = "resolved_hash_suffix"
    return planned


def resolve_results(root: Path, value: str) -> Path:
    export_dir = root / "project" / "exports" / "migration-inventory"
    if value == "latest":
        paths = sorted(export_dir.glob("classification-results-*.csv"))
        if not paths:
            raise FileNotFoundError("No classification results found.")
        return paths[-1]
    path = Path(value)
    return path if path.is_absolute() else root / path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a reviewed classification copy plan.")
    parser.add_argument("--results", default="latest", help="Classification results CSV, or latest")
    parser.add_argument("--target", default="/volume1/data")
    parser.add_argument("--dry-run", action="store_true", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.target.rstrip("/") != "/volume1/data":
        print("Classification plan target must be exactly /volume1/data.", file=sys.stderr)
        return 2
    root = PROJECT_ROOT
    try:
        source_path = resolve_results(root, args.results)
        with source_path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(dict_reader(handle))
    except (FileNotFoundError, OSError) as exc:
        print(f"Classification plan failed: {exc}", file=sys.stderr)
        return 1
    if not rows or not REQUIRED_FIELDS.issubset(rows[0]):
        print("Classification plan failed: results are empty or incompatible.", file=sys.stderr)
        return 1
    planned = build_plan(rows, args.target.rstrip("/"))
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    export_dir = root / "project" / "exports" / "migration-inventory"
    plan_path = export_dir / f"classification-plan-{timestamp}.csv"
    fields = list(planned[0])
    write_dict_rows(plan_path, planned, fields)
    queue_paths = {}
    for queue, statuses in {
        "ocr": {"blocked_ocr"}, "conversion": {"blocked_conversion"},
        "manual-review": {"manual_extraction_review", "manual_temporal_review", "manual_category_review", "blocked_password"},
    }.items():
        path = export_dir / f"classification-{queue}-{timestamp}.csv"
        write_dict_rows(path, [r for r in planned if r["review_status"] in statuses], fields)
        queue_paths[queue] = path
    counts = Counter(row["review_status"] for row in planned)
    report_path = export_dir / f"classification-plan-{timestamp}.md"
    report = [
        "# SCRUM-61 reviewed classification copy plan", "",
        f"- Generated: `{datetime.now().astimezone().isoformat()}`", f"- Input: `{source_path.name}`",
        "- Mode: **read-only dry-run**", f"- Documents: **{len(planned)}**",
        f"- Review-ready: **{counts['review_ready']}**",
        f"- Sensitive policy block: **{counts['blocked_sensitive_policy']}**",
        f"- OCR queue: **{counts['blocked_ocr']}**", f"- Conversion queue: **{counts['blocked_conversion']}**",
        f"- Manual category review: **{counts['manual_category_review']}**",
        f"- Manual temporal review: **{counts['manual_temporal_review']}**",
        f"- Manual extraction review: **{counts['manual_extraction_review']}**", "",
        "No copy, move, overwrite, delete, timestamp, or database operation was authorized or performed.",
    ]
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    (export_dir / "classification-plan-latest.md").write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")
    print("SCRUM-61 reviewed classification copy plan complete")
    print(f"Report: {report_path.relative_to(root)}")
    print(f"Plan: {plan_path.relative_to(root)}")
    for name, path in queue_paths.items():
        print(f"{name.title()} queue: {path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
