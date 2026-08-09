#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.exports.csv_format import write_dict_rows
from core.semantic.personal_classification import (
    PROMPT_VERSION, SCHEMA_VERSION, approved_manifest, build_classification_prompt,
    build_manifest, review_result, select_personal_candidates, validate_classification,
)
from core.semantic.pilot_selection import parse_timestamp
from core.semantic.rag import GenerationRequest, OpenAICompatibleLocalProvider
from tools.runtime.migration_inventory import run_query, shutil_which


DEFAULT_SOURCE = "/volume1/data/import/cloud/onedrive/current/Documenten"
QUERY = r"""
SELECT v.golden_file_id AS file_id, v.content_group_id, v.golden_file_id,
       v.golden_path AS path, v.golden_filename AS filename, v.extension,
       v.size_bytes, v.content_sha256, f.modified_at_fs,
       v.semantic_metadata_current
FROM public.v_semantic_golden_records v
JOIN public.files f ON f.id = v.golden_file_id
WHERE v.golden_path = :'source' OR v.golden_path LIKE :'source_prefix'
ORDER BY v.golden_path, v.golden_file_id;
"""
REVIEW_FIELDS = [
    "file_id", "content_group_id", "path", "extension", "size_bytes",
    "modified_at_fs", "selection_stratum", "selection_size_bucket",
    "selection_status", "selection_reason",
]
RESULT_FIELDS = [
    "file_id", "filename", "source_path", "status", "document_type", "category",
    "document_family", "topics", "lifecycle", "suggested_path", "sensitivity",
    "confidence", "reason", "needs_review",
]


def load_rows(source: str) -> list[dict]:
    docker = os.getenv("DOCKER_BIN", "docker")
    if docker == "docker" and not shutil_which(docker) and Path("/usr/local/bin/docker").exists():
        docker = "/usr/local/bin/docker"
    command = [docker, "exec", os.getenv("POSTGRES_CONTAINER", "postgres"), "psql",
               "-U", os.getenv("DB_USER", "hugo"), "-d", os.getenv("DB_NAME", "nasdb_test")]
    return list(csv.DictReader(io.StringIO(run_query(command, QUERY, source))))


def build_contexts(manifest: dict, max_chunks: int) -> list[dict]:
    image = os.getenv("SEMANTIC_BENCHMARK_IMAGE", "core-semantic-embedding-benchmark:local")
    command = [
        "docker", "run", "--rm", "-i", "--network", "none", "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=1g", "--volume", "/volume1:/volume1:ro",
        "--volume", f"{ROOT / 'core'}:/app/core:ro",
        "--volume", f"{ROOT / 'project/models'}:/models:ro", image,
        "python", "-m", "core.semantic.classification_context",
        "--model-path", "/models/multilingual-e5-small", "--max-chunks", str(max_chunks),
    ]
    completed = subprocess.run(command, input=json.dumps(manifest), capture_output=True, text=True)
    if completed.returncode:
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        raise RuntimeError("local classification context extraction failed")
    return json.loads(completed.stdout.strip().splitlines()[-1])["documents"]


