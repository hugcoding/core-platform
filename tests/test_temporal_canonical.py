import csv
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from core.metadata.temporal_canonical import assess_rows, parse_timestamp, summarize
from tools.runtime import temporal_canonical_impact


AS_OF = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)


def evidence(file_id, date_type, timestamp, *, evidence_id, source="pdf_info_dictionary",
             status="needs_review", conflict="true", confidence="medium"):
    return {
        "file_id": str(file_id), "content_group_id": f"group-{file_id}",
        "filename": f"document-{file_id}.pdf", "extension": "pdf",
        "path": f"/volume1/documents/document-{file_id}.pdf",
        "filesystem_modified_at": "2025-02-17T10:00:00+00:00",
        "v1_workset_status": status, "v1_reason_code": "conflicting_temporal_evidence",
        "created_has_conflict": conflict, "modified_has_conflict": conflict,
        "activity_window_months": "9", "policy_version": "policy-v1",
        "policy_checksum": "hash", "v1_created_at": "2025-02-17T10:00:00+00:00",
        "v1_created_evidence_id": "info-created",
        "v1_modified_at": "2025-02-17T10:00:00+00:00",
        "v1_modified_evidence_id": "info-modified",
        "evidence_id": evidence_id, "evidence_date_type": date_type,
        "evidence_source_type": source, "evidence_confidence": confidence,
        "evidence_value_at": timestamp if source != "pdf_xmp" else "",
        "evidence_local_value": timestamp.replace("+00:00", ""),
        "evidence_timezone_status": "absent" if source == "pdf_xmp" else "utc",
        "evidence_raw_value": timestamp,
    }


