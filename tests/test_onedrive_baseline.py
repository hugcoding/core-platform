import csv
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.runtime import onedrive_baseline
from datetime import datetime, timezone

from tools.runtime.onedrive_baseline import assess_group, build_activity, build_assessment, summary_metrics


SOURCE = "/volume1/data/import/cloud/onedrive/current"


def item(file_id, path, *, content_sha256="hash", size="100", group_id="group-1", golden_id="", modified_at_fs="1767225600"):
    return {
        "file_id": str(file_id),
        "path": path,
        "filename": path.rsplit("/", 1)[-1],
        "extension": "pdf",
        "size_bytes": size,
        "content_sha256": content_sha256,
        "mime_type": "application/pdf",
        "modified_at_fs": modified_at_fs,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-02T00:00:00+00:00",
        "is_baseline": str(path.startswith(SOURCE)).lower(),
        "content_group_id": group_id,
        "existing_golden_file_id": golden_id,
        "existing_group_confidence": "high" if group_id else "",
        "existing_selection_status": "golden_selected" if group_id else "",
    }


class OneDriveBaselineTests(unittest.TestCase):
    def test_activity_uses_filesystem_mtime_without_duplicate_comparison(self):
        rows = [
            item(1, f"{SOURCE}/recent.pdf", modified_at_fs="1767225600"),
            item(2, f"{SOURCE}/old.pdf", modified_at_fs="1577836800"),
            item(3, f"{SOURCE}/unknown.pdf", modified_at_fs=""),
        ]
        result = build_activity(rows, datetime(2026, 8, 1, tzinfo=timezone.utc), 2)
        self.assertEqual(
            ["active_candidate", "legacy_review_candidate", "needs_temporal_review"],
            [row["activity_status"] for row in result],
        )
        self.assertTrue(all(row["activity_basis_source"] == "filesystem_mtime" for row in result))
        self.assertTrue(all(row["execution_authorized"] == "false" for row in result))

    def test_baseline_only_content_is_retained(self):
        result = assess_group([item(1, f"{SOURCE}/document.pdf")])
        self.assertEqual("baseline_only", result["relationship"])
        self.assertEqual("retain_baseline", result["proposed_action"])
        self.assertEqual("0", result["maximum_reclaimable_bytes_upper_bound"])
        self.assertEqual("false", result["execution_authorized"])

    def test_historical_exact_copy_is_reviewed_and_space_is_upper_bound(self):
        result = assess_group(
            [
                item(1, f"{SOURCE}/document.pdf"),
                item(2, "/volume1/backup/Documents/document.pdf"),
            ]
        )
        self.assertEqual("exact_duplicate_historical", result["relationship"])
        self.assertEqual("review_historical_exact_duplicates", result["proposed_action"])
        self.assertEqual("100", result["historical_reclaimable_bytes_upper_bound"])
        self.assertEqual("100", result["maximum_reclaimable_bytes_upper_bound"])

    def test_duplicate_inside_baseline_is_not_authorized_for_deletion(self):
        result = assess_group(
            [
                item(1, f"{SOURCE}/A/document.pdf"),
                item(2, f"{SOURCE}/B/document.pdf"),
            ]
        )
        self.assertEqual("exact_duplicate_within_baseline", result["relationship"])
        self.assertEqual("review_onedrive_exact_duplicates", result["proposed_action"])
        self.assertEqual("100", result["baseline_internal_reclaimable_bytes_upper_bound"])
        self.assertEqual("true", result["baseline_protected"])

    def test_existing_golden_record_is_preserved_as_canonical_reference(self):
        result = assess_group(
            [
                item(1, f"{SOURCE}/document.pdf", golden_id="2"),
                item(2, "/volume1/data/Documents/document.pdf", golden_id="2"),
            ]
        )
        self.assertEqual("2", result["canonical_file_id"])
        self.assertEqual("existing_content_group", result["canonical_basis"])
        self.assertEqual("historical_nas", result["canonical_source_zone"])

    def test_missing_existing_golden_member_falls_back_deterministically(self):
        result = assess_group(
            [
                item(1, f"{SOURCE}/document.pdf", golden_id="99"),
                item(2, "/volume1/backup/Documents/document.pdf", golden_id="99"),
            ]
        )
        self.assertNotEqual("99", result["canonical_file_id"])
        self.assertEqual("deterministic_golden-v3", result["canonical_basis"])

    def test_exact_match_and_golden_confidence_are_separate_fields(self):
        result = assess_group([
            item(1, f"{SOURCE}/A/document.pdf"),
            item(2, f"{SOURCE}/B/document.pdf"),
        ])
        self.assertEqual("full_sha256_and_size", result["exact_match_basis"])
        self.assertEqual("stored_full_content_hash_evidence", result["content_integrity_status"])
        self.assertEqual("provenance_only", result["selection_quality_scope"])
        self.assertEqual(result["confidence"], result["golden_selection_confidence"])
        self.assertEqual("low", result["golden_comparison_confidence"])

    def test_missing_full_hash_is_blocked(self):
        result = assess_group(
            [item(1, f"{SOURCE}/document.pdf", content_sha256="", group_id="")]
        )
        self.assertEqual("blocked_missing_full_hash", result["proposed_action"])
        self.assertEqual("0", result["maximum_reclaimable_bytes_upper_bound"])
        self.assertEqual("low", result["confidence"])

    def test_empty_file_is_separate_from_missing_hash(self):
        result = assess_group([
            item(1, f"{SOURCE}/empty.txt", content_sha256="", size="0", group_id="")
        ])
        self.assertEqual("empty_file", result["relationship"])
        self.assertEqual("review_empty_file", result["proposed_action"])
        self.assertEqual("excluded_empty_file", result["selection_status"])

    def test_build_assessment_keeps_unhashed_files_separate(self):
        assessment = build_assessment(
            [
                item(1, f"{SOURCE}/A.pdf", content_sha256="", group_id=""),
                item(2, f"{SOURCE}/B.pdf", content_sha256="", group_id=""),
            ]
        )
        self.assertEqual(2, len(assessment))

    def test_summary_counts_physical_baseline_only_once(self):
        rows = [
            item(1, f"{SOURCE}/document.pdf"),
            item(2, "/volume1/backup/Documents/document.pdf"),
        ]
        assessment = build_assessment(rows)
        metrics = summary_metrics(rows, assessment)
        self.assertEqual(1, metrics["baseline_files"])
        self.assertEqual(100, metrics["baseline_bytes"])
        self.assertEqual(1, metrics["historical_duplicate_groups"])
        self.assertEqual(100, metrics["historical_reclaimable_bytes_upper_bound"])

    def test_main_writes_read_only_report_and_compact_review(self):
        rows = [
            item(1, f"{SOURCE}/document.pdf"),
            item(2, "/volume1/backup/Documents/document.pdf"),
        ]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            onedrive_baseline, "PROJECT_ROOT", Path(tmp)
        ), mock.patch.object(
            onedrive_baseline, "run_query", return_value=output.getvalue()
        ), mock.patch.object(
            onedrive_baseline, "shutil_which", return_value="docker"
        ):
            exit_code = onedrive_baseline.main(
                [
                    "--source", SOURCE,
                    "--baseline-at", "2026-08-01T12:38:51+02:00",
                    "--snapshot-ref", "snapshot-1",
                    "--dry-run",
                ]
            )
            export_dir = Path(tmp) / "project" / "exports" / "migration-inventory"
            report = (export_dir / "onedrive-baseline-latest.md").read_text(encoding="utf-8")
            reviews = list(export_dir.glob("onedrive-duplicate-review-*.csv"))
            activities = list(export_dir.glob("onedrive-activity-*.csv"))

        self.assertEqual(0, exit_code)
        self.assertEqual(1, len(reviews))
        self.assertEqual(1, len(activities))
        self.assertIn("Mode: **read-only dry-run**", report)
        self.assertIn("Protective snapshot: `snapshot-1`", report)
        self.assertIn("Historical NAS copies: **0.00 GiB**", report)

    def test_main_can_skip_exact_matching(self):
        rows = [item(1, f"{SOURCE}/document.pdf")]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            onedrive_baseline, "PROJECT_ROOT", Path(tmp)
        ), mock.patch.object(
            onedrive_baseline, "run_query", return_value=output.getvalue()
        ) as query, mock.patch.object(onedrive_baseline, "shutil_which", return_value="docker"):
            exit_code = onedrive_baseline.main([
                "--source", SOURCE, "--as-of", "2026-08-01", "--skip-exact-matching", "--dry-run"
            ])
            report = (Path(tmp) / "project/exports/migration-inventory/onedrive-baseline-latest.md").read_text()
        self.assertEqual(0, exit_code)
        self.assertEqual(1, query.call_count)
        self.assertIn("Performed: **no**", report)

    def test_main_rejects_broad_data_root(self):
        self.assertEqual(2, onedrive_baseline.main(["--source", "/volume1/data", "--dry-run"]))


if __name__ == "__main__":
    unittest.main()
