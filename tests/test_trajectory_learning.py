import unittest

from core.organization.target_path import application_trajectory, propose_target
from core.organization.trajectory_learning import (
    build_trajectory_rules,
    matching_trajectory_rule,
    trajectory_from_target,
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
        self.assertEqual("proposal_only", rules[0]["activation_status"])
        self.assertEqual(3, len(rules[0]["source_review_event_ids"]))

    def test_relevant_counterexample_blocks_rule(self):
        rows = [review(i, f"Sollicitatie-Sogetti-{i}.pdf",
                       f"/volume1/data/Persoonlijk/Actief/Werk & Loopbaan/Sollicitaties/Sogetti/{i}.pdf")
                for i in range(1, 4)]
        rows.append(review(4, "Sollicitatie-Sogetti-anders.pdf",
                           "/volume1/data/Persoonlijk/Actief/Werk & Loopbaan/Sollicitaties/Anders/4.pdf"))
        self.assertEqual([], build_trajectory_rules(rows))

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
