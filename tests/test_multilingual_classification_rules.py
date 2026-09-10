import unittest

from core.organization.classification_rules import RULESET_VERSION, classify_weighted
from core.organization.target_path import propose_target


class MultilingualClassificationRuleTests(unittest.TestCase):
    def assertProposal(self, filename, source_path, category, family):
        row = {
            "file_id": 1, "filename": filename, "extension": filename.rsplit(".", 1)[-1],
            "path": "/volume1/data/Persoonlijk/Inactief/Te beoordelen/" + filename,
            "source_context_path": source_path, "accepted_lifecycle": "archive",
        }
        result = propose_target(row)
        self.assertEqual(category, result["category_code"])
        self.assertEqual(family, result["document_family_code"])
        evidence = result["proposal_evidence"]
        self.assertEqual(RULESET_VERSION, evidence["classification_ruleset_version"])
        self.assertEqual("proposed", evidence["classification_status"])
        self.assertTrue(evidence["matched_classification_signals"])
        self.assertNotIn("/import/", result["suggested_target_path"])

    def test_anonymized_round_two_scenarios(self):
        cases = (
            ("Employment Agreement.pdf", "/import/Documenten/Work/HR/Employment Agreement.pdf", "work_career", "employment_documents"),
            ("Addendum Pension Scheme.pdf", "/import/Documenten/Payroll/Addendum Pension Scheme.pdf", "finance", "pension_documents"),
            ("Programmeren in Java.pdf", "/import/Documenten/Opleiding/NCOI/Programmeren in Java.pdf", "learning_development", "course_material"),
            ("Kadastrale kaart.pdf", "/import/Documenten/Woning/Kadaster/Kadastrale kaart.pdf", "home_living", "property_documents"),
            ("MJOP 2026.pdf", "/import/Documenten/Woning/VvE/MJOP 2026.pdf", "home_living", "vve_documents"),
            ("Offerte uitbouw.pdf", "/import/Documenten/Woning/Verbouwing/Offerte uitbouw.pdf", "home_living", "home_maintenance"),
            ("ModOpdr1_vs2.3.docx", "/import/Documenten/Opleiding/Programmeren/ModOpdr1_vs2.3.docx", "learning_development", "course_material"),
        )
        for case in cases:
            with self.subTest(filename=case[0]):
                self.assertProposal(*case)

    def test_weak_offer_without_home_context_abstains(self):
        result = classify_weighted({"filename": "Offerte.pdf", "path": "/volume1/data/Te beoordelen/Offerte.pdf"})
        self.assertEqual("abstained", result["status"])
        self.assertEqual("low", result["confidence"])

    def test_competing_domains_abstain_with_evidence(self):
        result = classify_weighted({
            "filename": "Employment Agreement.pdf",
            "source_context_path": "/import/Documenten/Woning/Kadastrale kaart/details.pdf",
        })
        self.assertEqual("conflict", result["status"])
        self.assertEqual("conflicting_weighted_signals", result["reason_code"])
        self.assertTrue(result["competing_candidates"])


if __name__ == "__main__":
    unittest.main()
