import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Scrum78DatabaseGrowthAssessmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = (
            ROOT / "database/assessment/scrum78_database_growth.sql"
        ).read_text(encoding="utf-8")
        cls.docs = (
            ROOT / "docs/project/scrum-78-database-growth-review.md"
        ).read_text(encoding="utf-8")

    def test_assessment_is_read_only(self):
        executable = "\n".join(
            line for line in self.sql.splitlines()
            if not line.lstrip().startswith("--")
        )
        for keyword in (
            "INSERT", "UPDATE", "DELETE", "TRUNCATE", "DROP", "ALTER",
            "CREATE", "VACUUM", "REINDEX",
        ):
            self.assertIsNone(
                re.search(rf"\b{keyword}\b", executable, flags=re.IGNORECASE),
                f"assessment must not contain {keyword}",
            )

    def test_assessment_covers_growth_drivers_and_derived_layers(self):
        for table in (
            "files", "metadata", "file_events", "semantic_embeddings_acc",
            "classification_proposals", "classification_reviews",
        ):
            self.assertIn(table, self.sql)
        self.assertIn("pg_total_relation_size", self.sql)
        self.assertIn("pg_relation_size", self.sql)
        self.assertIn("idx_scan", self.sql)

    def test_report_preserves_data_contract_boundaries(self):
        self.assertIn("Operationele waarheid", self.docs)
        self.assertIn("Menselijk besluit", self.docs)
        self.assertIn("geen extra kopietabel", self.docs)
        self.assertIn("metadata_file_id_unique", self.docs)
        self.assertIn("idx_metadata_file_id", self.docs)


if __name__ == "__main__":
    unittest.main()
