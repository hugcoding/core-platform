import unittest
from unittest import mock

from tools.runtime.classification_extract import (
    classify_content,
    date_candidates,
    process_row,
    temporal_inconsistencies,
)


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
        with (
            mock.patch(
                "tools.runtime.classification_extract.extract_text",
                return_value=("opleiding module les opdracht examen", 1, {}),
            ),
            mock.patch(
                "tools.runtime.classification_extract.Path.stat",
                return_value=mock.Mock(st_mtime=1_700_000_000),
            ),
        ):
            result = process_row(row)

        self.assertEqual("extracted", result["extraction_result"])
        self.assertNotIn("text", result)
        self.assertNotIn("opleiding module", str(result.values()))

    def test_empty_file_is_not_reported_as_parser_error(self):
        row = {
            "extraction_status": "ready_for_local_extraction",
            "extraction_route": "python-docx",
            "golden_path": "/volume1/Aantekeningen.docx",
            "filename": "Aantekeningen.docx",
            "size_bytes": "0",
            "content_category": "pending_content_extraction",
        }
        result = process_row(row)
        self.assertEqual("empty_file", result["extraction_result"])
        self.assertEqual("", result["extraction_error"])

    def test_password_error_receives_separate_review_status(self):
        row = {
            "extraction_status": "ready_for_local_extraction",
            "extraction_route": "pypdf",
            "golden_path": "/volume1/beveiligd.pdf",
            "filename": "beveiligd.pdf",
            "size_bytes": "10",
            "content_category": "pending_content_extraction",
        }
        with mock.patch(
            "tools.runtime.classification_extract.extract_text",
            side_effect=PermissionError("PDF requires a password"),
        ):
            result = process_row(row)
        self.assertEqual("password_required", result["extraction_result"])

    def test_date_candidates_are_extracted_without_context_text(self):
        self.assertEqual(
            ["12-05-2014", "2020-01-31"],
            date_candidates("Op 12-05-2014 en 2020-01-31 gebeurde iets."),
        )

    def test_temporal_inconsistencies_detect_invalid_order(self):
        self.assertEqual(
            ["created_after_modified"],
            temporal_inconsistencies("2020-01-02T00:00:00", "2020-01-01T00:00:00"),
        )

    def test_temporal_inconsistencies_localize_offsetless_amsterdam_time(self):
        self.assertEqual(
            [],
            temporal_inconsistencies(
                "2008-10-20T09:05:17",
                "2008-10-20T09:05:18+02:00",
            ),
        )

    def test_temporal_inconsistencies_compare_aware_values_by_instant(self):
        self.assertEqual(
            [],
            temporal_inconsistencies(
                "2020-01-01T10:00:00+01:00",
                "2020-01-01T09:30:00+00:00",
            ),
        )

    def test_temporal_inconsistencies_distinguish_conflicting_offsets(self):
        self.assertEqual(
            ["embedded_timezone_conflict"],
            temporal_inconsistencies(
                "2009-05-03T16:08:29+00:00",
                "2009-05-03T16:09:18+02:00",
            ),
        )


if __name__ == "__main__":
    unittest.main()
