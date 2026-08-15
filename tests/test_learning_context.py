import unittest

from core.organization.learning_context import (
    build_learning_context_rules,
    matching_learning_context_rule,
)


class LearningContextTests(unittest.TestCase):
    def test_accepted_course_review_proposes_same_exact_course_context(self):
        rows = [{
            "id": "00000000-0000-0000-0000-000000000001",
            "file_id": 1,
            "decision": "accepted",
            "corrected_category_code": "learning_development",
            "path": "/volume1/data/import/cloud/onedrive/current/Documenten/Introductie Python voor data science (NL)/notebooks/les1.pdf",
        }]
        rules = build_learning_context_rules(rows)
        self.assertEqual("medium", rules[0]["confidence"])
        match = matching_learning_context_rule({
            "path": "/volume1/data/import/cloud/onedrive/current/Documenten/Introductie Python voor data science (NL)/notebooks/les2.pdf",
        }, rules)
        self.assertEqual("course_material", match["family_code"])

    def test_counterexample_blocks_course_context(self):
        rows = [{
            "id": str(index), "file_id": index, "decision": "accepted",
            "corrected_category_code": category,
            "path": f"/volume1/data/import/cloud/onedrive/current/Documenten/Introductie Python/notebooks/{index}.pdf",
        } for index, category in ((1, "learning_development"), (2, "work_career"))]
        self.assertEqual([], build_learning_context_rules(rows))


if __name__ == "__main__":
    unittest.main()
