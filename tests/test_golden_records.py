import unittest

from tools.runtime.golden_records import build_manifest, candidate_score


def item(file_id, path, hash_content="hash", size="10"):
    return {
        "file_id": str(file_id),
        "path": path,
        "filename": path.rsplit("/", 1)[-1],
        "extension": "pdf",
        "size_bytes": size,
        "hash_content": hash_content,
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


if __name__ == "__main__":
    unittest.main()
