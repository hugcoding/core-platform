import json
import tempfile
import unittest
from pathlib import Path

from core.semantic.extraction import extract_statistics, run_manifest


class ExtractionStatisticsTests(unittest.TestCase):
    def test_docx_reports_statistics_without_returning_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pilot.docx"
            path.write_bytes(b"placeholder")

            result = extract_statistics(
                path,
                docx_loader=lambda _: ("Een lokale extractie proef", 0),
            )

        self.assertEqual("docx", result["extension"])
        self.assertEqual(4, result["words"])
        self.assertTrue(result["has_extractable_text"])
        self.assertNotIn("text", result)

    def test_pdf_reports_page_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pilot.pdf"
            path.write_bytes(b"placeholder")

            result = extract_statistics(
                path,
                pdf_loader=lambda _: ("Pagina een en twee", 2),
            )

        self.assertEqual(2, result["pages"])
        self.assertEqual(4, result["words"])


class PilotManifestTests(unittest.TestCase):
    def _write_manifest(self, directory: str, **overrides) -> Path:
        payload = {
            "processing": "local_only",
            "embedding_enabled": False,
            "files": [
                {"file_id": 1, "approval": "approved", "path": "/pilot/one.pdf"},
                {"file_id": 2, "approval": "needs_review", "path": "/pilot/two.pdf"},
            ],
            **overrides,
        }
        path = Path(directory) / "manifest.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_only_approved_files_are_extracted(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._write_manifest(directory)
            results = list(
                run_manifest(
                    manifest,
                    extractor=lambda _: {
                        "extension": "pdf",
                        "size_bytes": 1,
                        "characters": 10,
                        "words": 2,
                        "pages": 1,
                        "has_extractable_text": True,
                    },
                )
            )

        self.assertEqual("extracted", results[0]["status"])
        self.assertEqual("skipped", results[1]["status"])

    def test_manifest_refuses_embeddings(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._write_manifest(directory, embedding_enabled=True)

            with self.assertRaisesRegex(ValueError, "embeddings must be disabled"):
                list(run_manifest(manifest))


if __name__ == "__main__":
    unittest.main()
