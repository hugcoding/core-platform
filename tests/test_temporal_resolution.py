import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "database/migrations/20260810_add_temporal_resolution_v1.sql"
ROLLBACK = ROOT / "database/migrations/rollback/20260810_add_temporal_resolution_v1.sql"


class TemporalResolutionMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")

    def test_resolution_is_auditable_and_keeps_evidence(self):
        self.assertIn("CREATE OR REPLACE VIEW public.v_file_temporal_resolution", self.sql)
        self.assertIn("evidence_ids", self.sql)
        self.assertIn("resolution_reason", self.sql)
        self.assertIn("'temporal-resolution-v1'", self.sql)
        self.assertNotIn("DELETE FROM public.file_date_evidence", self.sql)
        self.assertNotIn("UPDATE public.file_date_evidence", self.sql)

    def test_equivalent_instant_normalizes_pdf_info_to_utc(self):
        self.assertIn("pdf_info_timezone_status IN ('utc', 'explicit_offset')", self.sql)
        self.assertIn("pdf_info_value_at AT TIME ZONE 'UTC'", self.sql)
        self.assertIn(") <= 2", self.sql)
        self.assertIn("pdf_info_xmp_equivalent_instant", self.sql)

    def test_date_precision_and_material_conflict_are_explicit(self):
        self.assertIn("pdf_xmp_local_value::time = time '00:00:00'", self.sql)
        self.assertIn("pdf_info_xmp_equivalent_date_precision", self.sql)
        self.assertIn("materially_different_temporal_evidence", self.sql)
        self.assertIn("(resolution_status = 'material_conflict') AS material_conflict", self.sql)

    def test_temporal_profile_only_exposes_material_conflicts(self):
        self.assertIn("created_resolution.material_conflict", self.sql)
        self.assertIn("modified_resolution.material_conflict", self.sql)
        self.assertIn("CREATE OR REPLACE VIEW public.v_file_temporal_profile", self.sql)

    def test_rollback_restores_original_conflict_semantics(self):
        self.assertIn("count(DISTINCT COALESCE(value_at::text, local_value::text))", self.rollback)
        self.assertIn("DROP VIEW IF EXISTS public.v_file_temporal_resolution", self.rollback)
        self.assertNotIn("DROP TABLE", self.rollback)


if __name__ == "__main__":
    unittest.main()
