import json
import unittest
from pathlib import Path

from core.semantic.query_embedding import embed_queries, embed_query
from core.semantic.similarity import (
    query_terms, render_document_similarity_sql, render_hybrid_query_similarity_sql,
    render_query_similarity_sql, vector_literal,
)
from core.semantic.retrieval_evaluation import apply_review_csv, evaluate_results, load_evaluation, render_markdown, review_rows


class FakeVectors(list):
    def tolist(self):
        return list(self)


class FakeModel:
    def encode(self, passages, **kwargs):
        self.passages = passages
        return FakeVectors([[0.1] * 384 for _ in passages])


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

    def test_query_batch_loads_model_once(self):
        created = []
        vectors = embed_queries(
            ["python", "data science"], Path("."),
            model_factory=lambda path: created.append(FakeModel()) or created[0],
        )
        self.assertEqual(1, len(created))
        self.assertEqual(2, len(vectors))

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

    def test_hybrid_sql_combines_embedding_and_path_terms(self):
        sql = render_hybrid_query_similarity_sql(
            [0.1] * 384, "SQL cursus certificaat", limit=5,
        )
        self.assertIn("0.85 *", sql)
        self.assertIn("lexical_similarity", sql)
        self.assertIn("%sql%", sql)
        self.assertIn("regexp_replace(v.golden_path", sql)
        self.assertNotIn("lower(v.golden_filename || ' ' || v.golden_path)", sql)
        self.assertEqual(["sql", "cursus", "certificaat"], query_terms("SQL cursus en certificaat"))

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
        self.assertIn("retrieval-evaluate)", cli)

    def test_evaluation_config_and_metrics(self):
        root = Path(__file__).resolve().parents[1]
        config = load_evaluation(root / "project/pilots/scrum-59-retrieval-evaluation-v1.json")
        self.assertEqual(15, len(config["queries"]))
        self.assertTrue(any(item["id"].startswith("semantic-") for item in config["queries"]))
        self.assertTrue(any(item["id"].startswith("hard-negative-") for item in config["queries"]))
        expected = config["queries"][0]["expected_file_ids"][0]
        runs = {
            "embedding-v1": [[{"file_id": 999}, {"file_id": expected}]] + [[{"file_id": item["expected_file_ids"][0]}] for item in config["queries"][1:]],
            "hybrid-v1": [[{"file_id": item["expected_file_ids"][0]}] for item in config["queries"]],
        }
        report = evaluate_results(config, runs)
        self.assertEqual(1.0, report["rankings"]["hybrid-v1"]["hit_at_1"])
        self.assertLess(report["rankings"]["embedding-v1"]["mean_reciprocal_rank"], 1.0)

    def test_v2_expands_document_families_and_calculates_graded_ndcg(self):
        root = Path(__file__).resolve().parents[1]
        config = load_evaluation(root / "project/pilots/scrum-59-retrieval-evaluation-v2.json")
        self.assertEqual("semantic-retrieval-evaluation-v2", config["schema_version"])
        self.assertEqual(5, config["document_family_count"])
        self.assertEqual([3361765, 3361766], config["queries"][0]["judgments"]["relevant"])
        query = config["queries"][0]
        rows = [
            {"file_id": 3361767, "filename": "rules.pdf", "path": "/vve/rules.pdf", "ranking_score": 0.8},
            {"file_id": 3361765, "filename": "riool.pdf", "path": "/vve/riool.pdf", "ranking_score": 0.7},
            {"file_id": 999, "filename": "unknown.pdf", "path": "/unknown.pdf", "ranking_score": 0.6},
        ]
        report = evaluate_results({
            "schema_version": config["schema_version"],
            "document_family_count": config["document_family_count"],
            "queries": [query],
        }, {"hybrid-v1": [rows]})
        metrics = report["rankings"]["hybrid-v1"]
        self.assertEqual(2, metrics["queries"][0]["best_relevant_rank"])
        self.assertGreater(metrics["ndcg_at_10"], 0.0)
        self.assertLess(metrics["ndcg_at_10"], 1.0)
        review = metrics["queries"][0]["top_10_review"]
        self.assertEqual(["related", "relevant", "unjudged"], [row["judgment"] for row in review])
        markdown = render_markdown(report)
        self.assertIn("NDCG@10", markdown)
        self.assertIn("riool.pdf", markdown)
        self.assertIn("/vve/riool.pdf", markdown)
        rows = review_rows(report)
        self.assertEqual(3, len(rows))
        self.assertEqual("related", rows[0]["review_judgment"])
        self.assertEqual("", rows[2]["review_judgment"])
        self.assertIn("document_family", rows[0])
        self.assertIn("reviewer_notes", rows[0])

    def test_v2_rejects_conflicting_or_unknown_family_judgments(self):
        import tempfile
        for query in (
            {"id": "q", "query": "test", "relevant_families": ["missing"]},
            {"id": "q", "query": "test", "relevant_file_ids": [1], "related_file_ids": [1]},
        ):
            config = {"schema_version": "semantic-retrieval-evaluation-v2", "queries": [query]}
            with tempfile.TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "evaluation.json"
                path.write_text(json.dumps(config), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_evaluation(path)

    def test_compact_review_overrides_judgment_and_reports_top3_coverage(self):
        import tempfile
        root = Path(__file__).resolve().parents[1]
        config = load_evaluation(root / "project/pilots/scrum-59-retrieval-evaluation-v2.json")
        with tempfile.TemporaryDirectory() as temp_dir:
            review = Path(temp_dir) / "review.csv"
            review.write_text(
                "query_id;file_id;review_judgment\n"
                "vve-riolering;999;hard_negative\n",
                encoding="utf-8",
            )
            apply_review_csv(config, review)
        query = config["queries"][0]
        report = evaluate_results(
            {"schema_version": config["schema_version"], "queries": [query]},
            {"hybrid-v1": [[{"file_id": 999}, {"file_id": 3361765}]]},
        )
        metrics = report["rankings"]["hybrid-v1"]
        self.assertEqual(1, metrics["hard_negative_in_top_3"])
        self.assertEqual(0.5, metrics["human_review_coverage_at_3"])
        self.assertIn("NDCG@3", render_markdown(report))

    def test_nas_host_runtime_avoids_python_310_zip_strict(self):
        root = Path(__file__).resolve().parents[1]
        host_runtime = (root / "tools/runtime/semantic_retrieval_evaluate.py").read_text("utf-8")
        evaluation = (root / "core/semantic/retrieval_evaluation.py").read_text("utf-8")
        self.assertNotIn("strict=True", host_runtime)
        self.assertNotIn("strict=True", evaluation)
        self.assertIn("does not match evaluation query count", host_runtime)


if __name__ == "__main__":
    unittest.main()
