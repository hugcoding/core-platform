import subprocess
import unittest
from unittest.mock import patch

from tools.runtime.migration_inventory import DETAIL_QUERY, parse_csv, run_query, sql_literal


class MigrationInventoryTest(unittest.TestCase):
    def test_manifest_is_grouped_by_exact_content_key(self):
        self.assertIn("GROUP BY content_key", DETAIL_QUERY)
        self.assertIn("sf.hash_content || ':' || COALESCE(sf.size_bytes::text, 'NULL')", DETAIL_QUERY)
        self.assertIn("ARRAY_TO_JSON(ARRAY_AGG(path ORDER BY path))", DETAIL_QUERY)
        self.assertIn("'already_in_target'", DETAIL_QUERY)
        self.assertIn("all_content_stats AS", DETAIL_QUERY)
        self.assertNotIn("SELECT COUNT(*) FROM files all_files", DETAIL_QUERY)

    def test_backup_wrapper_is_not_a_blanket_exclusion(self):
        self.assertNotIn("backup_or_archive", DETAIL_QUERY)
        self.assertIn("'personal_document_candidate'", DETAIL_QUERY)

    def test_run_query_renders_safely_quoted_source(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="file_id,path\n1,/volume1/source/file.txt\n",
            stderr="",
        )
        with patch("tools.runtime.migration_inventory.subprocess.run", return_value=completed) as runner:
            output = run_query(
                ["docker", "exec", "postgres", "psql"],
                "SELECT :'source', :'source_prefix'",
                "/volume1/source",
            )

        command = runner.call_args.args[0]
        self.assertNotIn("source=/volume1/source", command)
        self.assertEqual("SELECT '/volume1/source', '/volume1/source/%'", command[-1])
        self.assertEqual("/volume1/source/file.txt", parse_csv(output)[0]["path"])

    def test_sql_literal_escapes_quote(self):
        self.assertEqual("'/volume1/Hugo''s files'", sql_literal("/volume1/Hugo's files"))


if __name__ == "__main__":
    unittest.main()
