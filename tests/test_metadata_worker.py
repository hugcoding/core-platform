import sys
import types
import unittest
import tempfile
from pathlib import Path
from unittest import mock


redis_stub = types.ModuleType("redis")
redis_stub.Redis = lambda *args, **kwargs: None
redis_stub.exceptions = types.SimpleNamespace(ResponseError=Exception)
sys.modules["redis"] = redis_stub

psycopg2_stub = types.ModuleType("psycopg2")
psycopg2_stub.__path__ = []
psycopg2_stub.connect = lambda *args, **kwargs: None
psycopg2_extras_stub = types.ModuleType("psycopg2.extras")
psycopg2_extras_stub.RealDictCursor = object
psycopg2_stub.extras = psycopg2_extras_stub
sys.modules["psycopg2"] = psycopg2_stub
sys.modules["psycopg2.extras"] = psycopg2_extras_stub

magic_stub = types.ModuleType("magic")
magic_stub.from_file = lambda *args, **kwargs: None
sys.modules["magic"] = magic_stub

pyvips_stub = types.ModuleType("pyvips")
pyvips_stub.Image = types.SimpleNamespace(new_from_file=lambda path: None)
sys.modules["pyvips"] = pyvips_stub

xxhash_stub = types.ModuleType("xxhash")
xxhash_stub.xxh64 = lambda value: types.SimpleNamespace(hexdigest=lambda: "hash")
sys.modules["xxhash"] = xxhash_stub

import metadata_worker


class CandidateCursor:
    def __init__(self, path_row=None, inode_rows=None):
        self.path_row = path_row
        self.inode_rows = inode_rows or []
        self.query_count = 0

    def execute(self, query, params):
        self.query_count += 1

    def fetchone(self):
        return self.path_row

    def fetchall(self):
        return self.inode_rows


class RenameCandidateTests(unittest.TestCase):
    def test_identity_confidence_is_high_when_all_signals_match(self):
        candidate = {
            "path": "/volume1/old.txt",
            "filesystem_device": 99,
            "inode": 1234,
            "size_bytes": 100,
            "modified_at_fs": 200,
            "hash_content": "content",
        }
        with mock.patch.object(metadata_worker, "path_is_missing", return_value=True):
            score, level, signals = metadata_worker.identity_confidence(
                candidate, 99, 1234, 100, 200, "content"
            )

        self.assertEqual(100, score)
        self.assertEqual("high", level)
        self.assertTrue(all(signals.values()))

    def test_inode_match_alone_is_low_confidence(self):
        candidate = {
            "path": "/volume1/old.txt",
            "filesystem_device": 99,
            "inode": 1234,
            "size_bytes": 50,
            "modified_at_fs": 100,
            "hash_content": "old",
        }
        with mock.patch.object(metadata_worker, "path_is_missing", return_value=False):
            score, level, _ = metadata_worker.identity_confidence(
                candidate, 99, 1234, 100, 200, "new"
            )

        self.assertEqual(40, score)
        self.assertEqual("low", level)

    def test_missing_path_with_same_inode_is_a_rename(self):
        cursor = CandidateCursor(inode_rows=[{
            "id": 42, "path": "/volume1/old.txt", "filesystem_device": 99, "inode": 1234,
            "size_bytes": 100, "modified_at_fs": 200, "hash_content": None,
        }])

        with mock.patch.object(metadata_worker.os, "stat", side_effect=FileNotFoundError):
            candidate = metadata_worker.find_rename_candidate(
                cursor, "/volume1/new.txt", 1234, 100, 200
            )

        self.assertIsNone(candidate)

    def test_existing_hardlink_is_not_a_rename(self):
        cursor = CandidateCursor(inode_rows=[{"id": 42, "path": "/volume1/old.txt"}])

        with mock.patch.object(metadata_worker.os, "stat", return_value=object()):
            candidate = metadata_worker.find_rename_candidate(
                cursor, "/volume1/new.txt", 1234, 100, 200
            )

        self.assertIsNone(candidate)

    def test_multiple_missing_candidates_are_ambiguous(self):
        cursor = CandidateCursor(inode_rows=[
            {"id": 41, "path": "/volume1/older.txt"},
            {"id": 42, "path": "/volume1/old.txt"},
        ])

        with mock.patch.object(metadata_worker.os, "stat", side_effect=FileNotFoundError):
            candidate = metadata_worker.find_rename_candidate(
                cursor, "/volume1/new.txt", 1234, 100, 200
            )

        self.assertIsNone(candidate)

    def test_unique_complete_match_is_automatically_linked(self):
        cursor = CandidateCursor(inode_rows=[{
            "id": 42, "path": "/volume1/old.txt",
            "filesystem_device": 99, "inode": 1234,
            "size_bytes": 100, "modified_at_fs": 200, "hash_content": "content",
        }])
        with mock.patch.object(metadata_worker, "path_is_missing", return_value=True):
            result = metadata_worker.evaluate_identity_match(
                cursor, "/volume1/new.txt", 99, 1234, 100, 200, "content"
            )
        self.assertEqual("auto_linked", result["decision"])
        self.assertEqual("IDENTITY_MATCHED", result["event_type"])

    def test_same_inode_on_different_filesystem_is_rejected(self):
        cursor = CandidateCursor(inode_rows=[{
            "id": 42, "path": "/volume1/other/file.txt",
            "filesystem_device": 7, "inode": 1234,
            "size_bytes": 100, "modified_at_fs": 200,
            "hash_content": "content",
        }])
        with mock.patch.object(metadata_worker, "path_is_missing", return_value=True):
            result = metadata_worker.evaluate_identity_match(
                cursor, "/volume1/new.txt", 99, 1234, 100, 200, "content"
            )
        self.assertEqual("created_separate", result["decision"])
        self.assertEqual("medium", result["level"])
        self.assertFalse(result["signals"]["filesystem_device_match"])


