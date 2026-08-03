import json
import unittest
from pathlib import Path

from core.semantic.query_embedding import embed_query
from core.semantic.similarity import (
    render_document_similarity_sql, render_query_similarity_sql, vector_literal,
)


class FakeVectors(list):
    def tolist(self):
        return list(self)


class FakeModel:
    def encode(self, passages, **kwargs):
        self.passages = passages
        return FakeVectors([[0.1] * 384])


class SemanticSimilarityTests(unittest.TestCase):
    def test_query_uses_e5_prefix_and_returns_384_dimensions(self):
        model = FakeModel()
        vector = embed_query("  golden   records ", Path("."), model_factory=lambda path: model)
        self.assertEqual(["query: golden records"], model.passages)
        self.assertEqual(384, len(vector))

    def test_query_rejects_empty_or_wrong_dimension(self):
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            embed_query(" ", Path("."), model_factory=lambda path: FakeModel())
        with self.assertRaisesRegex(ValueError, "dimension 384"):
            embed_query("query", Path("."), model_factory=lambda path: type(
                "Bad", (), {"encode": lambda self, *args, **kwargs: FakeVectors([[0.1]])}
            )())

    def test_query_sql_is_read_only_and_filters_current_golden_records(self):
        sql = render_query_similarity_sql([0.1] * 384, limit=5, threshold=0.5)
        self.assertIn("<=>", sql)
        self.assertIn("v_semantic_golden_records", sql)
        self.assertIn("semantic_metadata_current", sql)
        self.assertIn("LIMIT 5", sql)
        self.assertNotIn("INSERT", sql)
        self.assertNotIn("UPDATE", sql)
        self.assertNotIn("DELETE", sql)

    def test_document_sql_excludes_source_and_requires_same_model_lineage(self):
        sql = render_document_similarity_sql(103, limit=10, threshold=0.25)
        self.assertIn("source.file_id = 103", sql)
        self.assertIn("target.file_id <> source.file_id", sql)
        self.assertIn("source_run.model_revision = target_run.model_revision", sql)
        self.assertIn("source_v.semantic_run_id = source.semantic_run_id", sql)

    def test_search_bounds_and_vector_dimension_are_validated(self):
        with self.assertRaisesRegex(ValueError, "limit"):
            render_query_similarity_sql([0.1] * 384, limit=0)
        with self.assertRaisesRegex(ValueError, "threshold"):
            render_document_similarity_sql(1, threshold=1.1)
        with self.assertRaisesRegex(ValueError, "dimension 384"):
            vector_literal([0.1])

    def test_cli_is_offline_and_read_only(self):
        root = Path(__file__).resolve().parents[1]
        runtime = (root / "tools/runtime/semantic_similarity.py").read_text("utf-8")
        cli = (root / "tools/runtime/core").read_text("utf-8")
        self.assertIn('"--network", "none"', runtime)
        self.assertIn('"--read-only"', runtime)
        self.assertIn("similarity)", cli)


if __name__ == "__main__":
    unittest.main()
