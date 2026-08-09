import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.semantic.personal_classification import (
    approved_manifest, build_manifest, select_personal_candidates, selection_stratum,
    validate_classification,
)


def row(file_id, path, *, extension="docx", modified="2026-08-01T10:00:00+00:00",
        current="t", group=None, size=1000):
    return {
        "file_id": str(file_id), "golden_file_id": str(file_id),
        "content_group_id": group or f"group-{file_id}", "path": path,
        "filename": path.rsplit("/", 1)[-1], "extension": extension,
        "size_bytes": str(size), "content_sha256": "a" * 64,
        "modified_at_fs": modified, "semantic_metadata_current": current,
    }


class PersonalSelectionTests(unittest.TestCase):
    def test_path_is_only_selection_stratum(self):
        self.assertEqual("work", selection_stratum("/Documenten/CV & Sollicitaties/cv.docx"))
        self.assertEqual("home", selection_stratum("/Documenten/Administratie/VVE/memo.pdf"))
        self.assertEqual("personal", selection_stratum("/Documenten/los.docx"))

    def test_selection_is_recent_golden_and_not_limited_to_embedding_pilot(self):
        rows = [
            row(1, "/volume1/Documenten/CV/cv.docx"),
            row(2, "/volume1/Documenten/Studie/les.pdf", extension="pdf"),
            row(3, "/volume1/Documenten/oud.docx", modified="2020-01-01T00:00:00Z"),
            row(4, "/volume1/Documenten/stale.docx", current="f"),
        ]
        selected, excluded = select_personal_candidates(
            rows, cutoff=datetime(2024, 8, 1, tzinfo=timezone.utc), limit=25,
        )
        self.assertEqual({"1", "2", "4"}, {item["file_id"] for item in selected})
        self.assertEqual(
            {"outside_recent_window"},
            {item["selection_reason"] for item in excluded},
        )

    def test_manifest_is_explicitly_read_only(self):
        selected, _ = select_personal_candidates(
            [row(1, "/volume1/Documenten/brief.docx")],
            cutoff=datetime(2024, 8, 1, tzinfo=timezone.utc), limit=25,
        )
        manifest = build_manifest(
            selected, source="/volume1/Documenten",
            cutoff=datetime(2024, 8, 1, tzinfo=timezone.utc),
        )
        self.assertFalse(manifest["database_writes_enabled"])
        self.assertFalse(manifest["file_mutations_enabled"])
        self.assertFalse(manifest["external_ai_enabled"])
        self.assertEqual("pending_review", manifest["files"][0]["approval"])

    def test_manifest_requires_completed_review_and_unchanged_golden(self):
        selected, _ = select_personal_candidates(
            [row(1, "/volume1/Documenten/brief.docx")],
            cutoff=datetime(2024, 8, 1, tzinfo=timezone.utc), limit=25,
        )
        manifest = build_manifest(
            selected, source="/volume1/Documenten",
            cutoff=datetime(2024, 8, 1, tzinfo=timezone.utc),
        )
        with self.assertRaisesRegex(ValueError, "incomplete"):
            approved_manifest(manifest, selected)
        manifest["files"][0]["approval"] = "approved"
        approved = approved_manifest(manifest, selected)
        self.assertEqual([1], [item["file_id"] for item in approved["files"]])
        changed = [{**selected[0], "content_sha256": "b" * 64}]
        with self.assertRaisesRegex(ValueError, "content_sha256"):
            approved_manifest(manifest, changed)

    def test_excluded_manifest_item_is_not_classified(self):
        selected, _ = select_personal_candidates(
            [row(1, "/volume1/Documenten/a.docx"), row(2, "/volume1/Documenten/b.docx")],
            cutoff=datetime(2024, 8, 1, tzinfo=timezone.utc), limit=25,
        )
        manifest = build_manifest(
            selected, source="/volume1/Documenten",
            cutoff=datetime(2024, 8, 1, tzinfo=timezone.utc),
        )
        manifest["files"][0]["approval"] = "approved"
        manifest["files"][1]["approval"] = "excluded"
        approved = approved_manifest(manifest, selected)
        self.assertEqual(1, len(approved["files"]))

    def test_core_cli_exposes_personal_classification(self):
        cli = Path("tools/runtime/core").read_text(encoding="utf-8")
        self.assertIn("personal-classification)", cli)
        self.assertIn("semantic-personal-classification", cli)


class PersonalClassificationTests(unittest.TestCase):
    def test_valid_classification(self):
        result = validate_classification(json.dumps({
            "file_id": 42, "document_type": "motivatiebrief", "category": "work",
            "document_family": "sollicitatie", "topics": ["data engineering", "UWV"],
            "lifecycle": "active_candidate",
            "suggested_path": "Active/Work/Sollicitaties/UWV/brief.docx",
            "sensitivity": "personal", "confidence": "high", "reason": "Recente brief.",
        }), 42)
        self.assertEqual("classified", result["status"])
        self.assertTrue(result["needs_review"])

    def test_unsafe_or_wrong_lifecycle_path_goes_to_review(self):
        value = {
            "file_id": 42, "document_type": "factuur", "category": "finance",
            "document_family": "facturen", "topics": [], "lifecycle": "archive_candidate",
            "suggested_path": "Active/Finance/factuur.pdf", "sensitivity": "sensitive",
            "confidence": "high", "reason": "Oud document.",
        }
        result = validate_classification(json.dumps(value), 42)
        self.assertEqual("needs_review", result["status"])
        self.assertEqual("invalid_suggested_path", result["reason"])

    def test_invalid_json_goes_to_review(self):
        self.assertEqual(
            "provider_response_not_valid_json",
            validate_classification("not-json", 1)["reason"],
        )


if __name__ == "__main__":
    unittest.main()