class MutationClassificationTests(unittest.TestCase):
    def test_path_mutations(self):
        self.assertEqual("CREATED", metadata_worker.classify_path_mutation(None))
        self.assertEqual(
            "MODIFIED",
            metadata_worker.classify_path_mutation({"deleted_at": None}),
        )
        self.assertEqual(
            "RESTORED",
            metadata_worker.classify_path_mutation({"deleted_at": object()}),
        )

    def test_rename_in_same_folder(self):
        mutation = metadata_worker.classify_rename_mutation(
            "/volume1/photos/old.jpg",
            "/volume1/photos/new.jpg",
        )
        self.assertEqual("RENAMED", mutation)

    def test_move_to_different_folder(self):
        mutation = metadata_worker.classify_rename_mutation(
            "/volume1/photos/file.jpg",
            "/volume1/archive/file.jpg",
        )
        self.assertEqual("MOVED", mutation)

    def test_identical_observed_state_is_not_a_material_change(self):
        existing = {
            "deleted_at": None,
            "size_bytes": 100,
            "modified_at_fs": 200,
            "filesystem_device": 99,
            "inode": 1234,
        }

        self.assertTrue(metadata_worker.observed_file_state_is_unchanged(
            existing,
            size_bytes=100,
            modified_at_fs=200,
            filesystem_device=99,
            inode=1234,
        ))
        self.assertFalse(metadata_worker.observed_file_state_is_unchanged(
            existing,
            size_bytes=101,
            modified_at_fs=200,
            filesystem_device=99,
            inode=1234,
        ))


class ScanSessionTests(unittest.TestCase):
    def test_empty_scan_session_is_stored_as_null(self):
        cursor = mock.Mock()

        metadata_worker.insert_file_event(
            cursor,
            file_id=42,
            event_type="CREATED",
            source="filesystem_watcher",
            scan_session_id="",
        )

        params = cursor.execute.call_args.args[1]
        self.assertIsNone(params[-2])

    def test_processed_job_updates_its_scan_session(self):
        cursor = CandidateCursor()

        metadata_worker.mark_session_job_processed(
            cursor, {"scan_session_id": "f93d9348-7c3a-42e1-a123-dc31e08a7319"}
        )

        self.assertEqual(1, cursor.query_count)

    def test_legacy_event_without_session_is_ignored(self):
        cursor = CandidateCursor()

        metadata_worker.mark_session_job_processed(cursor, {"event": "UPSERT"})

        self.assertEqual(0, cursor.query_count)

    def test_session_update_failure_does_not_fail_event(self):
        cursor = mock.Mock()
        cursor.execute.side_effect = RuntimeError("old database schema")

        metadata_worker.mark_session_job_processed(
            cursor, {"scan_session_id": "f93d9348-7c3a-42e1-a123-dc31e08a7319"}
        )


