import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class DocumentWorksetPathReviewViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = (ROOT / "database" / "migrations" /
                   "20260821_add_document_workset_path_review_view.sql").read_text(encoding="utf-8")

    def test_view_exposes_effective_lifecycle_and_both_path_sources(self):
        self.assertIn("v_document_workset_path_review", self.sql)
        self.assertIn("effective_lifecycle", self.sql)
        self.assertIn("core_proposed_path", self.sql)
        self.assertIn("human_proposed_path", self.sql)
        self.assertIn("lifecycle_aligned_proposed_path", self.sql)

    def test_archive_maps_to_inactive_without_writing_files(self):
        self.assertIn("WHEN 'archive' THEN 'Inactief'", self.sql)
        self.assertIn("path_requires_lifecycle_correction", self.sql)
        self.assertNotIn("UPDATE public.files", self.sql)
        self.assertNotIn("DELETE FROM", self.sql)

    def test_view_uses_current_hash_and_latest_append_only_evidence(self):
        self.assertIn("f.content_sha256 = p.content_sha256", self.sql)
        self.assertIn("DISTINCT ON (file_id)", self.sql)
        self.assertIn("ORDER BY file_id, created_at DESC, id DESC", self.sql)

    def test_rollback_only_drops_projection(self):
        rollback = (ROOT / "database" / "migrations" / "rollback" /
                    "20260821_add_document_workset_path_review_view.sql").read_text(encoding="utf-8")
        self.assertIn("DROP VIEW IF EXISTS public.v_document_workset_path_review", rollback)


if __name__ == "__main__":
    unittest.main()
