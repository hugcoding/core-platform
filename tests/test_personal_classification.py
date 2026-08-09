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
            "sensitivity": "personal", "sensitivity_signals": ["employment"],
            "confidence": "high", "reason": "Recente brief.",
        }), 42, "brief.docx")
        self.assertEqual("classified", result["status"])
        self.assertTrue(result["needs_review"])
        self.assertEqual("Active/Work/motivation_letters/brief.docx", result["suggested_path"])

    def test_path_is_deterministic_and_model_path_is_ignored(self):
        value = {
            "file_id": 42, "document_type": "factuur", "category": "finance",
            "document_family": "facturen", "topics": [], "lifecycle": "archive_candidate",
            "suggested_path": "Active/Finance/factuur.pdf", "sensitivity": "sensitive",
            "sensitivity_signals": ["financial"], "confidence": "high", "reason": "Oud document.",
        }
        result = validate_classification(json.dumps(value), 42, "Factuur 2026.pdf")
        self.assertEqual("classified", result["status"])
        self.assertEqual("Archive/Finance/invoices/Factuur 2026.pdf", result["suggested_path"])

    def test_category_family_sensitivity_and_confidence_are_normalized(self):
        result = validate_classification(json.dumps({
            "file_id": 9, "document_type": "belastingaangifte", "category": "personal",
            "document_family": "inkomstenbelasting_aangiftes", "topics": ["inkomstenbelasting"],
            "lifecycle": "archive_candidate", "sensitivity": "personal",
            "sensitivity_signals": ["financial", "government_identifier"],
            "confidence": "high", "reason": "Aangifte met BSN en inkomen.",
        }), 9, "aangifte.pdf")
        self.assertEqual("finance", result["category"])
        self.assertEqual("income_tax", result["document_family"])
        self.assertEqual("highly_sensitive", result["sensitivity"])
        self.assertEqual("medium", result["confidence"])
        self.assertIn("category_normalized:personal->finance", result["normalization_warnings"])
        self.assertEqual("Archive/Finance/income_tax/aangifte.pdf", result["suggested_path"])

    def test_equivalent_vve_memos_share_family(self):
        base = {
            "file_id": 1, "document_type": "memo", "category": "home",
            "topics": ["riolering", "VvE"], "lifecycle": "active_candidate",
            "sensitivity": "normal", "sensitivity_signals": ["none"],
            "confidence": "high", "reason": "Technische memo.",
        }
        first = validate_classification(json.dumps({**base, "document_family": "vve_building_memo"}), 1, "memo.docx")
        second = validate_classification(json.dumps({**base, "document_family": "VvE_technical_memo"}), 1, "memo.pdf")
        self.assertEqual("vve_technical_memos", first["document_family"])
        self.assertEqual(first["document_family"], second["document_family"])

    def test_invalid_json_goes_to_review(self):
        self.assertEqual(
            "provider_response_not_valid_json",
            validate_classification("not-json", 1)["reason"],
        )

    def test_none_cannot_be_combined_with_sensitive_signal(self):
        result = validate_classification(json.dumps({
            "file_id": 7, "document_type": "brief", "category": "personal",
            "document_family": "letters", "topics": [], "lifecycle": "active_candidate",
            "sensitivity": "personal", "sensitivity_signals": ["none", "relationship"],
            "confidence": "medium", "reason": "Brief.",
        }), 7, "brief.docx")
        self.assertEqual("conflicting_sensitivity_signals", result["reason"])


if __name__ == "__main__":
    unittest.main()
