import unittest

from core.organization.similar_documents import (
    apply_similar_review_proposals,
    normalized_document_identity,
)


class SimilarDocumentProposalTests(unittest.TestCase):
    def test_identity_matches_docx_pdf_and_language_variant(self):
        self.assertEqual(
            normalized_document_identity("Motivatiebrief DUO.docx"),
            normalized_document_identity("Motivatiebrief DUO.pdf"),
        )
        self.assertEqual(
            normalized_document_identity("Diploma HBO.pdf"),
            normalized_document_identity("Diploma HBO - EN.pdf"),
        )

    def test_accepted_human_review_becomes_advisory_consensus(self):
        items = [{
            "file_id": 1, "filename": "Motivatiebrief DUO.docx", "extension": "docx",
            "latest_review_id": "aa4aee14-04f1-4e98-9df9-d91123302c83",
            "latest_review_decision": "accepted", "latest_review_category": "work_career",
            "latest_review_family": "motivation_letters",
        }, {
            "file_id": 2, "filename": "Motivatiebrief DUO.pdf", "extension": "pdf",
            "latest_review_decision": None,
        }]
        result = apply_similar_review_proposals(items)
        proposal = result[1]["similar_document_proposal"]
        self.assertEqual("consensus_proposal", proposal["status"])
        self.assertEqual("work_career", proposal["proposed_category_code"])
        self.assertEqual("motivation_letters", proposal["proposed_document_family_code"])
        self.assertEqual([1], proposal["related_file_ids"])
        self.assertNotIn("privacy_classification", proposal)

    def test_conflicting_human_reviews_are_not_reused(self):
        items = [{
            "file_id": 1, "filename": "Diploma.pdf", "extension": "pdf",
            "latest_review_id": "aa4aee14-04f1-4e98-9df9-d91123302c83",
            "latest_review_decision": "accepted", "latest_review_category": "health",
            "latest_review_family": "medical_documents",
        }, {
            "file_id": 2, "filename": "Diploma.docx", "extension": "docx",
            "latest_review_id": "0c3d5b7e-92dd-4d35-980c-700ff4bc9ca0",
            "latest_review_decision": "accepted", "latest_review_category": "learning_development",
            "latest_review_family": "certificates",
        }, {
            "file_id": 3, "filename": "Diploma - EN.pdf", "extension": "pdf",
            "latest_review_decision": None,
        }]
        proposal = apply_similar_review_proposals(items)[2]["similar_document_proposal"]
        self.assertEqual("conflicting_reviews_require_review", proposal["status"])
        self.assertNotIn("proposed_category_code", proposal)


if __name__ == "__main__":
    unittest.main()