class StreamPriorityTests(unittest.TestCase):
    def test_realtime_stream_is_checked_before_polling(self):
        realtime_response = [
            (metadata_worker.REALTIME_STREAM_KEY, [("1-0", {"event": "UPSERT"})])
        ]
        redis_client = mock.Mock()
        redis_client.xreadgroup.return_value = realtime_response

        with mock.patch.object(metadata_worker, "r", redis_client):
            response = metadata_worker.read_next_batch()

        self.assertEqual(realtime_response, response)
        redis_client.xreadgroup.assert_called_once_with(
            metadata_worker.GROUP_NAME,
            metadata_worker.CONSUMER_NAME,
            streams={metadata_worker.REALTIME_STREAM_KEY: ">"},
            count=50,
        )

    def test_polling_batch_is_small_when_realtime_stream_is_empty(self):
        polling_response = [
            (metadata_worker.STREAM_KEY, [("2-0", {"event": "UPSERT"})])
        ]
        redis_client = mock.Mock()
        redis_client.xreadgroup.side_effect = [[], polling_response]

        with mock.patch.object(metadata_worker, "r", redis_client):
            response = metadata_worker.read_next_batch()

        self.assertEqual(polling_response, response)
        self.assertEqual(10, redis_client.xreadgroup.call_args.kwargs["count"])
        self.assertEqual(
            {metadata_worker.STREAM_KEY: ">"},
            redis_client.xreadgroup.call_args.kwargs["streams"],
        )


class ProcessCursor:
    def __init__(self, existing_file=None, rename_rows=None):
        self.existing_file = existing_file
        self.rename_rows = rename_rows or []
        self.calls = []
        self.current_query = ""

    def execute(self, query, params):
        self.current_query = query
        self.calls.append((query, params))

    def fetchone(self):
        if "SELECT id, path, deleted_at" in self.current_query:
            return self.existing_file
        if "RETURNING id" in self.current_query:
            return {"id": 42, "content_sha256": None, "size_bytes": 100}
        return None

    def fetchall(self):
        return self.rename_rows


