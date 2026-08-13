import unittest
from core.organization.learning_context import build_llm_learning_context
from core.organization.review_learning import audit_review_paths, analyze_privacy_reviews, analyze_proposal_quality, analyze_reviews

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

    def test_privacy_candidate_reports_agreement_and_counterexamples(self):
        rows = [
            {"file_id": file_id, "review_type": "privacy_classification", "decision": "accepted",
             "proposal_reason_code": "personal_or_financial_signal", "privacy_evidence": ["existing:personal"],
             "proposal_privacy_classification": "medium", "corrected_privacy_classification": judgment,
             "filename": f"document-{file_id}.pdf"}
            for file_id, judgment in ((1, "medium"), (2, "medium"), (3, "medium"), (4, "high"))
        ]
        candidate = analyze_privacy_reviews(rows, minimum_support=3)[0]
        self.assertEqual("medium", candidate["target_privacy_classification"])
        self.assertEqual(4, candidate["support"])
        self.assertEqual(0.75, candidate["agreement"])
        self.assertEqual(1, candidate["counterexample_count"])
        self.assertEqual(4, candidate["counterexamples"][0]["file_id"])
        self.assertEqual("candidate_only", candidate["activation_status"])
        self.assertFalse(candidate["may_lower_high_automatically"])

    def test_only_latest_privacy_judgment_per_file_counts(self):
        rows = [
            {"file_id": 1, "review_type": "privacy_classification", "decision": "accepted",
             "proposal_reason_code": "signal", "privacy_evidence": "{passport}",
             "proposal_privacy_classification": "high", "corrected_privacy_classification": "medium"},
            {"file_id": 1, "review_type": "privacy_classification", "decision": "accepted",
             "proposal_reason_code": "signal", "privacy_evidence": "{passport}",
             "proposal_privacy_classification": "high", "corrected_privacy_classification": "high"},
            {"file_id": 2, "review_type": "privacy_classification", "decision": "accepted",
             "proposal_reason_code": "signal", "privacy_evidence": "{passport}",
             "proposal_privacy_classification": "high", "corrected_privacy_classification": "high"},
        ]
        candidate = analyze_privacy_reviews(rows, minimum_support=2)[0]
        self.assertEqual(2, candidate["support"])
        self.assertEqual(1.0, candidate["agreement"])

    def test_proposal_quality_checks_category_family_and_path(self):
        rows = [
            {"file_id": 1, "review_type": "target_path", "decision": "accepted",
             "proposal_category_code": "work", "corrected_category_code": "work",
             "proposal_document_family_code": "general", "corrected_document_family_code": "cv",
             "proposal_target_path": "/data/Algemeen/a.pdf", "proposed_target_path": "/data/CV/a.pdf",
             "filename": "a.pdf"},
            {"file_id": 2, "review_type": "target_path", "decision": "accepted",
             "proposal_category_code": "work", "corrected_category_code": "work",
             "proposal_document_family_code": "cv", "corrected_document_family_code": "cv",
             "proposal_target_path": "/data/CV/b.pdf", "proposed_target_path": "",
             "filename": "b.pdf"},
            {"file_id": 3, "review_type": "target_path", "decision": "rejected",
             "proposal_category_code": "work", "proposal_document_family_code": "general",
             "proposal_target_path": "/data/Algemeen/c.pdf", "filename": "c.pdf"},
        ]
        by_dimension = {item["dimension"]: item for item in analyze_proposal_quality(rows)}
        self.assertEqual(2, by_dimension["category"]["accepted_unchanged"])
        self.assertEqual(1, by_dimension["category"]["rejected"])
        self.assertEqual(1, by_dimension["document_family"]["accepted_corrected"])
        self.assertEqual(1, by_dimension["target_path"]["accepted_corrected"])
        self.assertEqual(2, by_dimension["target_path"]["counterexample_count"])

    def test_core_and_human_paths_are_audited_for_structure_and_fit(self):
        rows = [{
            "file_id": 1, "review_type": "target_path", "decision": "accepted",
            "filename": "cv.pdf", "proposal_category_code": "work_career",
            "corrected_category_code": "work_career", "proposal_document_family_code": "general",
            "corrected_document_family_code": "resumes",
            "proposal_target_path": "/volume1/data/Persoonlijk/Actief/Werk & Loopbaan/Algemeen/cv.pdf",
            "proposed_target_path": "/volume1/data/Persoonlijk/Actief/Werk & Loopbaan/Sollicitaties/cv.pdf",
        }]
        audits = {item["source_type"]: item for item in audit_review_paths(rows)}
        self.assertEqual("needs_review", audits["core_proposal"]["status"])
        self.assertIn("generic_path_layer_present", audits["core_proposal"]["reason_codes"])
        self.assertEqual("pass", audits["human_proposal"]["status"])
        self.assertIn("family_layer_omitted", audits["human_proposal"]["reason_codes"])

    def test_human_path_outside_managed_root_is_invalid(self):
        rows = [{"file_id": 2, "review_type": "target_path", "filename": "x.pdf",
                 "proposal_category_code": "finance", "proposal_document_family_code": "tax_documents",
                 "proposed_target_path": "/tmp/x.pdf"}]
        audit = audit_review_paths(rows)[0]
        self.assertEqual("invalid", audit["status"])
