import hashlib
import tempfile
import unittest
from pathlib import Path

from core.integrity.pdf_content_similarity import analyze_pdf, analyze_pdf_group


class FakePage:
    def __init__(self, text): self.text = text
    def extract_text(self): return self.text


class FakeReader:
    def __init__(self, source):
        marker = source.read().decode("utf-8")
        self.pages = [FakePage("Dezelfde   zichtbare tekst\n op één pagina")]
        self.metadata = {
            "/Title": "TransactieDetail", "/CreationDate": f"D:{marker}",
            "/ModDate": f"D:{marker}",
        }
        self.trailer = {"/ID": [f"id-{marker}", f"id-{marker}"]}
        self.is_encrypted = False
    def get_fields(self): return {}


class PdfContentSimilarityTests(unittest.TestCase):
    def test_metadata_variants_are_textual_candidates_not_exact_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for index, marker in enumerate(("145004", "145239", "145410")):
                path = Path(directory) / f"document {index}.pdf"
                path.write_text(marker, encoding="utf-8")
                paths.append(path)
            result = analyze_pdf_group(paths, reader_factory=FakeReader)
        self.assertEqual("textually_identical_pdf_candidate", result["relationship"])
        self.assertEqual("high", result["confidence"])
        self.assertEqual(3, len({item["content_sha256"] for item in result["documents"]}))
        self.assertEqual(1, len({item["normalized_text_sha256"] for item in result["documents"]}))
        self.assertIn("CreationDate", result["metadata_differences"])
        self.assertIn("document_id", result["metadata_differences"])
        self.assertTrue(result["requires_human_review"])
        self.assertFalse(result["automatic_deletion_allowed"])
        self.assertFalse(result["file_mutations"])

    def test_exact_bytes_remain_exact_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.pdf"; first.write_text("same", encoding="utf-8")
            second = Path(directory) / "second.pdf"; second.write_text("same", encoding="utf-8")
            result = analyze_pdf_group([first, second], reader_factory=FakeReader)
        self.assertEqual("exact_duplicate", result["relationship"])
        self.assertEqual("exact", result["confidence"])

    def test_analysis_does_not_return_extracted_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.pdf"; path.write_text("145004", encoding="utf-8")
            result = analyze_pdf(path, reader_factory=FakeReader)
        self.assertNotIn("text", result)
        self.assertEqual(
            hashlib.sha256("Dezelfde zichtbare tekst op één pagina".encode()).hexdigest(),
            result["normalized_text_sha256"],
        )
        self.assertFalse(result["database_writes"])


if __name__ == "__main__":
    unittest.main()
