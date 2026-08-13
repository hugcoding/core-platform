import json
import unittest
from unittest import mock

from core.semantic.workset_llm import (
    MAX_DOCUMENTS, build_prompt, extract_bounded_context, validate_proposal,
)


class WorksetLlmTests(unittest.TestCase):
    def test_limit_is_five(self):
        self.assertEqual(5, MAX_DOCUMENTS)

    def test_prompt_contains_taxonomy_examples_and_bounded_text(self):
        system, user = build_prompt(
            {"file_id": 4, "filename": "brief.pdf", "path": "/volume1/brief.pdf",
             "core_category": "work_career", "core_family": "motivation_letters"},
            {"text": "inhoud"},
            [{"filename": "voorbeeld.pdf", "category_code": "work_career",
              "family_code": "motivation_letters"}], "system",
        )
        self.assertEqual("system", system)
        self.assertIn("allowed_categories", user)
        self.assertIn("voorbeeld.pdf => category=work_career", user)
        self.assertIn("DOCUMENT_TEXT:\ninhoud", user)

    @mock.patch("core.semantic.workset_llm.extract_document", return_value=(" tekst  met   spaties ", 1))
    def test_extraction_does_not_return_unbounded_text(self, _extract):
        context = extract_bounded_context("/volume1/a.pdf")
        self.assertEqual("tekst met spaties", context["text"])
        self.assertEqual("ready", context["status"])

    def test_valid_proposal_uses_canonical_codes(self):
        proposal = validate_proposal(json.dumps({
            "file_id": 4, "abstained": False, "category_code": "work_career",
            "family_code": "motivation_letters", "lifecycle": "active",
            "privacy_advice": "medium", "confidence": "high",
            "relation_kind": "exported_representation", "related_file_ids": [3],
            "reason": "PDF-uitvoer van een motivatiebrief",
        }), 4)
        self.assertEqual("ready", proposal["status"])
        self.assertEqual("motivation_letters", proposal["family_code"])

    def test_unknown_taxonomy_abstains(self):
        proposal = validate_proposal(json.dumps({
            "file_id": 4, "category_code": "invented", "family_code": "invented",
            "lifecycle": "active", "privacy_advice": "low", "confidence": "high",
            "relation_kind": "none", "related_file_ids": [], "reason": "x",
        }), 4)
        self.assertTrue(proposal["abstained"])


if __name__ == "__main__":
    unittest.main()
