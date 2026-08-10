import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from core.metadata.date_evidence import (
    EXTRACTOR_VERSION, extract_date_evidence, idempotency_key,
)


CORE_XML = """<?xml version="1.0"?>
<cp:coreProperties
 xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dcterms="http://purl.org/dc/terms/">
 <dcterms:created>2025-01-02T03:04:05Z</dcterms:created>
 <dcterms:modified>2025-02-03T04:05:06+02:00</dcterms:modified>
</cp:coreProperties>"""


class DateEvidenceExtractionTests(unittest.TestCase):
    def office_file(self, suffix):
        temporary = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        temporary.close()
        path = Path(temporary.name)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("docProps/core.xml", CORE_XML)
        self.addCleanup(path.unlink)
        return path

    def test_docx_and_xlsx_share_uniform_contract(self):
        for suffix in (".docx", ".xlsx"):
            with self.subTest(suffix=suffix):
                evidence = extract_date_evidence(self.office_file(suffix))
                self.assertEqual(["created", "modified"], [row["date_type"] for row in evidence])
                self.assertEqual(
                    {"office_core_properties"}, {row["source_type"] for row in evidence}
                )
                self.assertEqual({"content"}, {row["evidence_scope"] for row in evidence})
                self.assertEqual("2025-01-02T03:04:05+00:00", evidence[0]["value_at"])
                self.assertEqual(120, evidence[1]["timezone_offset_minutes"])
                self.assertEqual(EXTRACTOR_VERSION, evidence[0]["extractor_version"])

    def test_pdf_info_dictionary_uses_same_contract(self):
        reader = SimpleNamespace(
            is_encrypted=False,
            metadata={"/CreationDate": "D:20240102030405Z", "/ModDate": "D:20240203040506+02'00'"},
        )
        evidence = extract_date_evidence(
            Path("example.pdf"), pdf_reader_factory=lambda _: reader
        )
        self.assertEqual(["created", "modified"], [row["date_type"] for row in evidence])
        self.assertEqual({"pdf_info_dictionary"}, {row["source_type"] for row in evidence})
        self.assertEqual("2024-02-03T02:05:06+00:00", evidence[1]["value_at"])

    def test_pdf_xmp_is_retained_beside_info_dictionary(self):
        reader = SimpleNamespace(
            is_encrypted=False,
            metadata={"/CreationDate": "D:20240102030405Z"},
            xmp_metadata=SimpleNamespace(
                xmp_create_date=datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
                xmp_modify_date=datetime(2024, 2, 3, 4, 5, 6, tzinfo=timezone.utc),
            ),
        )
        evidence = extract_date_evidence(
            Path("example.pdf"), pdf_reader_factory=lambda _: reader
        )
        self.assertEqual(3, len(evidence))
        self.assertEqual(2, sum(row["source_type"] == "pdf_xmp" for row in evidence))

    def test_missing_timezone_is_retained_without_inventing_utc(self):
        reader = SimpleNamespace(
            is_encrypted=False, metadata={"/CreationDate": "D:20240102030405"}
        )
        row = extract_date_evidence(
            Path("example.pdf"), pdf_reader_factory=lambda _: reader
        )[0]
        self.assertIsNone(row["value_at"])
        self.assertEqual("2024-01-02T03:04:05", row["local_value"])
        self.assertEqual("absent", row["timezone_status"])
        self.assertEqual("low", row["confidence"])

    def test_real_world_pdf_utc_suffix_variants_are_normalized(self):
        for raw in ("D:20250211174245Z00'00'", "D:20251125013310Z'"):
            with self.subTest(raw=raw):
                reader = SimpleNamespace(
                    is_encrypted=False, metadata={"/CreationDate": raw}, xmp_metadata=None
                )
                row = extract_date_evidence(
                    Path("example.pdf"), pdf_reader_factory=lambda _: reader
                )[0]
                self.assertEqual("utc", row["timezone_status"])
                self.assertTrue(row["value_at"].endswith("+00:00"))

    def test_idempotency_tracks_content_version_and_extractor(self):
        evidence = extract_date_evidence(self.office_file(".docx"))[0]
        first = idempotency_key(12, "a" * 64, evidence)
        self.assertEqual(first, idempotency_key(12, "a" * 64, evidence))
        self.assertEqual(first, idempotency_key(99, "a" * 64, evidence))
        self.assertNotEqual(first, idempotency_key(12, "b" * 64, evidence))
        file_evidence = {**evidence, "evidence_scope": "file"}
        self.assertNotEqual(
            idempotency_key(12, "a" * 64, file_evidence),
            idempotency_key(99, "a" * 64, file_evidence),
        )


class DateEvidenceMigrationTests(unittest.TestCase):
    def test_migration_is_generic_append_only_and_has_current_view(self):
        root = Path(__file__).resolve().parents[1]
        sql = (root / "database/migrations/20260810_add_file_date_evidence.sql").read_text("utf-8")
        rollback = (root / "database/migrations/rollback/20260810_add_file_date_evidence.sql").read_text("utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS public.file_date_evidence", sql)
        self.assertIn("idempotency_key text NOT NULL UNIQUE", sql)
        self.assertIn("evidence_scope text NOT NULL", sql)
        self.assertNotIn("file_id bigint NOT NULL REFERENCES public.files(id) ON DELETE CASCADE", sql)
        self.assertIn("CREATE OR REPLACE VIEW public.v_file_temporal_profile", sql)
        self.assertNotIn("pdf_created_at", sql)
        self.assertNotIn("office_created_at", sql)
        self.assertIn("DROP TABLE IF EXISTS public.file_date_evidence", rollback)

    def test_worker_image_and_cli_include_backfill_runtime(self):
        root = Path(__file__).resolve().parents[1]
        dockerfile = (root / "Dockerfile.metadata").read_text("utf-8")
        cli = (root / "tools/runtime/core").read_text("utf-8")
        runtime = (root / "tools/runtime/date_evidence_backfill.py").read_text("utf-8")
        self.assertIn("COPY core/metadata ./core/metadata", dockerfile)
        self.assertIn("pypdf cryptography", dockerfile)
        self.assertIn("metadata date-backfill", cli)
        self.assertIn("--dry-run", runtime)
        self.assertIn("--apply", runtime)
        self.assertIn('"file_mutations": False', runtime)


if __name__ == "__main__":
    unittest.main()
