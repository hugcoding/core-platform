import unittest
from pathlib import Path

from core.integrity.ocr_duplicate_similarity import (
    ANALYZER_VERSION, compare_ocr_text, evidence_metadata, group_key,
)


ROOT = Path(__file__).resolve().parents[1]


class OcrDuplicateSimilarityTests(unittest.TestCase):
    def test_small_ocr_noise_is_a_near_duplicate(self):
        common = " ".join(f"clausule {number} overeenkomst woning vanbruggen" for number in range(300))
        result = compare_ocr_text(common + " handtekening", common + " handtekeninq")
        self.assertTrue(result["qualifies"])
        self.assertGreaterEqual(result["length_ratio"], 0.98)
        self.assertGreaterEqual(result["token_jaccard"], 0.95)
        self.assertGreaterEqual(result["fivegram_jaccard"], 0.90)

    def test_different_documents_are_not_grouped(self):
        left = "arbeidsovereenkomst salaris werkgever " * 150
        right = "hypotheek woning rente lening " * 150
        self.assertFalse(compare_ocr_text(left, right)["qualifies"])

    def test_short_templates_are_not_grouped(self):
        self.assertFalse(compare_ocr_text("zelfde tekst", "zelfde tekst")["qualifies"])

    def test_group_key_is_pair_order_independent(self):
        left, right = "a" * 64, "b" * 64
        self.assertEqual(group_key("contract", left, right), group_key("contract", right, left))

    def test_evidence_requires_human_review(self):
        evidence = evidence_metadata("contract", 2, {"qualifies": True})
        self.assertTrue(evidence["requires_human_review"])
        self.assertFalse(evidence["automatic_deletion_allowed"])
        self.assertFalse(evidence["raw_text_stored_in_database"])

    def test_worker_is_bounded_and_migration_allows_reviewed_signed_ocr(self):
        worker = (ROOT / "workset_ocr_worker.py").read_text("utf-8")
        migration = (ROOT / "database/migrations/20260916_allow_reviewed_ocr_near_duplicates.sql").read_text("utf-8")
        self.assertIn("def discover_ocr_near_duplicates(limit: int = 3)", worker)
        self.assertIn("r.file_id>l.file_id", worker)
        self.assertIn("LIMIT %s", worker)
        self.assertIn("ocr_similarity_comparisons", worker)
        self.assertIn("CREATE TABLE IF NOT EXISTS public.ocr_similarity_comparisons", migration)
        self.assertIn("BEFORE UPDATE OR DELETE", migration)
        self.assertIn("automatic_deletion_allowed", evidence_metadata("x", 1, {}))
        self.assertIn(ANALYZER_VERSION, migration)
        self.assertIn("NOT e.signature_present OR e.analyzer_version", migration)

    def test_policy_and_operations_are_documented(self):
        documentation = (ROOT / "project/reports/OCR-NEAR-DUPLICATE-DETECTION.md").read_text("utf-8")
        for value in ("minimaal 500", "minimaal 98%", "minimaal 95%", "minimaal 90%"):
            self.assertIn(value, documentation)
        self.assertIn("nooit automatisch", documentation)
        self.assertIn("20260916_allow_reviewed_ocr_near_duplicates.sql", documentation)
        self.assertIn("ocr_similarity_comparisons", documentation)


if __name__ == "__main__":
    unittest.main()
