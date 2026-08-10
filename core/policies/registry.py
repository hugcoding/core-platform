from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any


POLICY_NAMESPACE = uuid.UUID("13a29fbd-4921-499e-944e-08cbe85dbf6e")
CONTRACT_VERSION = "active-document-workset-policy-v1"
POLICY_CODE = "active_document_workset"
ENVIRONMENTS = {"development", "acceptance", "production"}
CONFIDENCES = {"low", "medium", "high"}
ACTIVITY_SOURCES = {
    "source_metadata_modified", "source_metadata_created", "filesystem_mtime",
}
EXCLUDED_ACTIVITY_SOURCES = {
    "core_first_observed_at", "filesystem_atime", "filesystem_birthtime",
}
REQUIRED_EXTENSIONS = {"pdf", "docx", "xlsx"}
_VERSION = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _timestamp(value: object, field: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def validate_seed(payload: dict[str, Any], *, environment: str) -> dict[str, Any]:
    if payload.get("schema_version") != CONTRACT_VERSION:
        raise ValueError("unsupported active document workset policy contract")
    if payload.get("policy_code") != POLICY_CODE:
        raise ValueError(f"policy_code must be {POLICY_CODE}")
    if environment not in ENVIRONMENTS:
        raise ValueError("environment must be development, acceptance or production")
    version = str(payload.get("policy_version") or "")
    if not _VERSION.fullmatch(version):
        raise ValueError("policy_version is required and must be stable")
    config = payload.get("configuration")
    if not isinstance(config, dict):
        raise ValueError("configuration must be an object")

    months = int(config.get("activity_window_months") or 0)
    if not 1 <= months <= 24:
        raise ValueError("activity_window_months must be between 1 and 24")
    extensions = {str(value).lower().lstrip(".") for value in config.get("extensions", [])}
    if extensions != REQUIRED_EXTENSIONS:
        raise ValueError("extensions must contain exactly pdf, docx and xlsx")
    roots = [str(value).rstrip("/") for value in config.get("source_roots", [])]
    if not roots or any(not root.startswith("/volume1/") or root == "/volume1/data" for root in roots):
        raise ValueError("source_roots must contain scoped paths below /volume1")
    activity = {str(value) for value in config.get("activity_sources", [])}
    excluded = {str(value) for value in config.get("excluded_activity_sources", [])}
    if activity != ACTIVITY_SOURCES:
        raise ValueError("activity_sources do not match the v1 contract")
    if excluded != EXCLUDED_ACTIVITY_SOURCES or activity & excluded:
        raise ValueError("excluded_activity_sources do not match the v1 safety contract")
    if config.get("golden_records_only") is not True:
        raise ValueError("golden_records_only must be true")
    for key in ("temporal_conflict_action", "missing_golden_action"):
        if config.get(key) != "needs_review":
            raise ValueError(f"{key} must be needs_review")
    confidence = str(config.get("minimum_confidence") or "")
    if confidence not in CONFIDENCES:
        raise ValueError("minimum_confidence must be low, medium or high")
    review_limit = int(config.get("review_limit") or 0)
    if not 1 <= review_limit <= 1000:
        raise ValueError("review_limit must be between 1 and 1000")

    normalized_config = {
        **config,
        "activity_window_months": months,
        "extensions": sorted(extensions),
        "source_roots": sorted(set(roots)),
        "activity_sources": sorted(activity),
        "excluded_activity_sources": sorted(excluded),
        "minimum_confidence": confidence,
        "review_limit": review_limit,
    }
    effective_from = _timestamp(payload.get("effective_from"), "effective_from")
    effective_until = payload.get("effective_until")
    if effective_until is not None:
        effective_until = _timestamp(effective_until, "effective_until")
        if datetime.fromisoformat(effective_until) <= datetime.fromisoformat(effective_from):
            raise ValueError("effective_until must be later than effective_from")
    reason = str(payload.get("change_reason") or "").strip()
    if not reason:
        raise ValueError("change_reason is required")
    return {
        "schema_version": "policy-seed-plan-v1",
        "policy_code": POLICY_CODE,
        "environment": environment,
        "contract_version": CONTRACT_VERSION,
        "policy_version": version,
        "status": "active",
        "configuration": normalized_config,
        "effective_from": effective_from,
        "effective_until": effective_until,
        "created_by": str(payload.get("created_by") or "core-policy-seed"),
        "change_reason": reason,
        "approved_at": _timestamp(payload.get("approved_at") or effective_from, "approved_at"),
        "approved_by": str(payload.get("approved_by") or "core-policy-seed"),
    }


def build_seed_plan(payload: dict[str, Any], *, environment: str) -> dict[str, Any]:
    plan = validate_seed(payload, environment=environment)
    checksum = hashlib.sha256(_canonical(plan["configuration"])).hexdigest()
    identity = f"{plan['policy_code']}:{environment}:{plan['policy_version']}:{checksum}"
    return {
        **plan,
        "id": str(uuid.uuid5(POLICY_NAMESPACE, identity)),
        "configuration_checksum": checksum,
    }


def _sql(value: object) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def render_seed_sql(plan: dict[str, Any]) -> str:
    configuration = json.dumps(plan["configuration"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    values = [
        f"{_sql(plan['id'])}::uuid", _sql(plan["policy_code"]), _sql(plan["environment"]),
        _sql(plan["contract_version"]), _sql(plan["policy_version"]), _sql(plan["status"]),
        f"{_sql(configuration)}::jsonb", _sql(plan["configuration_checksum"]),
        f"{_sql(plan['effective_from'])}::timestamptz",
        "NULL" if plan["effective_until"] is None else f"{_sql(plan['effective_until'])}::timestamptz",
        _sql(plan["created_by"]), _sql(plan["change_reason"]),
        f"{_sql(plan['approved_at'])}::timestamptz", _sql(plan["approved_by"]),
    ]
    return "\n".join([
        "BEGIN;",
        "INSERT INTO public.policy_versions",
        "  (id,policy_code,environment,contract_version,policy_version,status,configuration,",
        "   configuration_checksum,effective_from,effective_until,created_by,change_reason,approved_at,approved_by)",
        f"  VALUES ({','.join(values)}) ON CONFLICT DO NOTHING;",
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM public.policy_versions WHERE id={_sql(plan['id'])}::uuid",
        f"  AND policy_code={_sql(plan['policy_code'])} AND environment={_sql(plan['environment'])}",
        f"  AND policy_version={_sql(plan['policy_version'])} AND configuration_checksum={_sql(plan['configuration_checksum'])}) THEN",
        "  RAISE EXCEPTION 'policy seed provenance validation failed'; END IF; END $$;",
        "COMMIT;",
    ]) + "\n"
