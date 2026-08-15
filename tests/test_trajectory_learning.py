import unittest

from core.organization.target_path import application_trajectory, propose_target
from core.organization.trajectory_learning import (
    build_trajectory_rules,
    matching_trajectory_rule,
    trajectory_from_target,
    trajectory_parts_from_target,
)


def review(file_id, filename, target, *, decision="accepted", source="uitzoeken"):
    return {
        "id": f"00000000-0000-0000-0000-{file_id:012d}",
        "file_id": file_id,
        "decision": decision,
        "proposed_target_path": target,
        "filename": filename,
        "path": f"/volume1/data/import/Documenten/CV & Sollicitaties/{source}/{filename}",
    }


class TrajectoryLearningTests(unittest.TestCase):
    def test_temporary_source_folder_is_not_a_trajectory(self):
        code, label = application_trajectory({
            "path": "/volume1/data/Documenten/CV & Sollicitaties/uitzoeken/test.pdf",
        })
        self.assertEqual("general_applications", code)
        self.assertEqual("Algemene sollicitaties", label)

    def test_three_consistent_sogetti_reviews_create_proposal_only_rule(self):
        rows = [review(i, f"Sollicitatie-Sogetti-{i}.pdf",
                       f"/volume1/data/Persoonlijk/Actief/Werk & Loopbaan/Sollicitaties/Sogetti/Sollicitatie-{i}.pdf")
                for i in range(1, 4)]
        rules = build_trajectory_rules(rows)
        self.assertEqual(1, len(rules))
        self.assertEqual("Sogetti", rules[0]["trajectory_label"])
        self.assertEqual(3, rules[0]["support"])
        self.assertEqual("high", rules[0]["confidence"])
        self.assertEqual("proposal_only", rules[0]["activation_status"])
        self.assertEqual(3, len(rules[0]["source_review_event_ids"]))

    def test_relevant_counterexample_blocks_rule(self):
        rows = [review(i, f"Sollicitatie-Sogetti-{i}.pdf",
                       f"/volume1/data/Persoonlijk/Actief/Werk & Loopbaan/Sollicitaties/Sogetti/{i}.pdf")
                for i in range(1, 4)]
        rows.append(review(4, "Sollicitatie-Sogetti-anders.pdf",
                           "/volume1/data/Persoonlijk/Actief/Werk & Loopbaan/Sollicitaties/Anders/4.pdf"))
        self.assertEqual([], build_trajectory_rules(rows))

    def test_one_rijnland_review_creates_medium_contextual_proposal(self):
        rows = [review(
            1,
            "Motivatiebrief-Rijnland.docx",
            "/volume1/data/Persoonlijk/Actief/Werk & Loopbaan/Sollicitaties/Rijnland/Motivatiebrief.docx",
        )]
        rules = build_trajectory_rules(rows, minimum_support=1)
        self.assertEqual(1, len(rules))
        self.assertEqual("Rijnland", rules[0]["trajectory_label"])
        self.assertEqual("medium", rules[0]["confidence"])
        self.assertIn("exact_context_term_from_accepted_human_target_path", rules[0]["reason_codes"])
        self.assertIsNotNone(matching_trajectory_rule({
            "filename": "CV Rijnland.pdf",
            "path": "/volume1/data/Documenten/CV & Sollicitaties/uitzoeken/CV Rijnland.pdf",
        }, rules))

    def test_one_review_without_matching_source_context_creates_no_rule(self):
        rows = [review(
            1,
            "Motivatiebrief.docx",
            "/volume1/data/Persoonlijk/Actief/Werk & Loopbaan/Sollicitaties/Rijnland/Motivatiebrief.docx",
        )]
        self.assertEqual([], build_trajectory_rules(rows, minimum_support=1))

    def test_one_duo_review_learns_rijksoverheid_duo_hierarchy(self):
        rows = [review(
            1,
            "Motivatie Data engineer DUO.pdf",
            "/volume1/data/Persoonlijk/Actief/Werk & Loopbaan/Sollicitaties/Rijksoverheid/DUO/Motivatie Data engineer DUO.pdf",
        )]
        rules = build_trajectory_rules(rows, minimum_support=1)
        self.assertEqual(["Rijksoverheid", "DUO"], rules[0]["trajectory_parts"])
        self.assertEqual("duo", rules[0]["match_term"])
        self.assertEqual("medium", rules[0]["confidence"])
        proposal = propose_target({
            "filename": "CV Data engineer DUO.docx", "extension": "docx",
            "path": "/volume1/data/Documenten/CV & Sollicitaties/uitzoeken/CV Data engineer DUO.docx",
            "accepted_category": "work_career", "accepted_document_family": "resumes",
            "accepted_lifecycle": "active", "accepted_trajectory_parts": rules[0]["trajectory_parts"],
        })
        self.assertIn("/Sollicitaties/Rijksoverheid/DUO/", proposal["suggested_target_path"])

    def test_hierarchical_trajectory_display_is_auditable(self):
        self.assertEqual(
            ["Rijksoverheid", "DUO"],
            trajectory_parts_from_target(
                "/volume1/data/Persoonlijk/Actief/Werk & Loopbaan/Sollicitaties/Rijksoverheid/DUO/test.pdf",
                "test.pdf",
            ),
        )

    def test_generic_family_layer_is_not_learned(self):
        self.assertIsNone(trajectory_from_target(
            "/volume1/data/Persoonlijk/Actief/Werk & Loopbaan/Sollicitaties/CV/test.pdf",
            "test.pdf",
        ))

    def test_match_requires_applications_context_and_rebuilds_target(self):
        rules = build_trajectory_rules([
            review(i, f"Sogetti-{i}.pdf",
                   f"/volume1/data/Persoonlijk/Actief/Werk & Loopbaan/Sollicitaties/Sogetti/{i}.pdf")
            for i in range(1, 4)
        ])
        self.assertIsNone(matching_trajectory_rule(
            {"filename": "Sogetti.pdf", "path": "/volume1/data/Facturen/Sogetti.pdf"}, rules,
        ))
        rule = matching_trajectory_rule({
            "filename": "Hugo_Data-Engineer-Sogetti.pdf",
            "path": "/volume1/data/Documenten/CV & Sollicitaties/uitzoeken/Hugo_Data-Engineer-Sogetti.pdf",
        }, rules)
        proposal = propose_target({
            "filename": "Hugo_Data-Engineer-Sogetti.pdf", "extension": "pdf",
            "path": "/volume1/data/Documenten/CV & Sollicitaties/uitzoeken/Hugo_Data-Engineer-Sogetti.pdf",
            "accepted_category": "work_career", "accepted_document_family": "resumes",
            "accepted_lifecycle": "active", "accepted_trajectory_label": rule["trajectory_label"],
        })
        self.assertIn("/Sollicitaties/Sogetti/", proposal["suggested_target_path"])
        self.assertNotIn("/uitzoeken/", proposal["suggested_target_path"])


if __name__ == "__main__":
    unittest.main()
