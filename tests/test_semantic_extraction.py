import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.semantic.extraction import _pdf_text, extract_statistics, run_manifest, summarize


ROOT = Path(__file__).resolve().parents[1]


class ExtractionStatisticsTests(unittest.TestCase):
    def test_semantic_image_installs_local_aes_dependency(self):
        dockerfile = (ROOT / "Dockerfile.semantic-pilot").read_text(encoding="utf-8")
        self.assertIn("cryptography", dockerfile)

    def test_passwordless_aes_pdf_is_unlocked_locally(self):
        class Reader:
            is_encrypted = True
            pages = []

            def decrypt(self, password):
                self.password = password
                return 1

        reader = Reader()
        with mock.patch.dict("sys.modules", {"pypdf": mock.Mock(PdfReader=lambda _: reader)}):
            text, pages = _pdf_text(Path("encrypted.pdf"))

        self.assertEqual("", text)
        self.assertEqual(0, pages)
        self.assertEqual("", reader.password)

    def test_password_protected_pdf_is_reported_without_password(self):
        class Reader:
            is_encrypted = True

            def decrypt(self, password):
                return 0

        with mock.patch.dict("sys.modules", {"pypdf": mock.Mock(PdfReader=lambda _: Reader())}):
            with self.assertRaisesRegex(PermissionError, "password-protected PDF"):
                _pdf_text(Path("protected.pdf"))

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
            "external_ai_enabled": False,
            "database_writes_enabled": False,
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

    def test_manifest_refuses_external_ai_and_database_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            external = self._write_manifest(directory, external_ai_enabled=True)
            with self.assertRaisesRegex(ValueError, "external AI must be disabled"):
                list(run_manifest(external))
            database = self._write_manifest(directory, database_writes_enabled=True)
            with self.assertRaisesRegex(ValueError, "database writes must be disabled"):
                list(run_manifest(database))


class ExtractionSummaryTests(unittest.TestCase):
    def test_summary_contains_only_aggregate_statistics(self):
        results = [
            {"status": "extracted", "extension": "pdf", "has_extractable_text": True, "characters": 100, "words": 20, "pages": 2},
            {"status": "extracted", "extension": "pdf", "has_extractable_text": False, "characters": 0, "words": 0, "pages": 4},
            {"status": "error", "error_type": "PermissionError", "reason": "password-protected PDF"},
            {"status": "skipped"},
        ]

        report = summarize(results)

        self.assertEqual(4, report["documents"])
        self.assertEqual(2, report["extracted"])
        self.assertEqual(1, report["extractable_text"])
        self.assertEqual(1, report["needs_ocr"])
        self.assertEqual(1, report["password_protected"])
        self.assertEqual(1, report["errors"])
        self.assertEqual(20, report["words"])
        self.assertNotIn("text", report)


if __name__ == "__main__":
    unittest.main()
