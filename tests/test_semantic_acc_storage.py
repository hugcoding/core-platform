import json
import unittest

from core.semantic.acc_storage import build_plan, render_apply_sql


class SemanticAccStorageTests(unittest.TestCase):
    def manifest(self):
        return json.dumps({
            "source": "/volume1/data/import/cloud/onedrive/current",
            "selection_version": "onedrive-golden-v1",
            "embedding_enabled": False,
            "external_ai_enabled": False,
            "files": [
                {"file_id": 1, "approval": "approved", "path": "/volume1/a.pdf", "size_bytes": 100,
                 "content_group_id": "28e11fef-f188-4845-984a-2027540289d0", "content_sha256": "a" * 64},
                {"file_id": 2, "approval": "approved", "path": "/volume1/b.pdf", "size_bytes": 200,
                 "content_group_id": "4b662b54-f965-45ae-b898-1febfee9d4e6", "content_sha256": "b" * 64},
            ],
        }, sort_keys=True).encode()

    def results(self):
        return [
            {"file_id": 1, "status": "planned", "content_version": "a" * 64,
             "characters": 20, "words": 4, "pages": 1, "estimated_tokens": 5, "chunks": 1,
             "chunk_metadata": [{"chunk_id": "c" * 64, "ordinal": 0, "words": 4, "characters": 20}]},
            {"file_id": 2, "status": "error", "error_type": "PermissionError", "reason": "password-protected PDF"},
        ]

    def test_plan_is_deterministic_and_contains_no_text(self):
        first = build_plan(self.manifest(), self.results())
        second = build_plan(self.manifest(), self.results())
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(2, first["document_count"])
        self.assertEqual(1, first["chunk_count"])
        self.assertEqual("password_protected", first["documents"][1]["status"])
        self.assertNotIn("text", json.dumps(first))

    def test_changed_file_content_is_rejected(self):
        results = self.results()
        results[0]["content_version"] = "changed"
        with self.assertRaisesRegex(ValueError, "content hash changed"):
            build_plan(self.manifest(), results)

    def test_apply_sql_is_idempotent_and_validates_golden_provenance(self):
        sql = render_apply_sql(build_plan(self.manifest(), self.results()))
        self.assertIn("ON CONFLICT (id) DO UPDATE", sql)
        self.assertIn("ON CONFLICT (run_id, file_id) DO UPDATE", sql)
        self.assertIn("cg.golden_file_id=f.id", sql)
        self.assertIn("semantic document provenance validation failed", sql)
        self.assertNotIn("password-protected PDF'", sql.split("error_reason", 1)[0])


class SemanticAccMigrationTests(unittest.TestCase):
    def test_schema_stores_metadata_but_no_text_or_embedding(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        sql = (root / "database/migrations/20260801_add_semantic_acc_metadata.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS public.semantic_runs", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS public.semantic_chunks", sql)
        self.assertNotIn("chunk_text", sql)
        self.assertNotIn(" vector", sql.lower())


if __name__ == "__main__":
    unittest.main()
