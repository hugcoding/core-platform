import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class EffectiveWorksetReviewProjectionTests(unittest.TestCase):
    def test_migration_builds_one_read_only_effective_projection(self):
        sql = (ROOT / "database/migrations/20260907_add_effective_workset_review_projection.sql").read_text("utf-8")
        self.assertIn("CREATE OR REPLACE VIEW public.v_effective_document_workset", sql)
        self.assertIn("effective_workset_status", sql)
        self.assertIn("review_family", sql)
        self.assertIn("review_state", sql)
        self.assertNotIn("CREATE MATERIALIZED VIEW", sql)
        self.assertNotIn("INSERT INTO", sql)

    def test_projection_includes_lifecycle_and_quarantine_semantics(self):
        sql = (ROOT / "database/migrations/20260907_add_effective_workset_review_projection.sql").read_text("utf-8")
        self.assertIn("l.lifecycle_active_until <= now()", sql)
        self.assertIn("location_kind = 'deletion_quarantine'", sql)
        self.assertIn("similarity_review_event_id IS NOT NULL", sql)
        self.assertIn("public.core_workset_family", sql)
        self.assertIn("public.core_normalized_document_identity", sql)
        self.assertIn("identity_consensus", sql)

    def test_round_three_identity_migration_is_safe_and_versioned(self):
        sql = (ROOT / "database/migrations/20260914_add_similar_document_identity_v2.sql").read_text("utf-8")
        rollback = (ROOT / "database/migrations/rollback/20260914_add_similar_document_identity_v2.sql").read_text("utf-8")
        self.assertIn("similar-document-review-v2", sql)
        self.assertIn("gecomprimeerd", sql)
        self.assertIn("definitief", sql)
        self.assertIn("versie|version|vs?|rev", sql)
        self.assertIn("ARRAY['bestand', 'brief', 'document'", sql)
        self.assertNotIn("UPDATE ", sql.upper())
        self.assertIn("similar-document-review-v1", rollback)

    def test_dashboard_refines_database_family_bucket_with_visible_proposal(self):
        source = (ROOT / "dashboard/app.py").read_text("utf-8")
        self.assertIn("FROM public.v_effective_document_workset w", source)
        self.assertIn('item["review_family"]', source)
        self.assertIn('item["effective_review_family"]', source)
        self.assertIn('item.get("effective_review_family") or "general"', source)

    def test_rollback_removes_only_new_projection_objects(self):
        sql = (ROOT / "database/migrations/rollback/20260907_add_effective_workset_review_projection.sql").read_text("utf-8")
        self.assertIn("DROP VIEW IF EXISTS public.v_effective_document_workset", sql)
        self.assertIn("DROP FUNCTION IF EXISTS public.core_workset_family", sql)


if __name__ == "__main__":
    unittest.main()
