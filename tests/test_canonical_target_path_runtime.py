from pathlib import Path
import unittest

from core.organization.target_path import mark_collisions, propose_target
from tools.runtime.canonical_target_path import FIELDS


ROOT = Path(__file__).resolve().parents[1]


class CanonicalTargetPathRuntimeTests(unittest.TestCase):
    def test_runtime_is_active_golden_read_only_projection(self):
        source = (ROOT / "tools/runtime/canonical_target_path.py").read_text(encoding="utf-8")
        self.assertIn("v_active_document_workset", source)
        self.assertIn("v_current_file_classification", source)
        self.assertIn("w.workset_status = 'active'", source)
        self.assertIn('run_query(command, QUERY, "")', source)
        for mutation in ("INSERT INTO", "UPDATE public", "DELETE FROM", "shutil.move", "os.rename"):
            self.assertNotIn(mutation, source)

    def test_cli_routes_command(self):
        source = (ROOT / "tools/runtime/core").read_text(encoding="utf-8")
        self.assertIn("target-path-pilot", source)
        self.assertIn("canonical-target-path", source)

    def test_csv_fields_cover_complete_evaluated_row(self):
        query_row = {
            "file_id": "1", "content_group_id": "group", "path": "/source/a.pdf",
            "filename": "a.pdf", "extension": "pdf", "size_bytes": "10",
            "content_sha256": "abc", "last_qualifying_activity_at": "2026-08-11T10:00:00Z",
            "activity_basis_source": "source_metadata_modified", "activity_confidence": "medium",
            "workset_status": "active", "accepted_category": "work",
            "accepted_document_family": "Sollicitaties", "accepted_lifecycle": "active_candidate",
        }
        evaluated = mark_collisions([propose_target(query_row)])[0]
        self.assertEqual(set(), set(evaluated) - set(FIELDS))


if __name__ == "__main__":
    unittest.main()
