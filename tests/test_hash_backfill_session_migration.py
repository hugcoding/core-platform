import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HashBackfillSessionMigrationTests(unittest.TestCase):
    def test_forward_migration_allows_hash_backfill(self):
        sql = (ROOT / "database/migrations/20260801_add_hash_backfill_scan_type.sql").read_text(encoding="utf-8")
        self.assertIn("'hash_backfill'", sql)
        self.assertIn("DROP CONSTRAINT IF EXISTS scan_sessions_type_check", sql)

    def test_rollback_preserves_existing_session_history(self):
        sql = (ROOT / "database/migrations/rollback/20260801_add_hash_backfill_scan_type.sql").read_text(encoding="utf-8")
        self.assertNotIn("DELETE FROM public.scan_sessions", sql)
        self.assertIn("rollback blocked: hash_backfill session history exists", sql)


if __name__ == "__main__":
    unittest.main()