class TemporalCanonicalSelectionTests(unittest.TestCase):
    def test_precise_created_wins_over_date_only_on_same_calendar_day(self):
        rows = [
            evidence(
                10, "created", "2008-06-27T00:00:00+00:00",
                evidence_id="date-only", source="pdf_xmp", confidence="low",
                conflict="false", status="inactive",
            ),
            evidence(
                10, "created", "2008-06-27T19:21:12+00:00",
                evidence_id="precise", confidence="medium",
                conflict="false", status="inactive",
            ),
        ]
        rows[0]["evidence_value_at"] = ""
        rows[0]["evidence_local_value"] = "2008-06-27 00:00:00"
        rows[0]["evidence_timezone_status"] = "absent"
        rows[0]["v1_created_evidence_id"] = "precise"
        rows[1]["v1_created_evidence_id"] = "precise"
        result = assess_rows(rows, as_of=AS_OF)[0]
        self.assertEqual("precise", result["created_evidence_id"])
        self.assertEqual("timestamp_timezone_known", result["created_precision"])
        self.assertTrue(result["created_same_day_precision_preferred"])
        self.assertEqual(
            "earliest_credible_created_same_day_precision_preferred",
            result["created_selection_reason"],
        )
        self.assertFalse(result["created_changed"])

    def test_earlier_calendar_day_still_wins_for_created(self):
        rows = [
            evidence(
                11, "created", "2008-06-26T00:00:00+00:00",
                evidence_id="earlier-date-only", source="pdf_xmp", confidence="low",
                conflict="false", status="inactive",
            ),
            evidence(
                11, "created", "2008-06-27T19:21:12+00:00",
                evidence_id="later-precise", confidence="high",
                conflict="false", status="inactive",
            ),
        ]
        rows[0]["evidence_value_at"] = ""
        rows[0]["evidence_local_value"] = "2008-06-26 00:00:00"
        rows[0]["evidence_timezone_status"] = "absent"
        result = assess_rows(rows, as_of=AS_OF)[0]
        self.assertEqual("earlier-date-only", result["created_evidence_id"])
        self.assertFalse(result["created_same_day_precision_preferred"])

    def test_precise_modified_wins_over_date_only_on_same_calendar_day(self):
        rows = [
            evidence(
                12, "modified", "2020-08-13T00:00:00+00:00",
                evidence_id="date-only", source="pdf_xmp", confidence="low",
                conflict="false", status="inactive",
            ),
            evidence(
                12, "modified", "2020-08-13T10:08:56+00:00",
                evidence_id="precise", confidence="medium",
                conflict="false", status="inactive",
            ),
        ]
        rows[0]["evidence_value_at"] = ""
        rows[0]["evidence_local_value"] = "2020-08-13 00:00:00"
        rows[0]["evidence_timezone_status"] = "absent"
        result = assess_rows(rows, as_of=AS_OF)[0]
        self.assertEqual("precise", result["modified_evidence_id"])
        self.assertTrue(result["modified_same_day_precision_preferred"])

    def test_postgresql_short_utc_offset_and_epoch_are_python38_compatible(self):
        self.assertEqual(
            datetime(2026, 3, 2, 11, 7, 50, tzinfo=timezone.utc),
            parse_timestamp("2026-03-02 11:07:50+00"),
        )
        self.assertEqual(
            datetime(2025, 4, 1, 20, 37, 38, tzinfo=timezone.utc),
            parse_timestamp("1743539858"),
        )

    def test_same_evidence_is_not_changed_by_timezone_rendering(self):
        row = evidence(
            7, "created", "2025-02-17T10:00:00+00:00", evidence_id="same-created",
            conflict="false", status="inactive",
        )
        row["v1_created_evidence_id"] = "same-created"
        row["v1_created_at"] = "2025-02-17 10:00:00+00"
        result = assess_rows([row], as_of=AS_OF)[0]
        self.assertFalse(result["created_changed"])

    def test_postgresql_filesystem_timestamp_keeps_recent_document_active(self):
        row = evidence(
            8, "created", "2022-01-01T00:00:00+00:00", evidence_id="old-created",
            conflict="false", status="active",
        )
        row["filesystem_modified_at"] = "2026-03-02 11:07:50+00"
        result = assess_rows([row], as_of=AS_OF)[0]
        self.assertEqual("active", result["v2_workset_status"])
        self.assertEqual("2026-03-02T11:07:50+00:00", result["filesystem_modified_at"])

    def test_timezone_ambiguous_chronology_does_not_block_lifecycle(self):
        rows = [
            evidence(9, "created", "2022-12-03T13:49:12+00:00", evidence_id="created", conflict="false", status="inactive"),
            evidence(9, "modified", "2022-12-03T12:50:27+00:00", evidence_id="modified", conflict="false", status="inactive"),
        ]
        rows[0]["evidence_value_at"] = ""
        rows[0]["evidence_timezone_status"] = "absent"
        result = assess_rows(rows, as_of=AS_OF)[0]
        self.assertEqual("chronology_timezone_ambiguous", result["chronology_issue"])
        self.assertEqual("inactive", result["v2_workset_status"])

    def test_earliest_created_latest_modified_and_invariant_conflict(self):
        rows = [
            evidence(1, "created", "2025-02-17T10:00:00+00:00", evidence_id="info-created"),
            evidence(1, "created", "2018-06-14T08:05:39+00:00", evidence_id="xmp-created", source="pdf_xmp", confidence="low"),
            evidence(1, "modified", "2025-02-17T10:00:00+00:00", evidence_id="info-modified"),
            evidence(1, "modified", "2020-01-02T07:54:32+00:00", evidence_id="xmp-modified", source="pdf_xmp", confidence="low"),
        ]
        result = assess_rows(rows, as_of=AS_OF)[0]
        self.assertTrue(result["created_changed"])
        self.assertEqual("xmp-created", result["created_evidence_id"])
        self.assertEqual("info-modified", result["modified_evidence_id"])
        self.assertEqual("decision_invariant_temporal_conflict", result["lifecycle_conflict_effect"])
        self.assertEqual("inactive", result["v2_workset_status"])
        self.assertTrue(result["lifecycle_changed"])

    def test_conflict_across_cutoff_remains_review(self):
        rows = [
            evidence(2, "created", "2025-01-01T00:00:00+00:00", evidence_id="old"),
            evidence(2, "modified", "2026-07-01T00:00:00+00:00", evidence_id="new"),
        ]
        rows[0]["filesystem_modified_at"] = "2025-01-01T00:00:00+00:00"
        rows[1]["filesystem_modified_at"] = "2025-01-01T00:00:00+00:00"
        result = assess_rows(rows, as_of=AS_OF)[0]
        self.assertEqual("decision_sensitive_temporal_conflict", result["lifecycle_conflict_effect"])
        self.assertEqual("needs_review", result["v2_workset_status"])

    def test_future_and_placeholder_evidence_are_excluded(self):
        rows = [
            evidence(3, "created", "1900-01-01T00:00:00+00:00", evidence_id="placeholder"),
            evidence(3, "modified", "2030-01-01T00:00:00+00:00", evidence_id="future"),
        ]
        result = assess_rows(rows, as_of=AS_OF)[0]
        self.assertEqual(2, result["excluded_evidence_count"])
        self.assertIn("known_placeholder_timestamp", result["excluded_evidence"])
        self.assertIn("future_timestamp", result["excluded_evidence"])

    def test_created_after_modified_requires_review(self):
        rows = [
            evidence(6, "created", "2026-06-01T00:00:00+00:00", evidence_id="created"),
            evidence(6, "modified", "2025-06-01T00:00:00+00:00", evidence_id="modified", conflict="false", status="active"),
        ]
        rows[0]["created_has_conflict"] = "false"
        rows[0]["modified_has_conflict"] = "false"
        result = assess_rows(rows, as_of=AS_OF)[0]
        self.assertEqual("created_after_modified", result["chronology_issue"])
        self.assertEqual("needs_review", result["v2_workset_status"])
        self.assertEqual("created_after_modified", result["v2_lifecycle_reason"])

    def test_summary_counts_impact(self):
        result = assess_rows([
            evidence(4, "created", "2020-01-01T00:00:00+00:00", evidence_id="created"),
            evidence(4, "modified", "2025-01-01T00:00:00+00:00", evidence_id="modified"),
        ], as_of=AS_OF)
        self.assertEqual(1, summarize(result)["documents"])


