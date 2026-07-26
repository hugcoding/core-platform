import unittest

from tools.runtime.migration_review import classify_review, extension_for


def row(category, path, action="review_required"):
    return {
        "category": category,
        "representative_path": path,
        "migration_action": action,
    }


class MigrationReviewTest(unittest.TestCase):
    def test_backup_folder_does_not_exclude_document(self):
        outcome, _ = classify_review(
            row("personal_document_candidate", "/volume1/backup/archive/report.docx", "candidate")
        )
        self.assertEqual("personal_document", outcome)

    def test_unknown_email_and_xml_are_documents(self):
        self.assertEqual(
            "personal_document",
            classify_review(row("unknown", "/volume1/source/message.msg"))[0],
        )
        self.assertEqual(
            "personal_document",
            classify_review(row("unknown", "/volume1/source/export.xml"))[0],
        )

    def test_media_is_deferred(self):
        outcome, _ = classify_review(
            row("personal_media_candidate", "/volume1/source/photo.jpg", "candidate")
        )
        self.assertEqual("deferred_media", outcome)

    def test_technical_and_ambiguous_formats_are_not_document_candidates(self):
        self.assertEqual(
            "project_or_technical",
            classify_review(row("unknown", "/volume1/source/code.class"))[0],
        )
        self.assertEqual(
            "manual_review",
            classify_review(row("unknown", "/volume1/source/design.eps"))[0],
        )
        self.assertEqual(
            "manual_review",
            classify_review(row("unknown", "/volume1/source/document.gdoc"))[0],
        )

    def test_extension_is_case_insensitive(self):
        self.assertEqual("docx", extension_for("/volume1/source/REPORT.DOCX"))


if __name__ == "__main__":
    unittest.main()
