import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class StagingPlacementReviewTests(unittest.TestCase):
    def test_migration_adds_append_only_review_type_and_bound_projection(self):
        sql = (ROOT / "database/migrations/20260923_add_staging_placement_reviews.sql").read_text()
        self.assertIn("'staging_placement'", sql)
        self.assertIn("v_latest_staging_placement_review", sql)
        self.assertIn("content_sha256", sql)
        self.assertIn("proposal_evidence ->> 'source_path'", sql)
        self.assertNotIn("UPDATE public.document_review_events", sql)
        self.assertNotIn("DELETE FROM public.document_review_events", sql)

    def test_queue_is_fail_closed_without_matching_explicit_review(self):
        source = (ROOT / "dashboard/app.py").read_text()
        self.assertIn('"blocked_reason": "classification_review_required"', source)
        self.assertIn('"target_path_basis": "explicit_staging_review"', source)
        self.assertIn('str(approval.get("content_sha256") or "")', source)
        self.assertIn('str(approval.get("source_path") or "")', source)
        self.assertIn('str(approval.get("proposal_lifecycle") or "")', source)
        self.assertIn('str(approval.get("proposal_target_path") or "")', source)

    def test_portal_exposes_distinct_action_without_classification_submission(self):
        script = (ROOT / "dashboard/static/workset.js").read_text()
        self.assertIn("Naar Te beoordelen plaatsen", script)
        self.assertIn("/api/v1/workset/staging-placement-reviews", script)
        self.assertIn("core:execution-queue-refresh", script)

    def test_endpoint_is_non_mutating_and_hash_bound(self):
        source = (ROOT / "dashboard/app.py").read_text()
        start = source.index('def create_staging_placement_review')
        end = source.index('@app.post("/api/v1/workset/reviews")', start)
        endpoint = source[start:end]
        self.assertIn("INSERT INTO public.document_review_events", endpoint)
        self.assertIn('"file_mutations": False', endpoint)
        self.assertNotIn("UPDATE public.files", endpoint)
        self.assertNotIn("DELETE FROM public.files", endpoint)


if __name__ == "__main__":
    unittest.main()
