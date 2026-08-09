import json
import unittest
from pathlib import Path

from core.semantic.classification_storage import (
    build_proposal_plan, build_review_plan, render_proposal_apply_sql, render_review_apply_sql,
)


class ClassificationStorageTests(unittest.TestCase):
    def manifest(self):
        return json.dumps({
            "processing": "local_only", "external_ai_enabled": False,
            "files": [{"file_id": 7, "approval": "approved",
                       "content_group_id": "28e11fef-f188-4845-984a-2027540289d0",
                       "content_sha256": "a" * 64, "path": "/volume1/private.pdf"}],
        }, sort_keys=True).encode()

    def report(self):
        result = {
            "file_id": 7, "status": "classified", "document_type": "invoice",
            "model_category": "finance", "category": "finance",
            "model_document_family": "Invoices", "document_family": "invoices",
            "topics": ["energy"], "lifecycle": "active_candidate",
            "suggested_path": "Active/Finance/invoices/invoice.pdf",
            "model_sensitivity": "sensitive", "sensitivity": "sensitive",
            "sensitivity_signals": ["financial"], "model_confidence": "high",
            "confidence": "high", "normalization_warnings": [], "reason": "Invoice content",
        }
        return json.dumps({
            "schema_version": "personal-golden-classification-v2",
            "prompt_version": "scrum-85-personal-classification-v2", "status": "completed",
            "read_only": True, "database_writes": False, "file_mutations": False,
            "results": [result], "provider": {"provider_id": "openai-compatible-local",
                "model": "qwen3.6:latest", "classification_seconds": 4.2,
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}},
        }, sort_keys=True).encode()

    def test_proposal_plan_is_deterministic_and_contains_no_path_or_raw_text(self):
        first = build_proposal_plan(self.report(), self.manifest())
        second = build_proposal_plan(self.report(), self.manifest())
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(first["proposals"][0]["id"], second["proposals"][0]["id"])
        self.assertEqual(1, first["proposal_count"])
        serialized = json.dumps(first)
        self.assertNotIn("/volume1/private.pdf", serialized)
        self.assertNotIn("raw_text", serialized.replace('"raw_text_stored": false', ""))

    def test_proposal_sql_is_idempotent_and_checks_current_golden_hash(self):
        sql = render_proposal_apply_sql(build_proposal_plan(self.report(), self.manifest()))
        self.assertIn("ON CONFLICT (id) DO NOTHING", sql)
        self.assertIn("cg.golden_file_id=f.id", sql)
        self.assertIn("f.content_sha256", sql)
        self.assertIn("proposal_sha256", sql)
        self.assertIn("proposal count validation failed", sql)

    def test_report_contract_and_manifest_identity_are_enforced(self):
        report = json.loads(self.report())
        report["database_writes"] = True
        with self.assertRaisesRegex(ValueError, "must not have written"):
            build_proposal_plan(json.dumps(report).encode(), self.manifest())
        report = json.loads(self.report())
        report["results"][0]["file_id"] = 8
        with self.assertRaisesRegex(ValueError, "unknown file_id"):
            build_proposal_plan(json.dumps(report).encode(), self.manifest())

    def test_review_is_append_only_and_idempotent(self):
        proposal_id = build_proposal_plan(self.report(), self.manifest())["proposals"][0]["id"]
        review = build_review_plan({
            "proposal_id": proposal_id, "idempotency_key": "review-7-v1", "decision": "accepted",
            "reviewer": "hugo", "reviewed_at": "2026-08-09T13:00:00+02:00",
            "category": "finance", "document_family": "invoices", "lifecycle": "active_candidate",
            "suggested_path": "Active/Finance/invoices/invoice.pdf", "sensitivity": "sensitive",
            "confidence": "high", "notes": "checked",
        })
        self.assertEqual(review["id"], build_review_plan({**review, "id": "ignored"})["id"])
        sql = render_review_apply_sql(review)
        self.assertIn("ON CONFLICT (idempotency_key) DO NOTHING", sql)
        self.assertNotIn("UPDATE public.classification_reviews", sql)

    def test_accepted_review_requires_final_values(self):
        with self.assertRaisesRegex(ValueError, "valid category"):
            build_review_plan({"proposal_id": "28e11fef-f188-4845-984a-2027540289d0",
                "idempotency_key": "x", "decision": "accepted", "reviewer": "hugo",
                "reviewed_at": "2026-08-09T13:00:00+02:00"})

    def test_migration_view_and_rollback(self):
        root = Path(__file__).resolve().parents[1]
        migration = (root / "database/migrations/20260809_add_classification_acc_storage.sql").read_text("utf-8")
        rollback = (root / "database/migrations/rollback/20260809_add_classification_acc_storage.sql").read_text("utf-8")
        for name in ("classification_runs", "classification_proposals", "classification_reviews",
                     "v_current_file_classification"):
            self.assertIn(name, migration)
        self.assertIn("DISTINCT ON (p.file_id)", migration)
        self.assertIn("cg.golden_file_id = f.id", migration)
        self.assertIn("DROP TABLE IF EXISTS public.classification_runs", rollback)

    def test_cli_requires_explicit_mode_and_is_routed(self):
        root = Path(__file__).resolve().parents[1]
        runtime = (root / "tools/runtime/semantic_classification_acc.py").read_text("utf-8")
        command = (root / "tools/runtime/core").read_text("utf-8")
        self.assertIn("add_mutually_exclusive_group(required=True)", runtime)
        self.assertIn("classification-acc)", command)


if __name__ == "__main__":
    unittest.main()
