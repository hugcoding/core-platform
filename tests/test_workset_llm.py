import json
import unittest
from unittest import mock

from core.semantic.workset_llm import (
    MAX_DOCUMENTS, PROMPT_VERSION, build_prompt, extract_bounded_context, validate_proposal,
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
        self.assertEqual("scrum-101-workset-llm-v2", PROMPT_VERSION)

    @mock.patch("core.semantic.workset_llm.extract_document", return_value=(" tekst  met   spaties ", 1))
    def test_extraction_does_not_return_unbounded_text(self, _extract):
        context = extract_bounded_context("/volume1/a.pdf")
        self.assertEqual("tekst met spaties", context["text"])
        self.assertEqual("ready", context["status"])

    @mock.patch("core.semantic.workset_llm.extract_document", return_value=("", 2))
    def test_pdf_without_extractable_text_recommends_ocr(self, _extract):
        context = extract_bounded_context("/volume1/scan.pdf")
        self.assertEqual("ocr_recommended", context["status"])
        self.assertEqual("ocr_recommended_no_extractable_text", context["reason"])
        self.assertTrue(context["ocr_recommended"])

    @mock.patch("core.semantic.workset_llm.extract_document", return_value=("", 0))
    def test_empty_office_document_does_not_recommend_ocr(self, _extract):
        context = extract_bounded_context("/volume1/leeg.docx")
        self.assertEqual("needs_review", context["status"])
        self.assertEqual("no_extractable_text", context["reason"])
        self.assertFalse(context["ocr_recommended"])

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

    def test_clearly_english_reason_abstains(self):
        proposal = validate_proposal(json.dumps({
            "file_id": 4, "abstained": False, "category_code": "work_career",
            "family_code": "motivation_letters", "lifecycle": "active",
            "privacy_advice": "medium", "confidence": "high",
            "relation_kind": "none", "related_file_ids": [],
            "reason": "This document contains data from the current offer and aligns with human examples.",
        }), 4)
        self.assertTrue(proposal["abstained"])
        self.assertEqual("reason_not_dutch", proposal["reason"])


if __name__ == "__main__":
    unittest.main()
