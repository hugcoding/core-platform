import unittest
from unittest import mock

from tools.runtime.classification_extract import classify_content, process_row


class ClassificationExtractTest(unittest.TestCase):
    def test_content_outweighs_conflicting_source_path(self):
        category, confidence, reasons = classify_content(
            "Deze opleiding bevat een module, les, opdracht en examen.",
            "document.pdf",
            "/volume1/Documents/Wonen/document.pdf",
        )
        self.assertEqual("documenten/studie", category)
        self.assertEqual("high", confidence)
        self.assertIn("inhoud=", reasons)

    def test_sensitive_content_is_classified_separately(self):
        category, _, _ = classify_content(
            "Huisarts en ziekenhuis bespreken medische behandeling en medicatie.",
            "brief.pdf",
            "/volume1/Documents/brief.pdf",
        )
        self.assertEqual("gevoelig/gezondheid", category)

    def test_no_evidence_goes_to_uitzoeken(self):
        category, confidence, _ = classify_content(
            "willekeurige inhoud zonder bekende termen",
            "bestand.pdf",
            "/volume1/Documents/bestand.pdf",
        )
        self.assertEqual("documenten/uitzoeken", category)
        self.assertEqual("low", confidence)

    def test_raw_text_is_not_returned_in_result(self):
        row = {
            "extraction_status": "ready_for_local_extraction",
            "extraction_route": "pypdf",
            "golden_path": "/volume1/document.pdf",
            "filename": "document.pdf",
            "content_category": "pending_content_extraction",
        }
        with mock.patch(
            "tools.runtime.classification_extract.extract_text",
            return_value=("opleiding module les opdracht examen", 1),
        ):
            result = process_row(row)

        self.assertEqual("extracted", result["extraction_result"])
        self.assertNotIn("text", result)
        self.assertNotIn("opleiding module", str(result.values()))


if __name__ == "__main__":
    unittest.main()
