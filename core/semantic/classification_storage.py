from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any


RUN_NAMESPACE = uuid.UUID("896a85fe-8bed-47a0-8dfd-21afcdbdb88c")
PROPOSAL_NAMESPACE = uuid.UUID("99dcd692-7ed5-45f8-8fd4-ac572580645a")
REVIEW_NAMESPACE = uuid.UUID("c7f7a662-901a-44a7-95bb-a713481c85ed")
CATEGORIES = {"personal", "administration", "finance", "home", "work", "study", "projects", "other"}
LIFECYCLES = {"active_candidate", "archive_candidate", "needs_review", "quarantine"}
SENSITIVITIES = {"normal", "personal", "sensitive", "highly_sensitive"}
CONFIDENCES = {"low", "medium", "high"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sql(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _array(values: list[str]) -> str:
    return "ARRAY[" + ",".join(_sql(value) for value in values) + "]::text[]"


def build_proposal_plan(report_bytes: bytes, manifest_bytes: bytes) -> dict[str, Any]:
    report, manifest = json.loads(report_bytes), json.loads(manifest_bytes)
    if report.get("schema_version") != "personal-golden-classification-v2":
        raise ValueError("unsupported classification report")
    if report.get("status") != "completed" or report.get("read_only") is not True:
        raise ValueError("only completed read-only reports are eligible")
    if report.get("database_writes") is not False or report.get("file_mutations") is not False:
        raise ValueError("source run must not have written data or files")
    if manifest.get("processing") != "local_only" or manifest.get("external_ai_enabled") is not False:
        raise ValueError("classification must have used a local provider")
    approved = {int(row["file_id"]): row for row in manifest["files"] if row.get("approval") == "approved"}
    results = report.get("results") or []
    if len(results) != len(approved):
        raise ValueError("report result count does not match approved manifest")
    provider = report.get("provider") or {}
    provider_id, model_id = str(provider.get("provider_id") or ""), str(provider.get("model") or "")
    if not provider_id or not model_id:
        raise ValueError("provider provenance is required")
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    prompt_version = str(report.get("prompt_version") or "")
    contract_version = str(report["schema_version"])
    identity = f"{manifest_hash}:{prompt_version}:{contract_version}:{provider_id}:{model_id}"
    run_id = str(uuid.uuid5(RUN_NAMESPACE, identity))
    proposals = []
    for result in results:
        file_id = int(result["file_id"])
        item = approved.get(file_id)
        if item is None:
            raise ValueError(f"report returned unknown file_id={file_id}")
        if result.get("status") != "classified":
            continue
        proposal = {
            "id": str(uuid.uuid5(PROPOSAL_NAMESPACE, f"{run_id}:{file_id}")),
            "run_id": run_id, "file_id": file_id,
            "content_group_id": str(item["content_group_id"]),
            "content_sha256": str(item["content_sha256"]),
            "classifier_key": f"{provider_id}:{model_id}:{prompt_version}:{contract_version}",
            "status": "pending_review", "document_type": str(result["document_type"]),
            "model_category": str(result["model_category"]), "category": str(result["category"]),
            "model_document_family": str(result["model_document_family"]),
            "document_family": str(result["document_family"]),
            "topics": [str(v) for v in result.get("topics", [])],
            "lifecycle": str(result["lifecycle"]), "suggested_path": str(result["suggested_path"]),
            "model_sensitivity": str(result["model_sensitivity"]), "sensitivity": str(result["sensitivity"]),
            "sensitivity_signals": [str(v) for v in result.get("sensitivity_signals", [])],
            "model_confidence": str(result["model_confidence"]), "confidence": str(result["confidence"]),
            "normalization_warnings": [str(v) for v in result.get("normalization_warnings", [])],
            "reason": str(result["reason"]),
        }
        for field, allowed in (("category", CATEGORIES), ("lifecycle", LIFECYCLES),
                               ("sensitivity", SENSITIVITIES), ("confidence", CONFIDENCES)):
            if proposal[field] not in allowed:
                raise ValueError(f"invalid {field} for file_id={file_id}")
        proposal["proposal_sha256"] = hashlib.sha256(_canonical(proposal)).hexdigest()
        proposals.append(proposal)
    usage = provider.get("usage") or {}
    return {
        "schema_version": "classification-acc-plan-v1", "run_id": run_id,
        "environment": "acceptance", "manifest_sha256": manifest_hash,
        "prompt_version": prompt_version, "contract_version": contract_version,
        "provider_id": provider_id, "model_id": model_id,
        "status": "completed_with_errors" if len(proposals) != len(results) else "completed",
        "document_count": len(results), "proposal_count": len(proposals),
        "error_count": len(results) - len(proposals),
        "classification_seconds": provider.get("classification_seconds"),
        "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"), "local_provider": True, "raw_text_stored": False,
        "proposals": proposals,
    }


def render_proposal_apply_sql(plan: dict[str, Any]) -> str:
    statements = ["BEGIN;", f"""INSERT INTO public.classification_runs
      (id,environment,manifest_sha256,prompt_version,contract_version,provider_id,model_id,status,
       document_count,proposal_count,error_count,classification_seconds,prompt_tokens,completion_tokens,total_tokens)
      VALUES ({_sql(plan['run_id'])}::uuid,'acceptance',{_sql(plan['manifest_sha256'])},
       {_sql(plan['prompt_version'])},{_sql(plan['contract_version'])},{_sql(plan['provider_id'])},
       {_sql(plan['model_id'])},{_sql(plan['status'])},{plan['document_count']},{plan['proposal_count']},
       {plan['error_count']},{_sql(plan['classification_seconds'])},{_sql(plan['prompt_tokens'])},
       {_sql(plan['completion_tokens'])},{_sql(plan['total_tokens'])}) ON CONFLICT (id) DO NOTHING;"""]
    fields = ("document_type", "model_category", "category", "model_document_family", "document_family")
    for p in plan["proposals"]:
        statements.append(f"""INSERT INTO public.classification_proposals
          (id,run_id,file_id,content_group_id,content_sha256,classifier_key,proposal_sha256,status,
           document_type,model_category,category,model_document_family,document_family,topics,lifecycle,
           suggested_path,model_sensitivity,sensitivity,sensitivity_signals,model_confidence,confidence,
           normalization_warnings,reason)
          SELECT {_sql(p['id'])}::uuid,{_sql(plan['run_id'])}::uuid,f.id,cg.id,{_sql(p['content_sha256'])},
           {_sql(p['classifier_key'])},{_sql(p['proposal_sha256'])},'pending_review',
           {','.join(_sql(p[name]) for name in fields)},{_array(p['topics'])},{_sql(p['lifecycle'])},
           {_sql(p['suggested_path'])},{_sql(p['model_sensitivity'])},{_sql(p['sensitivity'])},
           {_array(p['sensitivity_signals'])},{_sql(p['model_confidence'])},{_sql(p['confidence'])},
           {_array(p['normalization_warnings'])},{_sql(p['reason'])}
          FROM public.files f JOIN public.content_groups cg ON cg.id={_sql(p['content_group_id'])}::uuid
          WHERE f.id={p['file_id']} AND f.deleted_at IS NULL AND f.content_sha256={_sql(p['content_sha256'])}
            AND cg.golden_file_id=f.id ON CONFLICT (id) DO NOTHING;""")
        statements.append(f"""DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM public.classification_proposals
          WHERE id={_sql(p['id'])}::uuid AND proposal_sha256={_sql(p['proposal_sha256'])}) THEN
          RAISE EXCEPTION 'classification proposal provenance validation failed for file_id={p['file_id']}';
          END IF; END $$;""")
    statements.extend([f"""DO $$ BEGIN IF (SELECT count(*) FROM public.classification_proposals
      WHERE run_id={_sql(plan['run_id'])}::uuid) <> {plan['proposal_count']} THEN
      RAISE EXCEPTION 'classification proposal count validation failed'; END IF; END $$;""", "COMMIT;"])
    return "\n".join(statements) + "\n"


def build_review_plan(review: dict[str, Any]) -> dict[str, Any]:
    required = ("proposal_id", "idempotency_key", "decision", "reviewer", "reviewed_at")
    if any(not review.get(field) for field in required):
        raise ValueError("review requires proposal_id, idempotency_key, decision, reviewer and reviewed_at")
    uuid.UUID(str(review["proposal_id"])); datetime.fromisoformat(str(review["reviewed_at"]).replace("Z", "+00:00"))
    decision = str(review["decision"])
    if decision not in {"accepted", "rejected"}:
        raise ValueError("decision must be accepted or rejected")
    if decision == "accepted":
        for field, allowed in (("category", CATEGORIES), ("lifecycle", LIFECYCLES),
                               ("sensitivity", SENSITIVITIES), ("confidence", CONFIDENCES)):
            if review.get(field) not in allowed:
                raise ValueError(f"accepted review requires valid {field}")
        if not review.get("document_family") or not review.get("suggested_path"):
            raise ValueError("accepted review requires document_family and suggested_path")
    key = str(review["idempotency_key"])
    plan = {"schema_version": "classification-review-plan-v1", "id": str(uuid.uuid5(REVIEW_NAMESPACE, key)),
            **{name: review.get(name) for name in ("proposal_id", "idempotency_key", "decision", "reviewer",
                "reviewed_at", "category", "document_family", "lifecycle", "suggested_path",
                "sensitivity", "confidence", "notes")}}
    plan["review_sha256"] = hashlib.sha256(_canonical(plan)).hexdigest()
    return plan


def render_review_apply_sql(plan: dict[str, Any]) -> str:
    columns = ("id", "proposal_id", "idempotency_key", "review_sha256", "decision", "reviewer", "reviewed_at", "category",
               "document_family", "lifecycle", "suggested_path", "sensitivity", "confidence", "notes")
    values = [f"{_sql(plan['id'])}::uuid", f"{_sql(plan['proposal_id'])}::uuid"] + [
        _sql(plan[name]) for name in columns[2:6]] + [f"{_sql(plan['reviewed_at'])}::timestamptz"] + [
        _sql(plan[name]) for name in columns[7:]]
    return "\n".join(["BEGIN;", f"INSERT INTO public.classification_reviews ({','.join(columns)}) SELECT {','.join(values)} WHERE EXISTS (SELECT 1 FROM public.classification_proposals WHERE id={_sql(plan['proposal_id'])}::uuid) ON CONFLICT (idempotency_key) DO NOTHING;",
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM public.classification_reviews WHERE idempotency_key={_sql(plan['idempotency_key'])} AND id={_sql(plan['id'])}::uuid AND review_sha256={_sql(plan['review_sha256'])}) THEN RAISE EXCEPTION 'classification review validation failed'; END IF; END $$;", "COMMIT;"]) + "\n"
