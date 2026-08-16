#!/usr/bin/env python3
"""SCRUM-98 read-only candidate-rule analysis."""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from core.exports.csv_format import write_dict_rows
from core.organization.review_learning import (
    analyze_privacy_reviews, analyze_proposal_quality, analyze_reviews, audit_review_paths,
)
from core.organization.trajectory_learning import build_trajectory_rules
from core.organization.learning_context import build_llm_learning_context


ROOT = Path(__file__).resolve().parents[2]
QUERY = """
COPY (
  SELECT e.id, e.file_id, e.review_type, e.decision, e.proposal_category_code,
         e.proposal_document_family_code, e.corrected_category_code,
         e.corrected_document_family_code, e.proposal_target_path, e.proposed_target_path,
         e.proposed_target_path_raw, e.created_at,
         e.proposal_privacy_classification, e.corrected_privacy_classification,
         e.proposal_confidence, e.proposal_reason_code, e.privacy_rule_version,
         e.privacy_evidence, e.target_path_input_kind, e.target_path_suggestion,
         e.target_path_suggestion_decision, f.filename, f.path
  FROM public.document_review_events e
  JOIN public.files f ON f.id = e.file_id
  WHERE e.channel = 'workset_portal'
  ORDER BY e.created_at, e.id
) TO STDOUT WITH CSV HEADER;
"""


