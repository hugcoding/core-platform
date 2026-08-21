import unittest

from core.organization.review_taxonomy import category_options, contextual_options, taxonomy


class ReviewTaxonomyTests(unittest.TestCase):
    def test_vve_context_gets_small_explained_shortlist(self):
        result = contextual_options(
            {"filename": "MEMO riolering.pdf", "path": "/Documenten/Administratie/VVE Eksterlaan/MEMO riolering.pdf"},
            {"category_code": "home_living", "document_family_code": "general"},
        )
        self.assertLessEqual(len(result["compact_families"]), 5)
        self.assertIn("vve_documents", [item["code"] for item in result["compact_families"]])
        self.assertEqual("deterministic_context_v1", result["selection_method"])

    def test_full_taxonomy_has_categories_and_more_families(self):
        contract = taxonomy()
        self.assertIn("home_living", [item["code"] for item in contract["categories"]])
        self.assertGreater(len(contract["families"]), 5)
        self.assertNotIn("needs_review", [item["code"] for item in contract["categories"]])

    def test_work_path_gets_content_proposal_instead_of_workflow_state(self):
        options = category_options(
            {"filename": "getekend contractvoorstel.pdf", "path": "/Documenten/Werk/getekend contractvoorstel.pdf"},
            {"category_code": "needs_review"},
        )
        self.assertEqual("work_career", options[0]["code"])
        self.assertNotIn("needs_review", [item["code"] for item in options])

    def test_unknown_document_does_not_fallback_to_personal_identity(self):
        options = category_options(
            {"filename": "onbekend.pdf", "path": "/Documenten/onbekend.pdf"},
            {"category_code": "needs_review"},
        )
        self.assertTrue(options)
        self.assertTrue(all(item["reason_codes"] == ["alternative"] for item in options))

    def test_mortgage_documents_are_canonically_ranked_under_home(self):
        options = category_options(
            {"filename": "Hypotheek ABN overzicht.pdf", "path": "/Documenten/Hypotheek/"},
            {"category_code": "needs_review"},
        )
        self.assertEqual("home_living", options[0]["code"])
        mortgage = next(
            item for item in taxonomy()["families"]
            if item["code"] == "mortgage_documents"
        )
        self.assertEqual(["home_living"], mortgage["categories"])


if __name__ == "__main__":
    unittest.main()
