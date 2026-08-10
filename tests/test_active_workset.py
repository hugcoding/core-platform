import csv
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from core.workset.active_workset import (
    evaluate_rows, select_review, subtract_months, summary, validate_policy,
)
from tools.runtime import active_workset


SOURCE = "/volume1/data/import/cloud/onedrive/current/Documenten"


def policy(**review):
    return {
        "schema_version": "active-workset-policy-v1",
        "policy_version": "test-v1",
        "source": SOURCE,
        "extensions": ["docx", "xlsx"],
        "activity_window_months": 9,
        "review_selection": {
            "active_per_extension": review.get("active_per_extension", 20),
            "outside_near_cutoff": review.get("outside_near_cutoff", 10),
            "duplicate_groups": review.get("duplicate_groups", 5),
            "temporal_conflicts": review.get("temporal_conflicts", 20),
        },
    }


def row(file_id, filename, modified, *, extension="docx", group="group-1",
        golden_id=1, golden_path=None, content_hash="sha", size="100", **temporal):
    return {
        "source_file_id": str(file_id),
        "source_path": f"{SOURCE}/{filename}",
        "filename": filename,
        "extension": extension,
        "size_bytes": size,
        "content_sha256": content_hash,
        "modified_at_fs": modified,
        "core_created_at": "2026-08-01T10:00:00+00:00",
        "content_group_id": group,
        "golden_file_id": str(golden_id) if golden_id else "",
        "golden_path": golden_path or f"{SOURCE}/{filename}",
        **temporal,
    }


class ActiveWorksetPolicyTests(unittest.TestCase):
    def setUp(self):
        self.as_of = datetime(2026, 8, 10, 12, tzinfo=timezone.utc)

    def test_policy_is_scoped_to_docx_xlsx_and_nine_months(self):
        result = validate_policy(policy())
        self.assertEqual(["docx", "xlsx"], result["extensions"])
        self.assertEqual(9, result["activity_window_months"])
        with self.assertRaisesRegex(ValueError, "exactly docx and xlsx"):
            validate_policy({**policy(), "extensions": ["pdf"]})

    def test_calendar_month_cutoff_is_deterministic(self):
        self.assertEqual(datetime(2025, 11, 10, 12, tzinfo=timezone.utc), subtract_months(self.as_of, 9))

    def test_recent_mtime_is_low_confidence_active_candidate(self):
        result = evaluate_rows([row(1, "recent.docx", "2026-07-01T00:00:00Z")],
                               policy=policy(), as_of=self.as_of)[0]
        self.assertEqual("active_candidate", result["workset_status"])
        self.assertEqual("filesystem_mtime_within_configured_window", result["reason"])
        self.assertEqual("low", result["confidence"])
        self.assertTrue(result["within_activity_window"])
        self.assertEqual("2026-08-01T10:00:00+00:00", result["core_first_observed_at"])
        self.assertIn("source_created_at", result["missing_evidence"])

    def test_temporal_profile_can_supply_activity_with_its_confidence(self):
        result = evaluate_rows([row(
            1, "temporal.docx", "2025-01-01T00:00:00Z",
            temporal_source_modified_at="2026-06-01T00:00:00Z",
            modified_confidence="medium", modified_source_type="office_core_properties",
            evidence_count="2", created_has_conflict="f", modified_has_conflict="f",
        )], policy=policy(), as_of=self.as_of)[0]
        self.assertEqual("active_candidate", result["workset_status"])
        self.assertEqual("source_metadata_modified_within_configured_window", result["reason"])
        self.assertEqual("medium", result["confidence"])
        self.assertEqual("source_metadata_modified", result["activity_basis_source"])
        self.assertEqual(2, result["temporal_evidence_count"])

    def test_temporal_conflict_forces_review_even_with_recent_signal(self):
        result = evaluate_rows([row(
            1, "conflict.docx", "2026-07-01T00:00:00Z",
            temporal_source_created_at="2026-05-01T00:00:00Z",
            created_confidence="medium", created_has_conflict="true",
        )], policy=policy(), as_of=self.as_of)[0]
        self.assertEqual("needs_review", result["workset_status"])
        self.assertEqual("conflicting_temporal_evidence", result["reason"])
        review = select_review([result], policy(temporal_conflicts=1))
        self.assertEqual("temporal_conflict", review[0]["review_reason"])

    def test_old_mtime_uses_configured_window_reason(self):
        result = evaluate_rows([row(1, "old.xlsx", "2025-10-01T00:00:00Z", extension="xlsx")],
                               policy=policy(), as_of=self.as_of)[0]
        self.assertEqual("inactive", result["workset_status"])
        self.assertEqual("no_qualifying_activity_within_configured_window", result["reason"])
        self.assertFalse(result["within_activity_window"])

    def test_group_uses_latest_source_signal_and_persisted_golden(self):
        result = evaluate_rows([
            row(10, "old-copy.docx", "2025-01-01T00:00:00Z", golden_id=99,
                golden_path="/volume1/archive/golden.docx"),
            row(11, "recent-copy.docx", "2026-07-01T00:00:00Z", golden_id=99,
                golden_path="/volume1/archive/golden.docx"),
        ], policy=policy(), as_of=self.as_of)
        self.assertEqual(1, len(result))
        self.assertEqual(11, result[0]["source_file_id"])
        self.assertEqual(99, result[0]["golden_file_id"])
        self.assertEqual(99, result[0]["candidate_file_id"])
        self.assertEqual("/volume1/archive/golden.docx", result[0]["golden_path"])
        self.assertEqual(2, result[0]["source_copy_count"])
        self.assertTrue(result[0]["duplicate_represented_by_golden"])

    def test_missing_golden_or_timestamp_needs_review(self):
        results = evaluate_rows([
            row(1, "ungrouped.docx", "2026-01-01T00:00:00Z", group="", golden_id=0),
            row(2, "unknown.xlsx", "", extension="xlsx", group="group-2", golden_id=2),
        ], policy=policy(), as_of=self.as_of)
        self.assertEqual({"missing_persisted_golden_record", "invalid_or_missing_activity_timestamp"},
                         {item["reason"] for item in results})

    def test_compact_review_is_limited_and_deduplicated(self):
        rows = evaluate_rows([
            row(1, "active-a.docx", "2026-07-01T00:00:00Z", golden_id=99),
            row(2, "active-b.docx", "2026-06-01T00:00:00Z", group="group-2", golden_id=2),
            row(3, "active.xlsx", "2026-06-01T00:00:00Z", extension="xlsx", group="group-3", golden_id=3),
            row(4, "outside.docx", "2025-10-01T00:00:00Z", group="group-4", golden_id=4),
        ], policy=policy(), as_of=self.as_of)
        review_policy = policy(active_per_extension=1, outside_near_cutoff=1, duplicate_groups=1)
        review = select_review(rows, review_policy)
        self.assertEqual(3, len(review))
        self.assertIn("duplicate_group", next(item for item in review if item["source_file_id"] == 1)["review_reason"])
        self.assertEqual(1, summary(rows)["inactive"])

    def test_runtime_query_projects_temporal_profile_only_onto_active_golden(self):
        self.assertIn("LEFT JOIN v_file_temporal_profile tp ON tp.file_id = gf.id", active_workset.QUERY)
        self.assertIn("gf.id AS golden_file_id", active_workset.QUERY)
        self.assertIn("gf.deleted_at IS NULL", active_workset.QUERY)

    def test_older_v1_policy_defaults_temporal_review_limit(self):
        legacy = policy()
        del legacy["review_selection"]["temporal_conflicts"]
        self.assertEqual(20, validate_policy(legacy)["review_selection"]["temporal_conflicts"])


