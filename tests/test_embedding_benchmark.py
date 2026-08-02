import json
import tempfile
import unittest
from pathlib import Path

from core.semantic.embedding_benchmark import (
    MODEL_ID, MODEL_REVISION, collect_passages, load_manifest, run_benchmark,
)


class FakeVectors:
    def __init__(self, rows):
        self.shape = (rows, 384)


class FakeModel:
    max_seq_length = 4

    def tokenizer(self, passages, **kwargs):
        return {"input_ids": [[1] * len(passage.split()) for passage in passages]}

    def encode(self, passages, **kwargs):
        self.seen = passages
        return FakeVectors(len(passages))


class EmbeddingBenchmarkTests(unittest.TestCase):
    def manifest(self):
        return {
            "processing": "local_only", "external_ai_enabled": False,
            "database_writes_enabled": False, "embedding_enabled": False, "files": [
                {"file_id": 1, "approval": "approved", "path": "/volume1/a.docx"}
            ],
        }

    def test_manifest_rejects_external_ai_and_database_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            value = self.manifest()
            value["external_ai_enabled"] = True
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "external AI"):
                load_manifest(path)

    def test_collection_is_bounded_and_uses_e5_passage_prefix(self):
        passages, stats = collect_passages(
            self.manifest(), max_chunks=1,
            extractor=lambda path: ("one two three", 1),
        )
        self.assertEqual(["passage: one two three"], passages)
        self.assertEqual(1, stats["source_documents"])

    def test_result_contains_aggregates_but_no_text_or_vectors(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_benchmark(
                self.manifest(), Path(directory), max_chunks=2,
                model_factory=lambda path: FakeModel(),
                extractor=lambda path: ("one two three four five", 1),
            )
        serialized = json.dumps(result)
        self.assertEqual(MODEL_ID, result["model_id"])
        self.assertEqual(40, len(MODEL_REVISION))
        self.assertEqual(384, result["dimension"])
        self.assertEqual(1, result["chunks"])
        self.assertGreater(result["truncated_chunks"], 0)
        self.assertFalse(result["vectors_stored"])
        self.assertFalse(result["raw_text_stored"])
        self.assertNotIn("one two", serialized)

    def test_runtime_wrapper_disables_network_and_mounts_sources_read_only(self):
        root = Path(__file__).resolve().parents[1]
        wrapper = (root / "tools/semantic/embedding-benchmark").read_text("utf-8")
        self.assertIn("--network none", wrapper)
        self.assertIn("/volume1:/volume1:ro", wrapper)
        self.assertIn("project/models:/models:ro", wrapper)


if __name__ == "__main__":
    unittest.main()