class MutationPersistenceTests(unittest.TestCase):
    def process_upsert(self, cursor, path="/volume1/photos/new.jpg", stat_side_effect=None):
        file_stat = types.SimpleNamespace(st_size=100, st_mtime=200, st_ino=1234, st_dev=99)
        stat_effect = stat_side_effect or (lambda candidate_path: file_stat)

        with (
            mock.patch.object(metadata_worker.os.path, "exists", return_value=True),
            mock.patch.object(metadata_worker.os, "stat", side_effect=stat_effect),
            mock.patch.object(metadata_worker, "upsert_folder", return_value=7),
            mock.patch.object(metadata_worker, "hash_first_1024", return_value="content"),
            mock.patch.object(metadata_worker, "get_mime", return_value="image/jpeg"),
            mock.patch.object(metadata_worker, "recompute_golden_group"),
            mock.patch.object(metadata_worker, "get_image_dims", return_value=(10, 20)),
            mock.patch.object(
                metadata_worker,
                "r",
                types.SimpleNamespace(set=lambda *args, **kwargs: None),
            ),
        ):
            metadata_worker.process_event(cursor, {"event": "UPSERT", "path": path})

    def test_created_is_written_to_files_insert(self):
        cursor = ProcessCursor()

        self.process_upsert(cursor)

        query, params = next(call for call in cursor.calls if "INSERT INTO files" in call[0])
        self.assertIn("last_mutation_type", query)
        self.assertNotIn("last_mutation_at", query)
        self.assertNotIn("xxhash", query)
        self.assertEqual(query.count("%s"), len(params))
        self.assertEqual("CREATED", params[-1])
        event_query, event_params = next(
            call for call in cursor.calls if "INSERT INTO file_events" in call[0]
        )
        self.assertEqual(event_query.count("%s"), len(event_params))
        self.assertEqual("CREATED", event_params[2])

    def test_read_only_open_notification_does_not_create_modified_event(self):
        cursor = ProcessCursor(existing_file={
            "id": 42,
            "path": "/volume1/photos/new.jpg",
            "deleted_at": None,
            "size_bytes": 100,
            "modified_at_fs": 200,
            "filesystem_device": 99,
            "inode": 1234,
            "content_sha256": None,
        })

        self.process_upsert(cursor)

        self.assertFalse(any("INSERT INTO files" in query for query, _ in cursor.calls))
        self.assertFalse(any("UPDATE files SET" in query for query, _ in cursor.calls))
        self.assertFalse(any("INSERT INTO file_events" in query for query, _ in cursor.calls))

    def test_mime_is_only_written_to_canonical_files_column(self):
        cursor = ProcessCursor()

        self.process_upsert(cursor)

        files_query, _ = next(call for call in cursor.calls if "INSERT INTO files" in call[0])
        metadata_query, _ = next(call for call in cursor.calls if "INSERT INTO metadata" in call[0])
        self.assertIn("mime_type", files_query)
        self.assertNotIn("mime_type", metadata_query)


    def test_rename_is_written_to_existing_file_update(self):
        old_path = metadata_worker.os.path.normpath("/volume1/photos/old.jpg")
        new_path = metadata_worker.os.path.normpath("/volume1/photos/new.jpg")
        cursor = ProcessCursor(rename_rows=[{
            "id": 42, "path": old_path, "filesystem_device": 99, "inode": 1234,
            "size_bytes": 100, "modified_at_fs": 200, "hash_content": "content",
        }])
        file_stat = types.SimpleNamespace(st_size=100, st_mtime=200, st_ino=1234, st_dev=99)

        def stat_side_effect(candidate_path):
            if candidate_path == old_path:
                raise FileNotFoundError
            return file_stat

        self.process_upsert(cursor, new_path, stat_side_effect)

        query, params = next(call for call in cursor.calls if "UPDATE files SET" in call[0])
        self.assertIn("last_mutation_type", query)
        self.assertNotIn("last_mutation_at", query)
        self.assertEqual(query.count("%s"), len(params))
        self.assertEqual("RENAMED", params[-2])
        self.assertEqual(42, params[-1])

    def test_delete_writes_deleted_mutation(self):
        cursor = ProcessCursor()

        metadata_worker.process_event(
            cursor,
            {"event": "DELETE", "path": "/volume1/photos/old.jpg"},
        )

        query, _ = cursor.calls[0]
        self.assertIn("last_mutation_type = 'DELETED'", query)
        self.assertNotIn("last_mutation_at", query)
        self.assertIn("updated_at = NOW()", query)

    def test_document_event_computes_full_hash_and_recomputes_group(self):
        cursor = ProcessCursor()
        file_stat = types.SimpleNamespace(st_size=100, st_mtime=200, st_ino=1234, st_dev=99)
        with (
            mock.patch.object(metadata_worker.os.path, "exists", return_value=True),
            mock.patch.object(metadata_worker.os, "stat", return_value=file_stat),
            mock.patch.object(metadata_worker, "upsert_folder", return_value=7),
            mock.patch.object(metadata_worker, "hash_first_1024", return_value="fast"),
            mock.patch.object(metadata_worker, "hash_full_sha256", return_value="full-sha"),
            mock.patch.object(metadata_worker, "get_mime", return_value="text/plain"),
            mock.patch.object(metadata_worker, "get_image_dims", return_value=(None, None)),
            mock.patch.object(metadata_worker, "recompute_golden_group") as recompute,
            mock.patch.object(
                metadata_worker,
                "r",
                types.SimpleNamespace(set=lambda *args, **kwargs: None),
            ),
        ):
            metadata_worker.process_event(
                cursor,
                {"event": "UPSERT", "path": "/volume1/data/document.txt"},
            )

        recompute.assert_called_once_with(
            cursor, "full-sha", 100, "polling_scanner"
        )
        files_query, files_params = next(
            call for call in cursor.calls if "INSERT INTO files" in call[0]
        )
        self.assertIn("content_sha256", files_query)
        self.assertIn("full-sha", files_params)

    def test_empty_document_remains_inventoried_without_hash_or_golden_group(self):
        cursor = ProcessCursor()
        file_stat = types.SimpleNamespace(st_size=0, st_mtime=200, st_ino=1234, st_dev=99)
        with (
            mock.patch.object(metadata_worker.os.path, "exists", return_value=True),
            mock.patch.object(metadata_worker.os, "stat", return_value=file_stat),
            mock.patch.object(metadata_worker, "upsert_folder", return_value=7),
            mock.patch.object(metadata_worker, "hash_first_1024", return_value="empty-fast"),
            mock.patch.object(metadata_worker, "hash_full_sha256") as full_hash,
            mock.patch.object(metadata_worker, "get_mime", return_value="text/plain"),
            mock.patch.object(metadata_worker, "get_image_dims", return_value=(None, None)),
            mock.patch.object(metadata_worker, "recompute_golden_group") as recompute,
            mock.patch.object(metadata_worker, "r", types.SimpleNamespace(set=lambda *args, **kwargs: None)),
        ):
            metadata_worker.process_event(
                cursor, {"event": "UPSERT", "path": "/volume1/data/empty.txt"}
            )

        full_hash.assert_not_called()
        recompute.assert_not_called()
        insert_query, insert_params = next(call for call in cursor.calls if "INSERT INTO files" in call[0])
        self.assertEqual(insert_query.count("%s"), len(insert_params))
        self.assertIn(0, insert_params)

    def test_nonempty_to_empty_recomputes_only_the_old_group(self):
        existing = {
            "id": 42, "path": "/volume1/data/document.txt", "deleted_at": None,
            "size_bytes": 100, "modified_at_fs": 100, "content_sha256": "old-sha",
            "created_at": None, "updated_at": None,
        }
        cursor = ProcessCursor(existing_file=existing)
        file_stat = types.SimpleNamespace(st_size=0, st_mtime=200, st_ino=1234, st_dev=99)
        with (
            mock.patch.object(metadata_worker.os.path, "exists", return_value=True),
            mock.patch.object(metadata_worker.os, "stat", return_value=file_stat),
            mock.patch.object(metadata_worker, "upsert_folder", return_value=7),
            mock.patch.object(metadata_worker, "hash_first_1024", return_value="empty-fast"),
            mock.patch.object(metadata_worker, "hash_full_sha256") as full_hash,
            mock.patch.object(metadata_worker, "get_mime", return_value="text/plain"),
            mock.patch.object(metadata_worker, "get_image_dims", return_value=(None, None)),
            mock.patch.object(metadata_worker, "recompute_golden_group") as recompute,
            mock.patch.object(metadata_worker, "r", types.SimpleNamespace(set=lambda *args, **kwargs: None)),
        ):
            metadata_worker.process_event(
                cursor, {"event": "UPSERT", "path": "/volume1/data/document.txt"}
            )

        full_hash.assert_not_called()
        recompute.assert_called_once_with(cursor, "old-sha", 100, "polling_scanner")

    def test_empty_to_nonempty_creates_a_normal_content_group(self):
        existing = {
            "id": 42, "path": "/volume1/data/document.txt", "deleted_at": None,
            "size_bytes": 0, "modified_at_fs": 100, "content_sha256": None,
            "created_at": None, "updated_at": None,
        }
        cursor = ProcessCursor(existing_file=existing)
        file_stat = types.SimpleNamespace(st_size=10, st_mtime=200, st_ino=1234, st_dev=99)
        with (
            mock.patch.object(metadata_worker.os.path, "exists", return_value=True),
            mock.patch.object(metadata_worker.os, "stat", return_value=file_stat),
            mock.patch.object(metadata_worker, "upsert_folder", return_value=7),
            mock.patch.object(metadata_worker, "hash_first_1024", return_value="fast"),
            mock.patch.object(metadata_worker, "hash_full_sha256", return_value="new-sha"),
            mock.patch.object(metadata_worker, "get_mime", return_value="text/plain"),
            mock.patch.object(metadata_worker, "get_image_dims", return_value=(None, None)),
            mock.patch.object(metadata_worker, "recompute_golden_group") as recompute,
            mock.patch.object(metadata_worker, "r", types.SimpleNamespace(set=lambda *args, **kwargs: None)),
        ):
            metadata_worker.process_event(
                cursor, {"event": "UPSERT", "path": "/volume1/data/document.txt"}
            )

        recompute.assert_called_once_with(cursor, "new-sha", 10, "polling_scanner")


