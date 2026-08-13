from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class WorksetLlmMigrationTests(unittest.TestCase):
    def test_auditable_local_only_contract(self):
        sql = (ROOT / "database/migrations/20260814_add_workset_llm_assistant.sql").read_text("utf-8")
        self.assertIn("cardinality(selected_file_ids) BETWEEN 1 AND 5", sql)
        self.assertIn("local_provider boolean NOT NULL DEFAULT true", sql)
        self.assertIn("raw_text_stored boolean NOT NULL DEFAULT false", sql)
        self.assertIn("ai_proposal_id", sql)
        self.assertNotIn("UPDATE public.document_review_events", sql)
        rollback = (ROOT / "database/migrations/rollback/20260814_add_workset_llm_assistant.sql").read_text("utf-8")
        self.assertIn("DROP TABLE IF EXISTS public.workset_ai_runs", rollback)
        self.assertNotIn("DROP TABLE IF EXISTS public.document_review_events", rollback)


if __name__ == "__main__":
    unittest.main()
