import unittest
from core.organization.learning_context import build_llm_learning_context
from core.organization.review_learning import analyze_reviews

class ReviewLearningTests(unittest.TestCase):
    def test_repeated_human_corrections_become_inactive_candidate(self):
        rows = [{"file_id": i, "decision": "accepted", "proposal_document_family_code": "general",
                 "corrected_category_code": "home_living", "corrected_document_family_code": "vve_documents",
                 "proposed_target_path": "/volume1/data/Persoonlijk/Actief/Wonen/VvE/file.pdf"} for i in (1, 2, 3)]
        candidates = analyze_reviews(rows, minimum_support=3)
        self.assertEqual("candidate_only", candidates[0]["activation_status"])
        self.assertEqual(3, candidates[0]["support"])
        context = build_llm_learning_context(candidates)
        self.assertEqual("advisory_only", context["usage"])
        self.assertFalse(context["rules_activated"])

    def test_sparse_or_rejected_reviews_do_not_create_candidate(self):
        rows = [{"file_id": 1, "decision": "accepted", "proposal_document_family_code": "general",
                 "corrected_category_code": "finance", "corrected_document_family_code": "invoices"},
                {"file_id": 2, "decision": "rejected", "proposal_document_family_code": "general",
                 "corrected_category_code": "finance", "corrected_document_family_code": "invoices"}]
        self.assertEqual([], analyze_reviews(rows, minimum_support=2))
