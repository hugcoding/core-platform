import unittest
from pathlib import Path


class MetadataDockerfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.dockerfile = (root / "Dockerfile.metadata").read_text(encoding="utf-8")

    def test_worker_receives_shared_integrity_package(self):
        self.assertIn("COPY core/integrity ./core/integrity", self.dockerfile)

    def test_dockerfile_does_not_copy_missing_namespace_init(self):
        self.assertNotIn("COPY core/__init__.py", self.dockerfile)


if __name__ == "__main__":
    unittest.main()
