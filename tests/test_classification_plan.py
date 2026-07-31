import unittest

from tools.runtime.classification_plan import build_plan, review_decision


def row(**overrides):
    value = {
        "content_group_id": "group-1", "content_sha256": "abcdef123456",
        "golden_file_id": "1", "filename": "report.pdf",
        "golden_path": "/volume1/backup/NITRO/D/data/hugo/Documents/Studie/report.pdf",
        "extraction_status": "ready_for_local_extraction", "extraction_result": "extracted",
        "content_category": "documenten/studie", "category_confidence": "high",
        "temporal_inconsistencies": "[]",
    }
    value.update(overrides)
    return value


class ClassificationPlanTests(unittest.TestCase):
    def test_high_confidence_document_is_review_ready_but_not_authorized(self):
        planned = build_plan([row()], "/volume1/data")[0]
        self.assertEqual("review_ready", planned["review_status"])
        self.assertEqual("documents/study", planned["target_bucket"])
        self.assertEqual("/volume1/data/documents/study/Studie/report.pdf", planned["reviewed_target_path"])
        self.assertEqual("false", planned["execution_authorized"])

    def test_ocr_and_conversion_are_separate_blocks(self):
        self.assertEqual("blocked_ocr", review_decision(row(extraction_result="needs_ocr"))[0])
        self.assertEqual("blocked_conversion", review_decision(row(extraction_status="conversion_required", extraction_result="skipped"))[0])

    def test_medium_confidence_requires_manual_category_review(self):
        self.assertEqual(("manual_category_review", "confidence_medium", "documents/study"), review_decision(row(category_confidence="medium")))

    def test_temporal_conflict_blocks_otherwise_ready_document(self):
        self.assertEqual("manual_temporal_review", review_decision(row(temporal_inconsistencies='["created_after_modified"]'))[0])

    def test_sensitive_document_needs_explicit_policy_approval(self):
        decision = review_decision(row(content_category="gevoelig/gezondheid"))
        self.assertEqual(("blocked_sensitive_policy", "sensitive_requires_explicit_approval", "sensitive/health"), decision)

    def test_different_content_at_same_target_gets_hash_suffix(self):
        planned = build_plan([row(), row(content_group_id="group-2", content_sha256="123456789abc")], "/volume1/data")
        self.assertEqual({"resolved_hash_suffix"}, {item["collision_status"] for item in planned})
        self.assertEqual(2, len({item["reviewed_target_path"] for item in planned}))


if __name__ == "__main__":
    unittest.main()
