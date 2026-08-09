import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Scrum78LegacyAiRetirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.migration = (
            ROOT / "database/migrations/20260809_remove_legacy_ai_tables.sql"
        ).read_text(encoding="utf-8")
        cls.rollback = (
            ROOT / "database/migrations/rollback/20260809_remove_legacy_ai_tables.sql"
        ).read_text(encoding="utf-8")
        cls.schema = (ROOT / "database/schema/schema.sql").read_text(encoding="utf-8")
        cls.root_schema = (ROOT / "schema.sql").read_text(encoding="utf-8")
        cls.assessment = (ROOT / "tools/runtime/legacy-assessment").read_text(
            encoding="utf-8"
        )
        cls.duplicates = (ROOT / "tools/runtime/legacy-duplicates").read_text(
            encoding="utf-8"
        )
        cls.verify = (
            ROOT / "database/assessment/scrum78_verify_legacy_ai_retirement.sql"
        ).read_text(encoding="utf-8")

    def test_migration_refuses_to_drop_nonempty_legacy_tables(self):
        self.assertIn("Cannot retire public.embeddings", self.migration)
        self.assertIn("Cannot retire public.ai_output", self.migration)
        self.assertLess(
            self.migration.index("Cannot retire public.embeddings"),
            self.migration.index("DROP TABLE IF EXISTS public.embeddings"),
        )

    def test_migration_refactors_procedure_before_dropping_tables(self):
        replace_position = self.migration.index(
            "CREATE OR REPLACE PROCEDURE public.cleanup_all_execute()"
        )
        drop_position = self.migration.index("DROP TABLE IF EXISTS public.embeddings")
        self.assertLess(replace_position, drop_position)
        current_procedure = self.migration[replace_position:drop_position]
        self.assertNotIn("FROM embeddings", current_procedure)
        self.assertNotIn("FROM ai_output", current_procedure)
        self.assertNotIn("DELETE FROM embeddings", current_procedure)
        self.assertNotIn("DELETE FROM ai_output", current_procedure)

    def test_rollback_restores_tables_and_cleanup_contract(self):
        self.assertIn("CREATE TABLE public.embeddings", self.rollback)
        self.assertIn("CREATE TABLE public.ai_output", self.rollback)
        self.assertIn("public.vector(1536)", self.rollback)
        self.assertIn("created_at timestamptz DEFAULT now()", self.rollback)
        self.assertIn("CREATE OR REPLACE PROCEDURE public.cleanup_all_execute()", self.rollback)

    def test_current_schema_snapshots_do_not_recreate_legacy_tables(self):
        for schema in (self.schema, self.root_schema):
            self.assertNotIn("CREATE TABLE public.embeddings", schema)
            self.assertNotIn("CREATE TABLE public.ai_output", schema)
            self.assertNotIn("DELETE FROM embeddings", schema)
            self.assertNotIn("DELETE FROM ai_output", schema)

    def test_legacy_tools_keep_compatible_zero_metrics_without_table_reads(self):
        for script in (self.assessment, self.duplicates):
            self.assertNotIn("FROM embeddings", script)
            self.assertNotIn("JOIN embeddings", script)
            self.assertNotIn("FROM ai_output", script)
            self.assertNotIn("JOIN ai_output", script)
        self.assertIn("'embeddings_total', '0'", self.assessment)
        self.assertIn("'ai_output_total', '0'", self.assessment)
        self.assertIn("embeddings_count=0", self.duplicates)
        self.assertIn("ai_output_count=0", self.duplicates)

    def test_verification_checks_retirement_and_current_contracts(self):
        self.assertIn("to_regclass('public.' || relation_name)", self.verify)
        self.assertIn("has_legacy_reference", self.verify)
        self.assertIn("semantic_embeddings_acc", self.verify)
        self.assertIn("classification_proposals", self.verify)


if __name__ == "__main__":
    unittest.main()