class TemporalCanonicalRuntimeTests(unittest.TestCase):
    def test_cli_exposes_read_only_impact_command(self):
        root = Path(__file__).resolve().parents[1]
        cli = (root / "tools/runtime/core").read_text(encoding="utf-8")
        runtime = (root / "tools/runtime/temporal_canonical_impact.py").read_text(encoding="utf-8")
        self.assertIn("core metadata temporal-impact", cli)
        self.assertIn('sh ./tools/runtime/temporal-canonical-impact "$@"', cli)
        self.assertIn("v_active_document_workset", runtime)
        self.assertIn("file_date_evidence", runtime)
        self.assertNotIn("INSERT INTO", runtime)
        self.assertNotIn("UPDATE public.", runtime)
        self.assertNotIn("DELETE FROM", runtime)

    def test_runtime_writes_read_only_reports(self):
        source = evidence(5, "created", "2025-01-01T00:00:00+00:00", evidence_id="created")
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(source))
        writer.writeheader()
        writer.writerow(source)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(temporal_canonical_impact, "PROJECT_ROOT", root), mock.patch.object(
                temporal_canonical_impact, "run_query", return_value=output.getvalue()
            ), mock.patch.object(temporal_canonical_impact, "shutil_which", return_value="docker"):
                status = temporal_canonical_impact.main([
                    "--as-of", "2026-08-11T12:00:00Z", "--dry-run",
                ])
            export_dir = root / "project/exports/active-workset"
            payload = json.loads((export_dir / "temporal-canonical-impact-latest.json").read_text("utf-8"))
            report = (export_dir / "temporal-canonical-impact-latest.md").read_text("utf-8")
        self.assertEqual(0, status)
        self.assertEqual("read_only_dry_run", payload["mode"])
        self.assertEqual("temporal-canonical-impact-report-v3", payload["schema_version"])
        self.assertFalse(payload["safety"]["database_writes"])
        self.assertIn("filesystem_modified_at", payload["documents"][0])
        self.assertEqual("conflicting_temporal_evidence", payload["documents"][0]["v1_reason_code"])
        self.assertIn("Database writes: **false**", report)


if __name__ == "__main__":
    unittest.main()
