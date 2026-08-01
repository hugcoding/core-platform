import json
import tempfile
import unittest
from pathlib import Path

from core.semantic.chunking import (
    chunk_text,
    plan_document_chunks,
    run_manifest,
    summarize,
)


class ChunkingTests(unittest.TestCase):
    def test_chunks_have_deterministic_overlap(self):
        text = " ".join(f"word-{index}" for index in range(10))

        chunks = chunk_text(text, target_words=4, overlap_words=1)

        self.assertEqual(3, len(chunks))
        self.assertEqual("word-3", chunks[0].split()[-1])
        self.assertEqual("word-3", chunks[1].split()[0])

    def test_empty_pdf_is_marked_for_ocr(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scan.pdf"
            path.write_bytes(b"pdf")

            result = plan_document_chunks(
                42,
                path,
                extractor=lambda _: ("", 28),
            )

        self.assertEqual("needs_ocr", result["status"])
        self.assertEqual(0, result["chunks"])

    def test_chunk_ids_are_stable_for_same_file_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.docx"
            path.write_bytes(b"stable source")
            extractor = lambda _: (" ".join(["word"] * 700), 0)

            first = plan_document_chunks(7, path, extractor=extractor)
            second = plan_document_chunks(7, path, extractor=extractor)

        self.assertEqual(first["content_version"], second["content_version"])
        self.assertEqual(first["chunk_ids"], second["chunk_ids"])
        self.assertNotIn("text", first)


class ChunkManifestTests(unittest.TestCase):
    def test_summary_contains_only_aggregate_statistics(self):
        results = [
            {"status": "planned", "chunks": 2, "estimated_tokens": 100},
            {"status": "needs_ocr", "chunks": 0, "estimated_tokens": 0},
        ]

        report = summarize(results)

        self.assertEqual(2, report["documents"])
        self.assertEqual(2, report["chunks"])
        self.assertEqual(1, report["needs_ocr"])

    def test_manifest_refuses_embedding_enabled_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "processing": "local_only",
                        "embedding_enabled": True,
                        "external_ai_enabled": False,
                        "database_writes_enabled": False,
                        "files": [],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "embeddings must be disabled"):
                run_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
