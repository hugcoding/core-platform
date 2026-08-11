import unittest

from core.organization.review_taxonomy import contextual_options, taxonomy


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


if __name__ == "__main__":
    unittest.main()