def fetch_rows() -> list[dict[str, str]]:
    docker = os.getenv("DOCKER_BIN", "docker")
    if docker == "docker" and Path("/usr/local/bin/docker").exists():
        docker = "/usr/local/bin/docker"
    command = [docker, "exec", "-i", os.getenv("POSTGRES_CONTAINER", "postgres"), "psql",
               "-v", "ON_ERROR_STOP=1", "-U", os.getenv("DB_USER", "hugo"),
               "-d", os.getenv("DB_NAME", "nasdb_test"), "-c", QUERY]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
    return list(csv.DictReader(io.StringIO(completed.stdout)))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Analyze human reviews into inactive candidate rules.")
    parser.add_argument("--minimum-support", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        rows = fetch_rows()
        candidates = analyze_reviews(rows, args.minimum_support)
        privacy_candidates = analyze_privacy_reviews(rows, args.minimum_support)
        proposal_quality = analyze_proposal_quality(rows)
        path_audit = audit_review_paths(rows)
        trajectory_candidates = build_trajectory_rules(rows, args.minimum_support)
    except (ValueError, subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Review-learning analysis failed: {exc}")
        return 1
    generated = datetime.now().astimezone()
    stamp = generated.strftime("%Y%m%d-%H%M%S")
    output = ROOT / "project/exports/review-learning"
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"review-learning-candidates-{stamp}.json"
    csv_path = output / f"review-learning-candidates-{stamp}.csv"
    md_path = output / f"review-learning-candidates-{stamp}.md"
    payload = {
        "schema_version": "review-learning-candidates-v2",
        "generated_at": generated.isoformat(), "mode": "read_only",
        "minimum_support": args.minimum_support, "reviews_analyzed": len(rows),
        "candidate_count": len(candidates) + len(privacy_candidates) + len(trajectory_candidates),
        "classification_candidate_count": len(candidates),
        "privacy_candidate_count": len(privacy_candidates),
        "candidates": candidates, "privacy_candidates": privacy_candidates,
        "trajectory_candidates": trajectory_candidates,
        "proposal_quality": proposal_quality,
        "path_systematics_audit": path_audit,
        "llm_learning_context": build_llm_learning_context(candidates),
        "safety": {"database_writes": False, "rules_activated": False,
                   "file_mutations": False, "model_updates": False},
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fields = ["candidate_type", "source_family_code", "target_category_code", "target_family_code",
              "support", "confidence", "conflict_count", "example_file_ids", "reason_codes", "activation_status", "llm_context"]
    csv_rows = [{**item, "example_file_ids": json.dumps(item["example_file_ids"]),
                 "reason_codes": json.dumps(item["reason_codes"]),
                 "llm_context": json.dumps(item["llm_context"], ensure_ascii=False)} for item in candidates]
    write_dict_rows(csv_path, csv_rows, fields)
    privacy_csv_path = output / f"review-learning-privacy-candidates-{stamp}.csv"
    privacy_fields = [
        "candidate_type", "pattern_reason_code", "pattern_evidence",
        "source_privacy_classification", "target_privacy_classification", "support",
        "agreement_count", "agreement", "confidence", "counterexample_count",
        "counterexamples", "example_file_ids", "reason_codes", "activation_status",
        "may_lower_high_automatically", "eligible_for_activation_review",
    ]
    privacy_csv_rows = [{
        **item,
        "counterexamples": json.dumps(item["counterexamples"], ensure_ascii=False),
        "example_file_ids": json.dumps(item["example_file_ids"]),
        "reason_codes": json.dumps(item["reason_codes"]),
    } for item in privacy_candidates]
    write_dict_rows(privacy_csv_path, privacy_csv_rows, privacy_fields)
    trajectory_csv_path = output / f"review-learning-trajectory-candidates-{stamp}.csv"
    trajectory_fields = [
        "candidate_type", "trajectory_code", "trajectory_label", "match_term",
        "trajectory_parts", "support", "agreement", "confidence",
        "counterexample_count", "counterexamples",
        "example_file_ids", "source_review_event_ids", "reason_codes", "activation_status",
    ]
    trajectory_csv_rows = [{
        **item,
        "trajectory_parts": json.dumps(item["trajectory_parts"], ensure_ascii=False),
        "counterexamples": json.dumps(item["counterexamples"], ensure_ascii=False),
        "example_file_ids": json.dumps(item["example_file_ids"]),
        "source_review_event_ids": json.dumps(item["source_review_event_ids"]),
        "reason_codes": json.dumps(item["reason_codes"]),
    } for item in trajectory_candidates]
    write_dict_rows(trajectory_csv_path, trajectory_csv_rows, trajectory_fields)
    proposal_csv_path = output / f"review-learning-proposal-quality-{stamp}.csv"
    proposal_fields = [
        "dimension", "reviewed_proposals", "judged_proposals", "accepted_unchanged",
        "accepted_corrected", "rejected", "deferred_or_passed", "agreement",
        "counterexample_count", "counterexamples", "mode",
    ]
    proposal_csv_rows = [{
        **item, "counterexamples": json.dumps(item["counterexamples"], ensure_ascii=False),
    } for item in proposal_quality]
    write_dict_rows(proposal_csv_path, proposal_csv_rows, proposal_fields)
    path_audit_csv = output / f"review-learning-path-audit-{stamp}.csv"
    path_audit_fields = [
        "file_id", "filename", "source_type", "path", "normalized_path", "status", "reason_codes",
    ]
    path_audit_rows = [{
        **item, "reason_codes": json.dumps(item["reason_codes"], ensure_ascii=False),
    } for item in path_audit]
    write_dict_rows(path_audit_csv, path_audit_rows, path_audit_fields)
    lines = ["# SCRUM-98 kandidaatregels uit portalbeoordelingen", "",
             "- Modus: **read-only**", f"- Beoordelingen geanalyseerd: **{len(rows)}**",
             f"- Minimum support: **{args.minimum_support}**",
             f"- Classificatiekandidaten: **{len(candidates)}**",
             f"- Privacykandidaten: **{len(privacy_candidates)}**",
             f"- Traject-/werkgeverkandidaten: **{len(trajectory_candidates)}**",
             "- Geactiveerde regels: **0**", "- Bestandsmutaties: **geen**", "",
             "| Bronfamilie | Nieuwe categorie | Nieuwe familie | Support | Confidence | Conflicten |",
             "|---|---|---|---:|---|---:|"]
    for item in candidates:
        lines.append(f"| {item['source_family_code']} | {item['target_category_code']} | "
                     f"{item['target_family_code']} | {item['support']} | {item['confidence']} | {item['conflict_count']} |")
    lines.extend(["", "## Privacykandidaten", "",
                  "| Signaal | Voorstel | Menselijk doel | Support | Agreement | Tegenvoorbeelden | Status |",
                  "|---|---|---|---:|---:|---:|---|"])
    for item in privacy_candidates:
        lines.append(
            f"| {item['pattern_evidence']} | {item['source_privacy_classification']} | "
            f"{item['target_privacy_classification']} | {item['support']} | "
            f"{item['agreement']:.0%} | {item['counterexample_count']} | candidate_only |"
        )
    lines.extend(["", "## Traject- en werkgeverkandidaten", "",
                  "| Traject | Herkenning | Support | Agreement | Tegenvoorbeelden | Status |",
                  "|---|---|---:|---:|---:|---|"])
    for item in trajectory_candidates:
        lines.append(
            f"| {item['trajectory_label']} | {item['match_term']} | {item['support']} | "
            f"{item['agreement']:.0%} | {item['counterexample_count']} | proposal_only |"
        )
    lines.extend(["", "## Kwaliteit van CORE-voorstellen", "",
                  "| Onderdeel | Beoordeeld | Ongewijzigd akkoord | Gecorrigeerd | Afgewezen | Agreement | Tegenvoorbeelden |",
                  "|---|---:|---:|---:|---:|---:|---:|"])
    for item in proposal_quality:
        lines.append(
            f"| {item['dimension']} | {item['judged_proposals']} | {item['accepted_unchanged']} | "
            f"{item['accepted_corrected']} | {item['rejected']} | {item['agreement']:.0%} | "
            f"{item['counterexample_count']} |"
        )
    audit_counts = {status: sum(item["status"] == status for item in path_audit)
                    for status in ("pass", "needs_review", "invalid")}
    lines.extend(["", "## Systematiek en passendheid van doelpaden", "",
                  f"- Geldig/passend: **{audit_counts['pass']}**",
                  f"- Review nodig: **{audit_counts['needs_review']}**",
                  f"- Ongeldig: **{audit_counts['invalid']}**", "",
                  "| Bron | Bestand | Status | Bevindingen |",
                  "|---|---|---|---|"])
    for item in path_audit:
        if item["status"] != "pass":
            lines.append(
                f"| {item['source_type']} | {item['filename']} | {item['status']} | "
                f"{', '.join(item['reason_codes'])} |"
            )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for latest, source in (("review-learning-candidates-latest.json", json_path),
                           ("review-learning-candidates-latest.md", md_path),
                           ("review-learning-privacy-candidates-latest.csv", privacy_csv_path),
                           ("review-learning-trajectory-candidates-latest.csv", trajectory_csv_path),
                           ("review-learning-proposal-quality-latest.csv", proposal_csv_path),
                           ("review-learning-path-audit-latest.csv", path_audit_csv)):
        (output / latest).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    print("SCRUM-98 read-only review-learning analysis complete")
    print(f"Report: {md_path.relative_to(ROOT)}")
    print(f"Details: {csv_path.relative_to(ROOT)}")
    print(f"Privacy details: {privacy_csv_path.relative_to(ROOT)}")
    print(f"Trajectory details: {trajectory_csv_path.relative_to(ROOT)}")
    print(f"Proposal quality: {proposal_csv_path.relative_to(ROOT)}")
    print(f"Path audit: {path_audit_csv.relative_to(ROOT)}")
    print(f"JSON: {json_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
