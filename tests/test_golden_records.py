import unittest

from core.integrity.golden_record import rank_candidates
from tools.runtime.golden_records import build_manifest, candidate_score


def item(file_id, path, content_sha256="hash", size="10"):
    return {
        "file_id": str(file_id),
        "path": path,
        "filename": path.rsplit("/", 1)[-1],
        "extension": "pdf",
        "size_bytes": size,
        "content_sha256": content_sha256,
        "mime_type": "application/pdf",
        "created_at": "2026-01-01+00",
        "updated_at": "2026-01-02+00",
    }


class GoldenRecordsTest(unittest.TestCase):
    def test_clean_source_wins_over_cloudstation_copy(self):
        manifest = build_manifest(
            [
                item(1, "/volume1/source/CloudStation/Studie/rapport.pdf"),
                item(2, "/volume1/source/Studie/rapport.pdf"),
            ]
        )
        self.assertEqual("2", manifest[0]["golden_file_id"])
        self.assertEqual("high", manifest[0]["confidence"])

    def test_equal_scores_choose_one_deterministic_golden_record(self):
        manifest = build_manifest(
            [
                item(1, "/volume1/source/A/rapport.pdf"),
                item(2, "/volume1/source/B/rapport.pdf"),
            ]
        )
        self.assertEqual("golden_selected_tiebreak", manifest[0]["selection_status"])
        self.assertEqual("low", manifest[0]["confidence"])
        self.assertEqual("1", manifest[0]["golden_file_id"])

    def test_copy_like_filename_is_penalized(self):
        original = candidate_score(item(1, "/volume1/source/rapport.pdf"))[0]
        copy = candidate_score(item(2, "/volume1/source/rapport kopie.pdf"))[0]
        self.assertGreater(original, copy)

    def test_target_classification_is_explicitly_pending(self):
        manifest = build_manifest([item(1, "/volume1/source/rapport.pdf")])
        self.assertEqual("", manifest[0]["proposed_target_path"])
        self.assertEqual(
            "pending_content_classification",
            manifest[0]["target_classification_status"],
        )

    def test_empty_file_is_ineligible_for_golden_selection(self):
        with self.assertRaisesRegex(ValueError, "Empty files"):
            rank_candidates([item(1, "/volume1/source/empty.txt", size="0")])

    def test_core_observation_timestamps_do_not_influence_provenance_score(self):
        with_timestamps = item(1, "/volume1/source/rapport.pdf")
        without_timestamps = {**with_timestamps, "created_at": "", "updated_at": ""}
        self.assertEqual(candidate_score(with_timestamps), candidate_score(without_timestamps))

    def test_manifest_separates_exact_evidence_from_selection_confidence(self):
        result = build_manifest([
            item(1, "/volume1/source/A/rapport.pdf"),
            item(2, "/volume1/source/B/rapport.pdf"),
        ])[0]
        self.assertEqual("full_sha256_and_size", result["exact_match_basis"])
        self.assertEqual("stored_full_content_hash_evidence", result["content_integrity_status"])
        self.assertEqual("provenance_only", result["selection_quality_scope"])
        self.assertEqual(result["confidence"], result["golden_selection_confidence"])
        self.assertEqual(result["golden_score"], result["provenance_quality_score"])

    def test_algorithm_upgrade_reports_changed_existing_golden_for_review(self):
        first = item(1, "/volume1/source/CloudStation/rapport.pdf")
        second = item(2, "/volume1/source/rapport.pdf")
        rows = [
            {**first, "existing_golden_file_id": "1", "existing_algorithm_version": "golden-v2"},
            {**second, "existing_golden_file_id": "1", "existing_algorithm_version": "golden-v2"},
        ]
        result = build_manifest(rows)[0]
        self.assertEqual("2", result["golden_file_id"])
        self.assertEqual("1", result["existing_golden_file_id"])
        self.assertEqual("golden-v2", result["existing_algorithm_version"])
        self.assertEqual("golden_change_review", result["selection_change"])

    def test_persisted_golden_outside_source_is_not_reported_as_a_change(self):
        row = {
            **item(1, "/volume1/source/rapport.pdf"),
            "existing_golden_file_id": "99",
            "existing_algorithm_version": "golden-v2",
        }
        result = build_manifest([row])[0]
        self.assertEqual("persisted_golden_outside_assessment_scope", result["selection_change"])


if __name__ == "__main__":
    unittest.main()
