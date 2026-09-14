import unittest

from core.organization.similar_documents import (
    apply_similar_review_proposals,
    document_identity,
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

    def test_identity_matches_round_three_variants(self):
        pairs = (
            ("badkamer.docx", "badkamer.pdf"),
            ("ModOpdr1_vs2.3.docx", "ModOpdr1_vs2.5.pdf"),
            ("signed_documents_vanbruggen-gecomprimeerd.pdf", "signed_documents_vanbruggen.pdf"),
            ("tuin.docx", "tuin definitief.docx"),
        )
        for left, right in pairs:
            with self.subTest(left=left, right=right):
                self.assertEqual(normalized_document_identity(left), normalized_document_identity(right))

    def test_generic_names_are_not_clustered(self):
        self.assertEqual("", normalized_document_identity("document.pdf"))
        self.assertEqual("", normalized_document_identity("scan (1).pdf"))
        self.assertFalse(document_identity("brief.docx")["is_safe"])
        self.assertEqual("short:tuin", normalized_document_identity("tuin definitief.docx"))

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
        self.assertEqual(
            "aa4aee14-04f1-4e98-9df9-d91123302c83",
            proposal["documents"][0]["source_review_event_id"],
        )
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

    def test_source_review_remains_visible_with_many_unreviewed_peers(self):
        pending = [{
            "file_id": file_id, "filename": f"tuin copy {file_id}.pdf", "extension": "pdf",
            "latest_review_decision": None,
        } for file_id in range(2, 9)]
        # Parenthesized copy suffixes intentionally normalize to the reviewed source.
        for offset, item in enumerate(pending, 1):
            item["filename"] = f"tuin ({offset}).pdf"
        source = {
            "file_id": 1, "filename": "tuin.docx", "extension": "docx",
            "latest_review_id": "aa4aee14-04f1-4e98-9df9-d91123302c83",
            "latest_review_decision": "accepted", "latest_review_category": "housing",
            "latest_review_family": "home_improvement",
        }
        result = apply_similar_review_proposals(pending + [source])
        self.assertEqual(1, result[0]["similar_document_proposal"]["documents"][0]["file_id"])
        self.assertTrue(result[0]["similar_document_proposal"]["documents"][0]["human_reviewed"])


if __name__ == "__main__":
    unittest.main()