class DateEvidencePersistenceTests(unittest.TestCase):
    class Cursor:
        def __init__(self, schema=True):
            self.schema = schema
            self.current_query = ""
            self.calls = []
            self.rowcount = 0

        def execute(self, query, params):
            self.current_query = query
            self.calls.append((query, params))
            self.rowcount = 1 if "INSERT INTO file_date_evidence" in query else 0

        def fetchone(self):
            if "to_regclass" in self.current_query:
                return {"relation": "file_date_evidence" if self.schema else None}
            if "FROM content_groups" in self.current_query:
                return {"id": "group-id"}
            return None

    @staticmethod
    def observation(date_type="created"):
        return {
            "evidence_scope": "content", "date_type": date_type,
            "source_type": "office_core_properties",
            "source_field": f"dcterms:{date_type}", "raw_value": "2025-01-02T03:04:05Z",
            "value_at": "2025-01-02T03:04:05+00:00", "local_value": "2025-01-02T03:04:05",
            "timezone_offset_minutes": 0, "timezone_status": "utc", "confidence": "medium",
            "extractor_version": "date-evidence-v1", "details": {"container": "ooxml"},
        }

    def test_persistence_is_idempotent_and_links_content_group(self):
        cursor = self.Cursor()
        with mock.patch.object(
            metadata_worker, "extract_date_evidence",
            return_value=[self.observation(), self.observation("modified")],
        ):
            inserted = metadata_worker.persist_date_evidence(
                cursor, file_id=42, path="/volume1/data/a.docx", extension="docx",
                content_sha256="a" * 64, size_bytes=100,
            )
        inserts = [call for call in cursor.calls if "INSERT INTO file_date_evidence" in call[0]]
        self.assertEqual(2, inserted)
        self.assertEqual(2, len(inserts))
        self.assertIn("ON CONFLICT (idempotency_key) DO NOTHING", inserts[0][0])
        self.assertEqual("group-id", inserts[0][1][1])

    def test_old_schema_is_skipped_without_extraction(self):
        cursor = self.Cursor(schema=False)
        with mock.patch.object(metadata_worker, "extract_date_evidence") as extract:
            inserted = metadata_worker.persist_date_evidence(
                cursor, file_id=42, path="/volume1/data/a.pdf", extension="pdf",
                content_sha256="a" * 64, size_bytes=100,
            )
        self.assertEqual(0, inserted)
        extract.assert_not_called()

    def test_backfill_can_request_strict_extraction_errors(self):
        cursor = self.Cursor()
        with mock.patch.object(
            metadata_worker, "extract_date_evidence", side_effect=ValueError("corrupt")
        ):
            with self.assertRaisesRegex(ValueError, "corrupt"):
                metadata_worker.persist_date_evidence(
                    cursor, file_id=42, path="/volume1/data/a.xlsx", extension="xlsx",
                    content_sha256="a" * 64, size_bytes=100, strict_extraction=True,
                )


