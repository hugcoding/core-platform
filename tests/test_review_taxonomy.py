import unittest

from core.organization.review_taxonomy import (
    build_taxonomy_proposals, category_options, contextual_options, extend_taxonomy,
    taxonomy, taxonomy_extension_code,
)


class ReviewTaxonomyTests(unittest.TestCase):
    def test_human_family_proposals_are_grouped_as_pending_evidence(self):
        reviews = [{
            "id": "00000000-0000-0000-0000-000000000001", "file_id": 7,
            "review_type": "target_path", "decision": "accepted",
            "corrected_category_code": "learning_development",
            "proposed_family_label": "Cursusmateriaal",
        }]
        result = build_taxonomy_proposals(reviews)
        self.assertEqual(1, len(result))
        self.assertEqual("family", result[0]["proposal_type"])
        self.assertEqual("pending", result[0]["decision"])
        self.assertEqual(1, result[0]["support"])

    def test_accepted_extension_is_added_without_mutating_base_taxonomy(self):
        base = taxonomy()
        code = taxonomy_extension_code("Cursusmateriaal")
        result = extend_taxonomy(base, [{
            "proposal_type": "family", "taxonomy_code": code,
            "proposed_label": "Cursusmateriaal", "category_code": "learning_development",
        }])
        self.assertNotIn(code, [item["code"] for item in base["families"]])
        self.assertIn(code, [item["code"] for item in result["families"]])
        self.assertTrue(result["version"].endswith("+db"))

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
