import unittest

from core.organization.privacy_classification import RULE_VERSION, propose_privacy


class PrivacyClassificationTests(unittest.TestCase):
    def test_passport_is_high_even_without_existing_classification(self):
        result = propose_privacy({
            "filename": "paspoort.pdf",
            "path": "/volume1/data/Documenten/Identiteit/paspoort.pdf",
        })
        self.assertEqual("high", result["classification"])
        self.assertEqual("high", result["confidence"])
        self.assertFalse(result["external_llm_content_allowed"])
        self.assertEqual(RULE_VERSION, result["rule_version"])

    def test_personal_classification_maps_to_medium(self):
        result = propose_privacy({"filename": "brief.docx", "sensitivity": "personal"})
        self.assertEqual("medium", result["classification"])
        self.assertIn("existing:personal", result["evidence"])

    def test_unknown_is_not_silently_low(self):
        result = propose_privacy({"filename": "document.pdf"})
        self.assertEqual("medium", result["classification"])
        self.assertEqual("low", result["confidence"])
        self.assertEqual("insufficient_privacy_evidence", result["reason_code"])

    def test_existing_highly_sensitive_cannot_be_lowered_by_missing_terms(self):
        result = propose_privacy({"filename": "scan.pdf", "sensitivity": "highly_sensitive"})
        self.assertEqual("high", result["classification"])


if __name__ == "__main__":
    unittest.main()
