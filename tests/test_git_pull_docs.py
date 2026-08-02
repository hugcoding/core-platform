import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GitPullDocumentationTests(unittest.TestCase):
    def setUp(self):
        self.script = (ROOT / "tools/runtime/git-pull").read_text("utf-8")
        self.core = (ROOT / "tools/runtime/core").read_text("utf-8")

    def test_documentation_rebuild_is_not_automatic(self):
        self.assertIn("docs_mode=ask", self.script)
        self.assertIn("Permanente Wiki opnieuw bouwen? [j/N]", self.script)
        self.assertIn("if [ -t 0 ]", self.script)
        self.assertIn("Non-interactive pull: Wiki rebuild skipped", self.script)

    def test_explicit_rebuild_and_skip_options_are_supported(self):
        self.assertIn("--rebuild-docs)", self.script)
        self.assertIn("--skip-docs)", self.script)
        self.assertIn("Use only one of --rebuild-docs or --skip-docs.", self.script)

    def test_core_forwards_pull_options(self):
        pull_case = self.core.split("    git)", 1)[1].split("    version)", 1)[0]
        self.assertIn("shift 2", pull_case)
        self.assertIn('sh ./tools/runtime/git-pull "$@"', pull_case)

    def test_docs_are_only_built_after_affirmative_decision(self):
        decision = self.script.index('if [ "$rebuild_docs" = yes ]')
        build = self.script.index("compose build docs")
        self.assertGreater(build, decision)


if __name__ == "__main__":
    unittest.main()
