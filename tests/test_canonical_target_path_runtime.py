from pathlib import Path
import unittest


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


if __name__ == "__main__":
    unittest.main()
