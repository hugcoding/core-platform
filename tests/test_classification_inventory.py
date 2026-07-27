import unittest

from tools.runtime.classification_inventory import build_rows, classify_route


def row(extension):
    return {
        "content_group_id": "group", "content_sha256": "hash",
        "size_bytes": "10", "golden_file_id": "1",
        "filename": f"bestand.{extension}", "extension": extension,
        "mime_type": "application/octet-stream",
        "golden_path": f"/volume1/Documents/bestand.{extension}",
        "golden_confidence": "high", "golden_selection_status": "single_source",
        "golden_algorithm_version": "golden-v1", "physical_copy_count": "1",
    }


class ClassificationInventoryTest(unittest.TestCase):
    def test_modern_documents_receive_local_extractors(self):
        self.assertEqual(("python-docx", "ready_for_local_extraction"), classify_route(row("docx")))
        self.assertEqual(("pypdf", "ready_for_local_extraction"), classify_route(row("pdf")))
        self.assertEqual(("openpyxl", "ready_for_local_extraction"), classify_route(row("xlsx")))

    def test_legacy_office_requires_conversion(self):
        self.assertEqual(("legacy-office-conversion", "conversion_required"), classify_route(row("doc")))

    def test_target_classification_remains_pending(self):
        planned = build_rows([row("pdf")])[0]
        self.assertEqual("pending_content_extraction", planned["content_category"])
        self.assertEqual("", planned["proposed_target_path"])
        self.assertEqual("local_only_no_embeddings", planned["processing_scope"])


if __name__ == "__main__":
    unittest.main()
