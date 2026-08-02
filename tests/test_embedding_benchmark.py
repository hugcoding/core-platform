import json
import tempfile
import unittest
from pathlib import Path

from core.semantic.embedding_benchmark import (
    MODEL_ID, MODEL_REVISION, TOKEN_CHUNKER_VERSION, collect_passages,
    load_manifest, run_benchmark,
)


class FakeVectors:
    def __init__(self, rows):
        self.shape = (rows, 384)


class FakeModel:
    max_seq_length = 512

    class Tokenizer:
        @staticmethod
        def encode(text, add_special_tokens=False):
            return text.split()

        @staticmethod
        def decode(tokens, skip_special_tokens=True):
            return " ".join(tokens)

        def __call__(self, passages, **kwargs):
            return {"input_ids": [[1] * (len(passage.split()) + 2) for passage in passages]}

    tokenizer = Tokenizer()

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
            self.manifest(), tokenizer=FakeModel.tokenizer, max_chunks=1,
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
        self.assertEqual(0, result["truncated_chunks"])
        self.assertEqual(TOKEN_CHUNKER_VERSION, result["chunker_version"])
        self.assertLessEqual(result["max_input_tokens"], result["model_max_sequence_length"])
        self.assertFalse(result["vectors_stored"])
        self.assertFalse(result["raw_text_stored"])
        self.assertNotIn("one two", serialized)

    def test_runtime_wrapper_disables_network_and_mounts_sources_read_only(self):
        root = Path(__file__).resolve().parents[1]
        wrapper = (root / "tools/semantic/embedding-benchmark").read_text("utf-8")
        self.assertIn("--network none", wrapper)
        self.assertIn("/volume1:/volume1:ro", wrapper)
        self.assertIn("project/models:/models:ro", wrapper)

    def test_image_is_cpu_only_and_build_context_excludes_models(self):
        root = Path(__file__).resolve().parents[1]
        dockerfile = (root / "Dockerfile.embedding-benchmark").read_text("utf-8")
        dockerignore = (root / ".dockerignore").read_text("utf-8")
        self.assertIn("download.pytorch.org/whl/cpu", dockerfile)
        self.assertNotIn("nvidia-", dockerfile)
        self.assertIn("project/models/", dockerignore)
        self.assertIn("project/exports/", dockerignore)

    def test_benchmark_does_not_rebuild_image_implicitly(self):
        root = Path(__file__).resolve().parents[1]
        wrapper = (root / "tools/semantic/embedding-benchmark").read_text("utf-8")
        self.assertNotIn("docker build", wrapper)
        self.assertIn("docker image inspect", wrapper)

    def test_token_chunking_has_deterministic_overlap(self):
        text = " ".join(f"w{index}" for index in range(12))
        passages, _ = collect_passages(
            self.manifest(), tokenizer=FakeModel.tokenizer, max_chunks=10,
            target_tokens=5, overlap_tokens=2, extractor=lambda path: (text, 1),
        )
        self.assertEqual("passage: w0 w1 w2 w3 w4", passages[0])
        self.assertEqual("passage: w3 w4 w5 w6 w7", passages[1])

    def test_benchmark_refuses_silent_model_truncation(self):
        class TinyModel(FakeModel):
            max_seq_length = 3
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "refusing silent truncation"):
                run_benchmark(
                    self.manifest(), Path(directory), model_factory=lambda path: TinyModel(),
                    extractor=lambda path: ("one two three four", 1),
                )


if __name__ == "__main__":
    unittest.main()