class ActiveWorksetRuntimeTests(unittest.TestCase):
    def test_core_cli_exposes_workset_pilot(self):
        cli = (Path(__file__).resolve().parents[1] / "tools/runtime/core").read_text(encoding="utf-8")
        self.assertIn("core workset pilot", cli)
        self.assertIn('sh ./tools/runtime/active-workset "$@"', cli)

    def test_main_writes_read_only_csv_json_markdown_and_review(self):
        rows = [
            row(1, "recent.docx", "2026-07-01T00:00:00Z"),
            row(2, "old.xlsx", "2025-01-01T00:00:00Z", extension="xlsx", group="group-2", golden_id=2),
        ]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = root / "policy.json"
            policy_path.write_text(json.dumps(policy()), encoding="utf-8")
            with mock.patch.object(active_workset, "PROJECT_ROOT", root), mock.patch.object(
                active_workset, "run_query", return_value=output.getvalue()
            ), mock.patch.object(active_workset, "shutil_which", return_value="docker"):
                result = active_workset.main([
                    "--policy", str(policy_path), "--as-of", "2026-08-10T12:00:00Z", "--dry-run",
                ])
            export_dir = root / "project/exports/active-workset"
            report = (export_dir / "active-workset-v1-latest.md").read_text(encoding="utf-8")
            payload = json.loads((export_dir / "active-workset-v1-latest.json").read_text(encoding="utf-8"))
            reviews = list(export_dir.glob("active-workset-v1-review-*.csv"))
        self.assertEqual(0, result)
        self.assertIn("Mode: **read-only dry-run**", report)
        self.assertEqual("read_only_dry_run", payload["mode"])
        self.assertFalse(payload["safety"]["database_writes"])
        self.assertEqual(2, payload["summary"]["content_groups"])
        self.assertEqual(1, len(reviews))


if __name__ == "__main__":
    unittest.main()
