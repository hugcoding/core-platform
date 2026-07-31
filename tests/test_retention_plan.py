import unittest
from datetime import datetime, timezone

from tools.runtime.retention_plan import build_plan, document_role, retention_basis

AS_OF = datetime(2026, 7, 31, tzinfo=timezone.utc)


def row(**overrides):
    value = {
        "content_group_id": "group-1", "content_sha256": "hash", "golden_file_id": "1",
        "filename": "reader.pdf", "golden_path": "/volume1/backup/NITRO/D/data/hugo/Documents/Studie/reader.pdf",
        "content_category": "documenten/studie", "category_confidence": "high",
        "category_reasons": "score=20", "extraction_result": "extracted",
        "filesystem_mtime": "2018-01-01T00:00:00+00:00",
        "embedded_created_at": "2017-01-01T00:00:00+00:00",
        "embedded_modified_at": "2018-01-01T00:00:00+00:00", "temporal_inconsistencies": "[]",
    }
    value.update(overrides)
    return value


class RetentionPlanTests(unittest.TestCase):
    def test_study_handout_is_separate_from_study_domain(self):
        self.assertEqual(("study_handout", "high", "handout_keyword"), document_role(row()))

    def test_undistinguished_study_document_needs_role_review(self):
        role = document_role(row(filename="document.pdf", golden_path="/volume1/Documents/Studie/document.pdf"))
        self.assertEqual(("study_reference", "medium", "study_role_not_distinguished"), role)

    def test_certificate_is_permanent(self):
        planned = build_plan([row(filename="diploma.pdf")], AS_OF)[0]
        self.assertEqual("study_certificate", planned["document_role"])
        self.assertEqual("permanent", planned["proposed_lifecycle_state"])

    def test_old_handout_is_sent_to_review_not_deleted(self):
        planned = build_plan([row()], AS_OF)[0]
        self.assertEqual("retention_review", planned["proposed_lifecycle_state"])
        self.assertEqual("review_snapshot_or_delete", planned["disposition_after_retention"])
        self.assertEqual("false", planned["execution_authorized"])

    def test_recent_handout_remains_active(self):
        planned = build_plan([row(embedded_modified_at="2026-01-01T00:00:00+00:00")], AS_OF)[0]
        self.assertEqual("active", planned["proposed_lifecycle_state"])

    def test_embedded_modified_date_has_priority(self):
        basis, source, confidence = retention_basis(row())
        self.assertEqual("2018-01-01T00:00:00+00:00", basis.isoformat())
        self.assertEqual(("embedded_modified_at", "high"), (source, confidence))

    def test_temporal_conflict_blocks_basis_date(self):
        self.assertEqual((None, "", "blocked_temporal_inconsistency"), retention_basis(row(temporal_inconsistencies='["created_after_modified"]')))

    def test_unknown_category_has_no_automatic_action(self):
        planned = build_plan([row(content_category="documenten/uitzoeken")], AS_OF)[0]
        self.assertEqual("unknown", planned["document_role"])
        self.assertEqual("retention_review", planned["proposed_lifecycle_state"])
        self.assertEqual("manual_classification", planned["disposition_after_retention"])

    def test_decision_id_is_deterministic_for_same_assessment(self):
        self.assertEqual(build_plan([row()], AS_OF)[0]["proposed_decision_id"], build_plan([row()], AS_OF)[0]["proposed_decision_id"])


if __name__ == "__main__":
    unittest.main()