def classify_documents(documents: list[dict], *, prompt: dict, model: str,
                       endpoint: str, timeout_seconds: int, checkpoint: Path,
                       existing_results: list[dict] | None = None) -> tuple[list[dict], dict]:
    provider = OpenAICompatibleLocalProvider(endpoint, timeout_seconds=timeout_seconds)
    results, usage = list(existing_results or []), Counter()
    completed_ids = {int(row["file_id"]) for row in results}
    started = time.monotonic()
    for position, document in enumerate(documents, start=1):
        file_id = int(document["file_id"])
        if file_id in completed_ids:
            print(f"[{position}/{len(documents)}] resume skip file_id={file_id}", file=sys.stderr)
            continue
        print(f"[{position}/{len(documents)}] classify file_id={file_id}", file=sys.stderr)
        item_started = time.monotonic()
        if document["status"] != "ready":
            result = review_result(file_id, document.get("error") or "context_not_ready")
        else:
            system, user = build_classification_prompt(document, prompt["system_prompt"])
            try:
                generated = provider.generate(GenerationRequest(model, system, user))
                result = validate_classification(generated["content"], file_id)
                usage.update({key: int(value) for key, value in generated.get("usage", {}).items()
                              if isinstance(value, (int, float))})
            except Exception as exc:
                result = review_result(file_id, f"provider_error:{type(exc).__name__}:{exc}")
        result.update({
            "filename": document["filename"], "source_path": document["path"],
            "duration_seconds": round(time.monotonic() - item_started, 3),
        })
        results.append(result)
        checkpoint.write_text(json.dumps({
            "schema_version": SCHEMA_VERSION, "status": "running",
            "selected_file_ids": [int(item["file_id"]) for item in documents],
            "results": results,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return results, {
        "provider_id": provider.provider_id, "model": model, "usage": dict(usage),
        "classification_seconds": round(time.monotonic() - started, 3),
    }


def render_report(manifest: dict, results: list[dict], provider: dict | None) -> str:
    statuses = Counter(row["status"] for row in results)
    categories = Counter(row["category"] for row in results)
    lifecycles = Counter(row["lifecycle"] for row in results)
    pending = sum(item.get("approval") == "pending_review" for item in manifest["files"])
    lines = [
        "# SCRUM-85 persoonlijke golden-recordclassificatie", "",
        f"- Geselecteerd: **{len(manifest['files'])}**",
        f"- Wacht op manifestreview: **{pending}**",
        f"- Geclassificeerd: **{statuses['classified']}**",
        f"- Technisch niet geclassificeerd: **{len(results) - statuses['classified']}**",
        f"- Menselijke review vereist: **{len(results)}**",
        "- Read-only: **ja**", "- Bestandsmutaties: **nee**", "- Databasewrites: **nee**", "",
        "## Categorieën", "",
        *[f"- `{key}`: **{value}**" for key, value in sorted(categories.items())], "",
        "## Lifecyclevoorstellen", "",
        *[f"- `{key}`: **{value}**" for key, value in sorted(lifecycles.items())], "",
    ]
    if provider:
        lines.extend(["## Lokale provider", "", f"- Provider: `{provider['provider_id']}`",
                      f"- Model: `{provider['model']}`",
                      f"- Classificatietijd: **{provider['classification_seconds']} s**",
                      f"- Tokens: `{provider['usage']}`", ""])
    lines.extend(["## Voorstellen", ""])
    for row in results:
        lines.append(
            f"- file_id `{row['file_id']}` — `{row['document_type']}` / `{row['category']}` / "
            f"`{row['lifecycle']}` → `{row['suggested_path']}` ({row['confidence']})"
        )
    lines.extend(["", "Alle voorstellen vereisen menselijke review. Er is geen bestand verplaatst of gewijzigd.", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only local classification of personal golden records.")
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--cutoff")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--manifest", help="Reviewed personal classification manifest JSON")
    parser.add_argument("--max-chunks", type=int, default=3, choices=(1, 2, 3))
    parser.add_argument("--model")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--prompt", default=str(ROOT / "project/prompts/scrum-85-personal-classification-v1.json"))
    parser.add_argument("--resume", help="Resume from a personal-classification checkpoint JSON")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run:
        if args.manifest or args.model:
            parser.error("--dry-run cannot be combined with --manifest or --model")
        if not args.cutoff:
            parser.error("--cutoff is required for --dry-run selection")
    elif not args.manifest or not args.model:
        parser.error("classification requires both --manifest and --model")

    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
    export_dir = ROOT / "project/exports/semantic-pilot"
    export_dir.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        source = args.source.rstrip("/")
        if not source.startswith("/volume1/") or source == "/volume1/data":
            parser.error("source must be an absolute path below /volume1 and may not be /volume1/data")
        try:
            cutoff = parse_timestamp(args.cutoff)
        except ValueError:
            parser.error("cutoff must be a valid ISO 8601 timestamp")
        rows = load_rows(source)
        selected, excluded = select_personal_candidates(rows, cutoff=cutoff, limit=args.limit)
        manifest = build_manifest(selected, source=source, cutoff=cutoff)
        manifest_path = export_dir / f"personal-golden-classification-manifest-{stamp}.json"
        review_path = export_dir / f"personal-golden-classification-selection-{stamp}.csv"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_dict_rows(review_path, ({field: row.get(field, "") for field in REVIEW_FIELDS}
                                      for row in [*selected, *excluded]), REVIEW_FIELDS)
        results, provider = [], None
    else:
        input_manifest_path = Path(args.manifest).resolve()
        manifest = json.loads(input_manifest_path.read_text(encoding="utf-8"))
        source = str(manifest.get("source") or "").rstrip("/")
        if not source.startswith("/volume1/") or source == "/volume1/data":
            raise ValueError("manifest source is outside the allowed personal source scope")
        manifest = approved_manifest(manifest, load_rows(source))
        selected, review_path = manifest["files"], None
        manifest_path = input_manifest_path
        prompt = json.loads(Path(args.prompt).read_text(encoding="utf-8"))
        if prompt.get("prompt_version") != PROMPT_VERSION:
            raise ValueError("unsupported prompt version")
        contexts = build_contexts(manifest, args.max_chunks)
        existing_results = None
        if args.resume:
            resume_path = Path(args.resume).resolve()
            resume_payload = json.loads(resume_path.read_text(encoding="utf-8"))
            existing_results = resume_payload.get("results", [])
            selected_ids = {int(item["file_id"]) for item in manifest["files"]}
            checkpoint_ids = {int(item) for item in resume_payload.get("selected_file_ids", [])}
            if checkpoint_ids != selected_ids or any(
                int(item["file_id"]) not in selected_ids for item in existing_results
            ):
                raise ValueError("resume checkpoint does not match the current selection")
            checkpoint = resume_path
        else:
            checkpoint = export_dir / f"personal-golden-classification-checkpoint-{stamp}.json"
        results, provider = classify_documents(
            contexts, prompt=prompt, model=args.model, endpoint=args.endpoint,
            timeout_seconds=args.timeout_seconds, checkpoint=checkpoint,
            existing_results=existing_results,
        )
        checkpoint.unlink(missing_ok=True)
    report = {
        "schema_version": SCHEMA_VERSION, "prompt_version": PROMPT_VERSION,
        "status": "planned" if args.dry_run else "completed",
        "read_only": True, "database_writes": False, "file_mutations": False,
        "manifest": str(manifest_path), "selected": len(selected),
        "results": results, "provider": provider,
    }
    json_path = export_dir / f"personal-golden-classification-{stamp}.json"
    md_path = export_dir / f"personal-golden-classification-{stamp}.md"
    csv_path = export_dir / f"personal-golden-classification-review-{stamp}.csv"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_report(manifest, results, provider), encoding="utf-8")
    write_dict_rows(csv_path, ({
        field: " | ".join(row["topics"]) if field == "topics" else row.get(field, "")
        for field in RESULT_FIELDS
    } for row in results), RESULT_FIELDS)
    summary = {
        "status": report["status"], "selected": len(selected), "read_only": True,
        "manifest": str(manifest_path),
        "json_report": str(json_path.relative_to(ROOT)), "markdown_report": str(md_path.relative_to(ROOT)),
        "review_csv": str(csv_path.relative_to(ROOT)),
    }
    if review_path is not None:
        summary["selection_csv"] = str(review_path.relative_to(ROOT))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
