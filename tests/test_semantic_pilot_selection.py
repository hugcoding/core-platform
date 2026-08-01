import unittest
from datetime import datetime, timezone

from core.semantic.pilot_selection import build_manifest, parse_timestamp, select_candidates


def row(file_id, path, **overrides):
    values = {
        "file_id": str(file_id),
        "path": path,
        "extension": "pdf",
        "size_bytes": "100",
        "content_sha256": f"hash-{file_id}",
        "modified_at_fs": "2026-07-01T12:00:00+00:00",
        "content_group_id": f"group-{file_id}",
        "golden_file_id": str(file_id),
    }
    values.update(overrides)
    return values


class SemanticPilotSelectionTests(unittest.TestCase):
    cutoff = datetime(2024, 8, 1, tzinfo=timezone.utc)

    def test_timestamp_parser_accepts_core_epoch_and_iso_formats(self):
        self.assertEqual(
            datetime(2025, 4, 1, 20, 37, 38, tzinfo=timezone.utc),
            parse_timestamp("1743539858"),
        )
        self.assertEqual(
            datetime(2025, 4, 1, 20, 37, 38, tzinfo=timezone.utc),
            parse_timestamp("2025-04-01T20:37:38Z"),
        )

    def test_epoch_timestamp_is_eligible_inside_recent_window(self):
        selected, excluded = select_candidates(
            [row(1, "/volume1/document.pdf", modified_at_fs="1743539858")],
            cutoff=self.cutoff,
            limit=1,
        )
        self.assertEqual([1], [int(item["file_id"]) for item in selected])
        self.assertEqual([], excluded)

    def test_selects_recent_non_sensitive_persisted_golden_once(self):
        rows = [
            row(1, "/volume1/data/import/cloud/onedrive/current/Document.pdf"),
            row(2, "/volume1/data/import/cloud/onedrive/current/Belasting/aanslag.pdf"),
            row(3, "/volume1/data/import/cloud/onedrive/current/old.pdf", modified_at_fs="2020-01-01T00:00:00Z"),
            row(4, "/volume1/data/import/cloud/onedrive/current/copy.pdf", content_group_id="group-1", golden_file_id="1"),
            row(5, "/volume1/data/import/cloud/onedrive/current/not-golden.pdf", golden_file_id="99"),
            row(6, "/volume1/data/import/cloud/onedrive/current/notes.txt", extension="txt"),
            row(7, "/volume1/data/import/cloud/onedrive/current/empty.pdf", size_bytes="0"),
        ]

        selected, excluded = select_candidates(rows, cutoff=self.cutoff, limit=50)

        self.assertEqual([1], [int(item["file_id"]) for item in selected])
        reasons = {int(item["file_id"]): item["selection_reason"] for item in excluded}
        self.assertTrue(reasons[2].startswith("sensitive_path_term:"))
        self.assertEqual("outside_recent_window", reasons[3])
        self.assertEqual("not_persisted_golden", reasons[4])
        self.assertEqual("not_persisted_golden", reasons[5])
        self.assertEqual("unsupported_extension", reasons[6])
        self.assertEqual("empty_file", reasons[7])

    def test_limit_is_deterministic_and_prefers_most_recent(self):
        rows = [
            row(1, "/volume1/a.pdf", modified_at_fs="2026-01-01T00:00:00Z"),
            row(2, "/volume1/b.pdf", modified_at_fs="2026-07-01T00:00:00Z"),
        ]
        selected, excluded = select_candidates(rows, cutoff=self.cutoff, limit=1)
        self.assertEqual([2], [int(item["file_id"]) for item in selected])
        self.assertEqual("pilot_limit", excluded[0]["selection_reason"])

    def test_manifest_disables_all_mutating_or_external_processing(self):
        selected, _ = select_candidates([row(1, "/volume1/document.docx")], cutoff=self.cutoff, limit=1)
        manifest = build_manifest(
            selected,
            source="/volume1/data/import/cloud/onedrive/current",
            cutoff=self.cutoff,
            generated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        self.assertFalse(manifest["embedding_enabled"])
        self.assertFalse(manifest["external_ai_enabled"])
        self.assertFalse(manifest["database_writes_enabled"])
        self.assertEqual("approved", manifest["files"][0]["approval"])
        self.assertNotIn("text", manifest["files"][0])


if __name__ == "__main__":
    unittest.main()
