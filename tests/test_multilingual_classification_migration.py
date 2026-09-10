from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class MultilingualClassificationMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = (ROOT / "database/migrations/20260909_add_multilingual_classification_rules_v2.sql").read_text("utf-8")

    def test_migration_exposes_read_only_python_sql_companion(self):
        self.assertIn("core_workset_family_v2", self.sql)
        self.assertIn("v_workset_classification_rules_v2", self.sql)
        self.assertIn("v_workset_source_context", self.sql)
        self.assertIn("rules_v2_family", self.sql)
        self.assertIn("rules_v2_category", self.sql)
        self.assertNotIn("UPDATE public", self.sql)
        self.assertNotIn("DELETE FROM", self.sql)

    def test_requested_multilingual_terms_are_versioned_in_sql(self):
        for term in (
            "employment agreement", "secondment agreement", "compensation letter",
            "pension scheme", "payroll", "kadastrale kaart", "mjop",
            "programmeren", "java", "modopdr", "badkamer", "elektra", "uitbouw",
        ):
            self.assertIn(term, self.sql.casefold())

    def test_ambiguous_domains_abstain_to_general(self):
        self.assertIn("work_hit::int + home_hit::int + finance_hit::int + learning_hit::int", self.sql)
        self.assertIn("THEN 'general'", self.sql)

    def test_rollback_is_scoped(self):
        rollback = (ROOT / "database/migrations/rollback/20260909_add_multilingual_classification_rules_v2.sql").read_text("utf-8")
        self.assertIn("DROP VIEW IF EXISTS public.v_workset_classification_rules_v2", rollback)
        self.assertIn("DROP FUNCTION IF EXISTS public.core_workset_family_v2", rollback)
        self.assertNotIn("DROP TABLE", rollback)


if __name__ == "__main__":
    unittest.main()
