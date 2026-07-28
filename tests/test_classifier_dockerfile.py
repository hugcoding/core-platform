import unittest
from pathlib import Path


class ClassifierDockerfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.dockerfile = (root / "Dockerfile.classifier").read_text(encoding="utf-8")

    def test_app_root_is_available_for_namespace_imports(self):
        self.assertIn("ENV PYTHONPATH=/app", self.dockerfile)
        self.assertIn("COPY core/exports ./core/exports", self.dockerfile)


if __name__ == "__main__":
    unittest.main()
