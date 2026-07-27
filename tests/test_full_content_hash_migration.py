import unittest
from pathlib import Path


class FullContentHashMigrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.sql = (
            root / "database" / "migrations" / "20260727_add_full_content_hash.sql"
        ).read_text(encoding="utf-8")

    def test_files_receive_full_hash_and_timestamp(self):
        self.assertIn("content_sha256 text", self.sql)
        self.assertIn("content_sha256_at timestamptz", self.sql)

    def test_active_full_hash_lookup_is_indexed(self):
        self.assertIn("files_content_sha256_size_active_idx", self.sql)
        self.assertIn("(content_sha256, size_bytes)", self.sql)

    def test_fast_hash_is_documented_as_non_authoritative(self):
        self.assertIn("identity signal only, not exact-duplicate proof", self.sql)


if __name__ == "__main__":
    unittest.main()
