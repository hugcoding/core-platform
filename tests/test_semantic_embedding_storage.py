import json
import unittest
from pathlib import Path

from core.semantic.embedding_storage import build_storage_plan, render_apply_sql
from core.semantic.embedding_persist import build_embedding_plan, collect_embedding_chunks


class FakeVectors(list):
    def tolist(self):
        return list(self)


class FakeModel:
    class Tokenizer:
        @staticmethod
        def encode(text, **kwargs):
            return text.split()

        @staticmethod
        def decode(tokens, **kwargs):
            return " ".join(tokens)

    tokenizer = Tokenizer()

    def encode(self, passages, **kwargs):
        return FakeVectors([[0.1] * 384 for _ in passages])


class SemanticEmbeddingStorageTests(unittest.TestCase):
    def manifest(self):
        return json.dumps({
            "processing": "local_only",
            "external_ai_enabled": False,
            "database_writes_enabled": False,
            "embedding_enabled": False,
            "files": [{
                "file_id": 7,
                "approval": "approved",
                "content_sha256": "a" * 64,
                "path": "/volume1/a.pdf",
            }],
        }, sort_keys=True).encode()

    def chunk(self):
        return {
            "file_id": 7,
            "chunk_id": "chunk-1",
            "ordinal": 0,
            "content_sha256": "a" * 64,
            "token_count": 12,
            "embedding": [0.1] * 384,
        }

    def test_plan_is_acc_local_and_uses_batch_four(self):
        plan = build_storage_plan(self.manifest(), [self.chunk()])
        self.assertEqual("acceptance", plan["environment"])
        self.assertEqual(4, plan["batch_size"])
        self.assertFalse(plan["network_enabled"])
        self.assertFalse(plan["raw_text_stored"])
        self.assertEqual(384, plan["dimension"])

    def test_plan_rejects_changed_content_and_wrong_dimension(self):
        chunk = self.chunk()
        chunk["content_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "content hash changed"):
            build_storage_plan(self.manifest(), [chunk])
        chunk = self.chunk()
        chunk["embedding"] = [0.1]
        with self.assertRaisesRegex(ValueError, "dimension 384"):
            build_storage_plan(self.manifest(), [chunk])

    def test_sql_is_idempotent_and_never_stores_raw_text(self):
        sql = render_apply_sql(build_storage_plan(self.manifest(), [self.chunk()]))
        self.assertIn("semantic_embeddings_acc", sql)
        self.assertIn("ON CONFLICT", sql)
        self.assertIn("semantic embedding count validation failed", sql)
        self.assertNotIn("/volume1/a.pdf", sql)
        self.assertNotIn("raw_text,", sql)

    def test_migration_and_rollback_exist(self):
        root = Path(__file__).resolve().parents[1]
        migration = (root / "database/migrations/20260802_add_semantic_embeddings_acc.sql").read_text("utf-8")
        rollback = (root / "database/migrations/rollback/20260802_add_semantic_embeddings_acc.sql").read_text("utf-8")
        self.assertIn("vector(384)", migration)
        self.assertIn("semantic_documents(run_id, file_id)", migration)
        self.assertIn("DROP TABLE IF EXISTS public.semantic_embeddings_acc", rollback)

    def test_persist_plan_contains_vectors_but_no_raw_text(self):
        plan = build_embedding_plan(
            self.manifest(), Path("."), model_factory=lambda path: FakeModel(),
            extractor=lambda path: ("one two three", 1),
        )
        serialized = json.dumps(plan)
        self.assertEqual(1, plan["chunk_count"])
        self.assertEqual(4, plan["batch_size"])
        self.assertEqual(384, len(plan["chunks"][0]["embedding"]))
        self.assertNotIn("passage:", serialized)
        self.assertNotIn("one two three", serialized)

    def test_runtime_command_requires_explicit_mode_and_offline_container(self):
        root = Path(__file__).resolve().parents[1]
        runtime = (root / "tools/runtime/semantic_embedding_acc.py").read_text("utf-8")
        command = (root / "tools/runtime/core").read_text("utf-8")
        self.assertIn('"--network", "none"', runtime)
        self.assertIn('"--tmpfs", "/tmp:rw,noexec,nosuid,size=1g"', runtime)
        self.assertIn('mode.add_argument("--apply"', runtime)
        self.assertIn("completed.stderr", runtime)
        self.assertIn("embedding-acc)", command)


if __name__ == "__main__":
    unittest.main()
