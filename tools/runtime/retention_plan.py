#!/usr/bin/env python3
"""Create a read-only lifecycle and retention proposal for SCRUM-61 documents."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.exports.csv_format import dict_reader, write_dict_rows

POLICY_VERSION = "retention-v1"
DECISION_NAMESPACE = uuid.UUID("d7814410-aa43-4d63-9c29-4cb606df57eb")
REQUIRED_FIELDS = {
    "content_group_id", "content_sha256", "golden_file_id", "filename",
    "golden_path", "content_category", "category_confidence",
    "extraction_result", "filesystem_mtime", "embedded_created_at",
    "embedded_modified_at", "temporal_inconsistencies",
}


@dataclass(frozen=True)
class Policy:
    policy_id: str
    active_years: int | None
    archive_years: int | None
    disposition: str
    snapshot_level: str


POLICIES = {
    "study_handout": Policy("study_handout_1y_4y", 1, 4, "review_snapshot_or_delete", "catalog"),
    "study_own_work": Policy("study_own_work_3y_7y", 3, 7, "retention_review", "catalog"),
    "study_reference": Policy("study_reference_3y_7y", 3, 7, "retention_review", "catalog"),
    "study_certificate": Policy("certificate_permanent", None, None, "permanent", "full"),
    "certificate": Policy("certificate_permanent", None, None, "permanent", "full"),
    "administration": Policy("administration_2y_5y", 2, 5, "retention_review", "catalog"),
    "personal": Policy("personal_3y_7y", 3, 7, "retention_review", "catalog"),
    "home": Policy("home_3y_7y", 3, 7, "retention_review", "catalog"),
    "work": Policy("work_3y_5y", 3, 5, "retention_review", "catalog"),
    "project": Policy("project_3y_5y", 3, 5, "retention_review", "catalog"),
    "financial": Policy("financial_manual", None, None, "manual_legal_review", "catalog"),
    "health": Policy("health_permanent_manual", None, None, "permanent_manual", "full"),
    "identity": Policy("identity_expiry_manual", None, None, "manual_expiry_review", "catalog"),
    "employment": Policy("employment_manual", None, None, "manual_legal_review", "catalog"),
    "unknown": Policy("unknown_no_automatic_action", None, None, "manual_classification", "catalog"),
}

HANDOUT_TERMS = ("handout", "reader", "syllabus", "lesmateriaal", "lesstof", "slides", "presentatie", "college")
OWN_WORK_TERMS = ("scriptie", "portfolio", "eindopdracht", "afstudeer", "persoonlijk ontwikkelplan", "pop")
CERTIFICATE_TERMS = ("diploma", "certificaat", "certificate", "getuigschrift", "cijferlijst")


def json_list(value: str) -> list:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return ["invalid_json"]
    return parsed if isinstance(parsed, list) else ["invalid_json"]


def document_role(row: dict[str, str]) -> tuple[str, str, str]:
    evidence = f"{row['filename']} {row['golden_path']} {row.get('category_reasons', '')}".casefold()
    category = row["content_category"]
    if any(term in evidence for term in CERTIFICATE_TERMS):
        role = "study_certificate" if category == "documenten/studie" else "certificate"
        return role, "high", "certificate_keyword"
    if category == "documenten/studie":
        if any(term in evidence for term in HANDOUT_TERMS):
            return "study_handout", "high", "handout_keyword"
        if any(term in evidence for term in OWN_WORK_TERMS):
            return "study_own_work", "high", "own_work_keyword"
        return "study_reference", "medium", "study_role_not_distinguished"
    mapping = {
        "documenten/administratie": "administration", "documenten/persoonlijk": "personal",
        "documenten/wonen": "home", "documenten/werk": "work", "projecten": "project",
        "gevoelig/financiën": "financial", "gevoelig/gezondheid": "health",
        "gevoelig/identiteit": "identity", "gevoelig/werk_en_inkomen": "employment",
    }
    role = mapping.get(category, "unknown")
    return role, "medium" if role != "unknown" else "low", "category_default_role"


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def retention_basis(row: dict[str, str]) -> tuple[datetime | None, str, str]:
    if json_list(row["temporal_inconsistencies"]):
        return None, "", "blocked_temporal_inconsistency"
    for field, confidence in (
        ("embedded_modified_at", "high"),
        ("embedded_created_at", "medium"),
        ("filesystem_mtime", "low"),
    ):
        value = parse_datetime(row[field])
        if value:
            return value, field, confidence
    return None, "", "missing"


def add_years(value: datetime, years: int) -> datetime:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, month=2, day=28)


def lifecycle(policy: Policy, basis: datetime | None, as_of: datetime) -> tuple[str, str, str]:
    if policy.disposition in {"permanent", "permanent_manual"}:
        return "permanent", "", "no_automatic_deletion"
    if policy.active_years is None or policy.archive_years is None:
        return "retention_review", "", policy.disposition
    if basis is None:
        return "retention_review", "", "missing_reliable_basis_date"
    active_until = add_years(basis, policy.active_years)
    retain_until = add_years(active_until, policy.archive_years)
    if as_of < active_until:
        return "active", retain_until.isoformat(), "within_active_period"
    if as_of < retain_until:
        return "cold_archive", retain_until.isoformat(), "active_period_elapsed"
    return "retention_review", retain_until.isoformat(), "retention_period_elapsed"


def propose_row(row: dict[str, str], as_of: datetime) -> dict[str, str]:
    role, role_confidence, role_reason = document_role(row)
    policy = POLICIES[role]
    basis, basis_source, basis_confidence = retention_basis(row)
    state, retain_until, lifecycle_reason = lifecycle(policy, basis, as_of)
    decision_key = f"{row['content_group_id']}:{POLICY_VERSION}:{as_of.date().isoformat()}:{state}"
    review_required = state == "retention_review" or role_confidence != "high"
    return {
        **row,
        "document_role": role,
        "document_role_confidence": role_confidence,
        "document_role_reason": role_reason,
        "retention_policy_id": policy.policy_id,
        "retention_policy_version": POLICY_VERSION,
        "retention_basis_date": basis.isoformat() if basis else "",
        "retention_basis_source": basis_source,
        "retention_basis_confidence": basis_confidence,
        "proposed_lifecycle_state": state,
        "retain_until": retain_until,
        "next_review_at": as_of.date().isoformat() if review_required else retain_until,
        "disposition_after_retention": policy.disposition,
        "snapshot_level": policy.snapshot_level,
        "legal_hold": "false",
        "lifecycle_reason": lifecycle_reason,
        "proposed_decision_id": str(uuid.uuid5(DECISION_NAMESPACE, decision_key)),
        "decision_actor_type": "policy_engine",
        "decision_action": "propose_retention",
        "decision_from_state": "unassessed",
        "decision_to_state": state,
        "decision_reason_code": lifecycle_reason,
        "decision_supersedes_id": "",
        "execution_authorized": "false",
    }


COMPACT_FIELDS = [
    "golden_file_id", "filename", "golden_path", "content_category",
    "document_role", "document_role_confidence", "retention_policy_id",
    "retention_basis_date", "retention_basis_source", "retention_basis_confidence",
    "proposed_lifecycle_state", "retain_until", "next_review_at",
    "disposition_after_retention", "snapshot_level", "lifecycle_reason",
    "execution_authorized",
]


def build_plan(rows: list[dict[str, str]], as_of: datetime) -> list[dict[str, str]]:
    return [propose_row(row, as_of) for row in rows]


def resolve_results(root: Path, value: str) -> Path:
    export_dir = root / "project" / "exports" / "migration-inventory"
    if value == "latest":
        paths = sorted(export_dir.glob("classification-results-*.csv"))
        if not paths:
            raise FileNotFoundError("No classification results found.")
        return paths[-1]
    path = Path(value)
    return path if path.is_absolute() else root / path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a read-only retention plan.")
    parser.add_argument("--results", default="latest")
    parser.add_argument("--as-of", help="ISO date used for deterministic assessment")
    parser.add_argument("--dry-run", action="store_true", required=True)
    args = parser.parse_args(argv)
    as_of = parse_datetime(args.as_of) if args.as_of else datetime.now(timezone.utc)
    if as_of is None:
        print("Retention plan failed: --as-of must be an ISO date.", file=sys.stderr)
        return 2
    try:
        source_path = resolve_results(PROJECT_ROOT, args.results)
        with source_path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(dict_reader(handle))
    except (FileNotFoundError, OSError) as exc:
        print(f"Retention plan failed: {exc}", file=sys.stderr)
        return 1
    if not rows or not REQUIRED_FIELDS.issubset(rows[0]):
        print("Retention plan failed: results are empty or incompatible.", file=sys.stderr)
        return 1
    planned = build_plan(rows, as_of)
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    export_dir = PROJECT_ROOT / "project" / "exports" / "migration-inventory"
    plan_path = export_dir / f"retention-plan-{timestamp}.csv"
    review_path = export_dir / f"retention-review-{timestamp}.csv"
    report_path = export_dir / f"retention-plan-{timestamp}.md"
    write_dict_rows(plan_path, planned, list(planned[0]))
    review_rows = [
        {field: row.get(field, "") for field in COMPACT_FIELDS}
        for row in planned
        if row["proposed_lifecycle_state"] in {"cold_archive", "retention_review"}
    ]
    write_dict_rows(review_path, review_rows, COMPACT_FIELDS)
    states = Counter(row["proposed_lifecycle_state"] for row in planned)
    roles = Counter(row["document_role"] for row in planned)
    report = [
        "# SCRUM-61 read-only retention plan", "",
        f"- Generated: `{datetime.now().astimezone().isoformat()}`",
        f"- Assessed as of: `{as_of.isoformat()}`", f"- Input: `{source_path.name}`",
        f"- Policy version: `{POLICY_VERSION}`", "- Mode: **read-only dry-run**",
        f"- Documents: **{len(planned)}**", f"- Active: **{states['active']}**",
        f"- Cold archive proposed: **{states['cold_archive']}**",
        f"- Retention review: **{states['retention_review']}**",
        f"- Permanent: **{states['permanent']}**", "", "## Document roles", "",
        "| Role | Documents |", "|---|---:|",
    ]
    report.extend(f"| `{role}` | {count} |" for role, count in sorted(roles.items()))
    report.extend(["", "No archive, copy, deletion, snapshot, timestamp, or database operation was authorized or performed."])
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    (export_dir / "retention-plan-latest.md").write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")
    print("SCRUM-61 read-only retention plan complete")
    print(f"Report: {report_path.relative_to(PROJECT_ROOT)}")
    print(f"Plan: {plan_path.relative_to(PROJECT_ROOT)}")
    print(f"Compact review: {review_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
