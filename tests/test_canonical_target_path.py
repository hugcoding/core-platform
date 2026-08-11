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


if __name__ == "__main__":
    unittest.main()