class EmptyGoldenGroupTests(unittest.TestCase):
    def test_empty_group_recomputation_is_ignored_without_golden_event(self):
        cursor = mock.Mock()

        metadata_worker.recompute_golden_group(cursor, "empty-sha", 0, "polling_scanner")

        cursor.execute.assert_not_called()

    def test_nonempty_group_passes_size_bytes_to_golden_ranking(self):
        class CandidateCursor:
            def __init__(self):
                self.query = ""

            def execute(self, query, params=None):
                self.query = query

            def fetchall(self):
                candidate = {
                    "file_id": 42,
                    "path": "/volume1/data/document.txt",
                    "created_at": None,
                    "updated_at": None,
                }
                if "size_bytes" in self.query.partition("FROM files")[0]:
                    candidate["size_bytes"] = 123
                return [candidate]

            def fetchone(self):
                return None

        def assert_candidate(candidate_rows):
            self.assertEqual(123, candidate_rows[0]["size_bytes"])
            raise StopIteration

        with mock.patch.object(
            metadata_worker, "rank_candidates", side_effect=assert_candidate
        ):
            with self.assertRaises(StopIteration):
                metadata_worker.recompute_golden_group(
                    CandidateCursor(), "full-sha", 123, "polling_scanner"
                )


class FullHashTests(unittest.TestCase):
    def test_full_sha256_reads_the_entire_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.txt"
            path.write_bytes(b"a" * 1024 + b"different-tail")
            digest = metadata_worker.hash_full_sha256(str(path), chunk_size=128)

        self.assertEqual(
            "cdc3a38991b86d7c4849475888ed6a699d7398deb28b42a775d41d6c4e418912",
            digest,
        )


if __name__ == "__main__":
    unittest.main()
