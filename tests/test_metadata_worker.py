import sys
import types
import unittest
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
            "inode": 1234,
            "size_bytes": 100,
            "modified_at_fs": 200,
            "hash_content": "content",
        }
        with mock.patch.object(metadata_worker, "path_is_missing", return_value=True):
            score, level, signals = metadata_worker.identity_confidence(
                candidate, 1234, 100, 200, "content"
            )

        self.assertEqual(100, score)
        self.assertEqual("high", level)
        self.assertTrue(all(signals.values()))

    def test_inode_match_alone_is_low_confidence(self):
        candidate = {
            "path": "/volume1/old.txt",
            "inode": 1234,
            "size_bytes": 50,
            "modified_at_fs": 100,
            "hash_content": "old",
        }
        with mock.patch.object(metadata_worker, "path_is_missing", return_value=False):
            score, level, _ = metadata_worker.identity_confidence(
                candidate, 1234, 100, 200, "new"
            )

        self.assertEqual(30, score)
        self.assertEqual("low", level)

    def test_missing_path_with_same_inode_is_a_rename(self):
        cursor = CandidateCursor(inode_rows=[{
            "id": 42, "path": "/volume1/old.txt", "inode": 1234,
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
            "id": 42, "path": "/volume1/old.txt", "inode": 1234,
            "size_bytes": 100, "modified_at_fs": 200, "hash_content": "content",
        }])
        with mock.patch.object(metadata_worker, "path_is_missing", return_value=True):
            result = metadata_worker.evaluate_identity_match(
                cursor, "/volume1/new.txt", 1234, 100, 200, "content"
            )
        self.assertEqual("auto_linked", result["decision"])
        self.assertEqual("IDENTITY_MATCHED", result["event_type"])


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


class ScanSessionTests(unittest.TestCase):
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
            return {"id": 42}
        return None

    def fetchall(self):
        return self.rename_rows


class MutationPersistenceTests(unittest.TestCase):
    def process_upsert(self, cursor, path="/volume1/photos/new.jpg", stat_side_effect=None):
        file_stat = types.SimpleNamespace(st_size=100, st_mtime=200, st_ino=1234)
        stat_effect = stat_side_effect or (lambda candidate_path: file_stat)

        with (
            mock.patch.object(metadata_worker.os.path, "exists", return_value=True),
            mock.patch.object(metadata_worker.os, "stat", side_effect=stat_effect),
            mock.patch.object(metadata_worker, "upsert_folder", return_value=7),
            mock.patch.object(metadata_worker, "hash_first_1024", return_value="content"),
            mock.patch.object(metadata_worker, "get_mime", return_value="image/jpeg"),
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
            "id": 42, "path": old_path, "inode": 1234,
            "size_bytes": 100, "modified_at_fs": 200, "hash_content": "content",
        }])
        file_stat = types.SimpleNamespace(st_size=100, st_mtime=200, st_ino=1234)

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


if __name__ == "__main__":
    unittest.main()
