import unittest

from core.organization.target_path import (
    CATEGORY_LABELS, contract_checksum, mark_collisions, propose_target,
    safe_component, select_representative,
)


class CanonicalTargetPathTests(unittest.TestCase):
    def test_accepted_technical_code_gets_dutch_path(self):
        result = propose_target({"file_id": 1, "filename": "brief.docx",
                                 "accepted_category": "work",
                                 "accepted_document_family": "Sollicitaties"})
        self.assertEqual("work_career", result["category_code"])
        self.assertEqual("Werk & Loopbaan", result["category_label"])
        self.assertEqual("/volume1/data/Persoonlijk/Actief/Werk & Loopbaan/Sollicitaties/brief.docx",
                         result["suggested_target_path"])
        self.assertEqual(["generic_trajectory_omitted", "generic_family_omitted"],
                         result["path_reduction_reason_codes"])
        self.assertFalse(result["file_mutations"])

    def test_administration_is_never_a_top_level_category(self):
        result = propose_target({"file_id": 2, "filename": "onbekend.pdf",
                                 "accepted_category": "administration"})
        self.assertEqual("needs_review", result["category_code"])
        self.assertEqual("/volume1/data/Persoonlijk/Te beoordelen/onbekend.pdf",
                         result["suggested_target_path"])
        self.assertNotIn("Administratie", CATEGORY_LABELS.values())

    def test_rules_are_deterministic_and_conservative(self):
        first = propose_target({"file_id": 3, "filename": "Motivatie sollicitatie.docx", "path": "/x"})
        second = propose_target({"file_id": 3, "filename": "Motivatie sollicitatie.docx", "path": "/x"})
        self.assertEqual(first["suggested_target_path"], second["suggested_target_path"])
        self.assertEqual("deterministic_keyword_rule", first["proposal_reason_code"])
        self.assertEqual(contract_checksum(), first["contract_checksum"])

    def test_smb_safe_component(self):
        self.assertEqual("_CON.docx", safe_component("CON.docx"))
        self.assertEqual("a_b_.pdf", safe_component('a<b>?.pdf'))
        self.assertLessEqual(len(safe_component("x" * 200 + ".pdf")), 120)

    def test_representative_selection_round_robins_extensions(self):
        rows = [{"file_id": i, "extension": ext, "path": f"/{i}",
                 "last_qualifying_activity_at": f"2026-08-{min(i, 28):02d}"}
                for i, ext in enumerate((["pdf"] * 20 + ["docx"] * 20 + ["xlsx"] * 20), 1)]
        selected = select_representative(rows, 50)
        self.assertEqual(50, len(selected))
        self.assertEqual({"pdf", "docx", "xlsx"}, {r["extension"] for r in selected})

    def test_collisions_are_reported_not_resolved_by_mutation(self):
        rows = [propose_target({"file_id": i, "filename": "zelfde.pdf"}) for i in (1, 2)]
        marked = mark_collisions(rows)
        self.assertTrue(all(r["collision_status"] == "batch_target_collision" for r in marked))

    def test_application_context_and_family_prevent_filename_collision(self):
        first = propose_target({
            "file_id": 10, "filename": "vacaturetekst.docx", "extension": "docx",
            "path": "/volume1/data/import/Documenten/CV & Sollicitaties/UWV/ETL Engineer/vacaturetekst.docx",
        })
        second = propose_target({
            "file_id": 11, "filename": "vacaturetekst.docx", "extension": "docx",
            "path": "/volume1/data/import/Documenten/CV & Sollicitaties/rijksoverheid/DUO/vacaturetekst.docx",
        })
        marked = mark_collisions([first, second])
        self.assertIn("/Sollicitaties/UWV – ETL Engineer/", first["suggested_target_path"])
        self.assertIn("/Sollicitaties/rijksoverheid – DUO/", second["suggested_target_path"])
        self.assertNotIn("/Vacatures/", first["suggested_target_path"])
        self.assertIn("family_retained_as_metadata_within_trajectory", first["path_reduction_reason_codes"])
        self.assertTrue(all(row["collision_status"] == "none" for row in marked))

    def test_literal_algemeen_source_folder_does_not_become_target_layer(self):
        result = propose_target({
            "file_id": 15, "filename": "HoogendoornHugo_CV.pdf", "extension": "pdf",
            "path": "/volume1/data/import/Documenten/CV & Sollicitaties/algemeen/HoogendoornHugo_CV.pdf",
        })
        self.assertEqual(
            "/volume1/data/Persoonlijk/Actief/Werk & Loopbaan/Sollicitaties/CV/HoogendoornHugo_CV.pdf",
            result["suggested_target_path"],
        )
        self.assertIn("generic_trajectory_omitted", result["path_reduction_reason_codes"])

    def test_cv_token_before_extension_is_detected_as_resume(self):
        result = propose_target({
            "file_id": 16, "filename": "HoogendoornHugo_CV.pdf", "extension": "pdf",
            "path": "/volume1/data/import/Documenten/CV & Sollicitaties/algemeen/HoogendoornHugo_CV.pdf",
        })
        self.assertEqual("resumes", result["document_family_code"])
        self.assertEqual("CV", result["folder_label"])
        self.assertEqual(
            "/volume1/data/Persoonlijk/Actief/Werk & Loopbaan/Sollicitaties/CV/HoogendoornHugo_CV.pdf",
            result["suggested_target_path"],
        )

    def test_cv_substring_inside_word_is_not_a_resume(self):
        result = propose_target({"file_id": 17, "filename": "documentcvwaarde.pdf", "extension": "pdf"})
        self.assertEqual("general", result["document_family_code"])

    def test_secret_candidate_precedes_normal_category_rules(self):
        result = propose_target({"file_id": 12, "filename": "wachtwoorden.xlsx", "extension": "xlsx"})
        self.assertEqual("quarantine", result["zone_code"])
        self.assertEqual("secret_candidate_requires_restricted_review", result["proposal_reason_code"])
        self.assertEqual("/volume1/data/Persoonlijk/Quarantaine/Geheimen/wachtwoorden.xlsx",
                         result["suggested_target_path"])

    def test_course_dataset_is_not_promoted_to_active_workset_path(self):
        result = propose_target({
            "file_id": 13, "filename": "knmi_stn.xlsx", "extension": "xlsx",
            "path": "/volume1/data/Documenten/cursus/notebooks/data/knmi/knmi_stn.xlsx",
        })
        self.assertEqual("needs_review", result["zone_code"])
        self.assertEqual("learning_development", result["category_code"])
        self.assertEqual("supporting_dataset_requires_review", result["proposal_reason_code"])
        self.assertIn("/Te beoordelen/Leren & Ontwikkelen/Cursusmateriaal/", result["suggested_target_path"])

    def test_python_notebook_course_gets_learning_proposal(self):
        result = propose_target({
            "file_id": 18,
            "filename": "Introductie Python voor data science.pdf",
            "extension": "pdf",
            "path": "/volume1/data/import/cloud/onedrive/current/Documenten/Introductie Python voor data science (NL)/notebooks/Introductie Python voor data science.pdf",
        })
        self.assertEqual("learning_development", result["category_code"])
        self.assertEqual("course_material", result["document_family_code"])
        self.assertEqual("medium", result["proposal_confidence"])
        self.assertIn("/Leren & Ontwikkelen/Cursusmateriaal/", result["suggested_target_path"])

    def test_accepted_review_family_code_gets_canonical_dutch_label(self):
        result = propose_target({
            "file_id": 14, "filename": "Een integere Belastingdienst.pdf", "extension": "pdf",
            "path": "/volume1/data/Documenten/CV & Sollicitaties/rijksoverheid/toeslagen/Een integere Belastingdienst.pdf",
            "accepted_document_family": "interview_preparation",
        })
        self.assertEqual("interview_preparation", result["document_family_code"])
        self.assertEqual("Gespreksvoorbereiding", result["folder_label"])
        self.assertNotIn("/Gespreksvoorbereiding/", result["suggested_target_path"])
        self.assertIn("family_retained_as_metadata_within_trajectory", result["path_reduction_reason_codes"])


if __name__ == "__main__":
    unittest.main()
