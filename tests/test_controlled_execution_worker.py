import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parents[1]


class ControlledExecutionWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.modules.setdefault("psycopg2", types.SimpleNamespace(connect=mock.Mock(), extras=types.SimpleNamespace(RealDictCursor=object)))
        sys.modules.setdefault("psycopg2.extras", sys.modules["psycopg2"].extras)
        redis_module = types.SimpleNamespace(Redis=mock.Mock, ResponseError=RuntimeError)
        redis_module.RedisError = RuntimeError
        sys.modules.setdefault("redis", redis_module)
        cls.worker = importlib.import_module("controlled_execution_worker")

    def test_resource_gate_prioritizes_memory_and_core_streams(self):
        self.assertEqual("waiting_for_memory", self.worker.resource_block(
            {"available_memory_mib": 100, "cpu_load_percent": 10}, 0))
        self.assertEqual("waiting_for_cpu", self.worker.resource_block(
            {"available_memory_mib": 9000, "cpu_load_percent": 99}, 0))
        self.assertEqual("core_pipeline_priority", self.worker.resource_block(
            {"available_memory_mib": 9000, "cpu_load_percent": 10}, 999999))

    def test_forward_batch_records_started_and_verified(self):
        item = {"id": "item", "current_status": "queued", "action_type": "migrate_active"}
        conn = mock.Mock()
        with mock.patch.object(self.worker, "batch_items", side_effect=[[item], [{**item, "current_status":"verified"}]]), \
             mock.patch.object(self.worker, "latest_batch_status", return_value="started"), \
             mock.patch.object(self.worker, "start_details", return_value={"mtime_ns": 1}) as preflight, \
             mock.patch.object(self.worker, "execute_item", return_value={"content_sha256": "a" * 64}) as execute, \
             mock.patch.object(self.worker, "append_event") as event:
            self.worker.process_forward(conn, {"id": "batch"})
        preflight.assert_called_once()
        execute.assert_called_once()
        self.assertEqual(["started", "started", "verified", "completed"],
                         [call.args[3] for call in event.call_args_list])

    def test_paused_batch_does_not_touch_next_file(self):
        item = {"id": "item", "current_status": "queued", "action_type": "migrate_active"}
        with mock.patch.object(self.worker, "batch_items", return_value=[item]), \
             mock.patch.object(self.worker, "latest_batch_status", return_value="paused"), \
             mock.patch.object(self.worker, "execute_item") as execute, \
             mock.patch.object(self.worker, "append_event"):
            self.worker.process_forward(mock.Mock(), {"id": "batch"})
        execute.assert_not_called()

    def test_planned_item_pauses_instead_of_silent_completion(self):
        with mock.patch.object(self.worker, 'batch_items', return_value=[{'id':'item','current_status':'planned'}]), \
             mock.patch.object(self.worker, 'latest_batch_status', return_value='started'), \
             mock.patch.object(self.worker, 'append_event') as events, \
             mock.patch.object(self.worker, 'execute_item') as execute:
            self.worker.process_forward(mock.Mock(), {'id':'batch'})
        execute.assert_not_called()
        self.assertEqual('paused', events.call_args.args[3])
        self.assertNotIn('completed',[call.args[3] for call in events.call_args_list])

    def test_completion_requires_all_items_terminal(self):
        with mock.patch.object(self.worker, 'batch_items', side_effect=[[],[{'current_status':'queued'}]]), \
             mock.patch.object(self.worker, 'append_event') as events:
            self.worker.process_forward(mock.Mock(), {'id':'batch','item_count':1})
        self.assertEqual('paused', events.call_args.args[3])

    def test_resource_change_between_items_returns_batch_to_queue(self):
        item = {"id": "item", "current_status": "queued", "action_type": "migrate_active"}
        with mock.patch.object(self.worker, "batch_items", return_value=[item]), \
             mock.patch.object(self.worker, "latest_batch_status", return_value="started"), \
             mock.patch.object(self.worker, "host_resources", return_value={"available_memory_mib": 10, "cpu_load_percent": 10}), \
             mock.patch.object(self.worker, "stream_lag", return_value=0), \
             mock.patch.object(self.worker, "append_event") as event:
            self.worker.process_forward(mock.Mock(), {"id": "batch"}, mock.Mock())
        self.assertEqual("queued", event.call_args_list[-1].args[3])
        self.assertEqual("waiting_for_memory", event.call_args_list[-1].args[5]["waiting_reason"])

    def test_started_item_uses_resume_path(self):
        item = {"current_status": "started", "action_type": "migrate_active",
                "target_path": "/volume1/data/Persoonlijk/Actief/x", "latest_details": {"mtime_ns": 1}}
        with mock.patch.object(self.worker.Path, "exists", return_value=True), \
             mock.patch.object(self.worker, "resume_verified_move", return_value={"resumed": True}) as resume:
            self.assertTrue(self.worker.execute_item(item)["resumed"])
        resume.assert_called_once()

    def test_interrupted_move_pauses_batch_for_safe_resume(self):
        item = {"id": "item", "current_status": "started", "action_type": "migrate_active",
                "target_path": "/volume1/data/Persoonlijk/Actief/x", "latest_details": {"mtime_ns": 1}}
        with mock.patch.object(self.worker, "batch_items", return_value=[item]), \
             mock.patch.object(self.worker, "latest_batch_status", return_value="started"), \
             mock.patch.object(self.worker, "execute_item", side_effect=OSError("interrupted")), \
             mock.patch.object(self.worker, "append_event") as event:
            self.worker.process_forward(mock.Mock(), {"id": "batch"})
        self.assertEqual("started", event.call_args_list[-2].args[3])
        self.assertEqual("paused", event.call_args_list[-1].args[3])

    def test_source_size_change_is_atomically_queued_for_reinventory(self):
        item = {"id": "item", "batch_id": "batch", "file_id": 42,
                "source_path": "/volume1/data/source.docx", "size_bytes": 10}
        client = mock.Mock()
        client.eval.return_value = "1-0"
        source_stat = mock.Mock(st_mode=0o100644, st_size=11, st_mtime_ns=12, st_ino=13)
        with mock.patch("core.execution.reinventory.Path") as path:
            path.return_value.lstat.return_value = source_stat
            result = self.worker.enqueue_source_reinventory(client, item)
        self.assertEqual("queued", result["reinventory_status"])
        self.assertEqual(11, result["observed_size_bytes"])
        self.assertEqual("scan_stream", client.eval.call_args.args[3])
        self.assertIn("UPSERT", client.eval.call_args.args[0])

    def test_source_size_block_records_reinventory_status(self):
        item = {"id": "item", "batch_id": "batch", "file_id": 42,
                "source_path": "/volume1/data/source.docx", "current_status": "queued",
                "action_type": "migrate_active"}
        with mock.patch.object(self.worker, "batch_items", side_effect=[[item], [{**item, "current_status": "blocked"}]]), \
             mock.patch.object(self.worker, "latest_batch_status", return_value="started"), \
             mock.patch.object(self.worker, "host_resources", return_value={"available_memory_mib": 9000, "cpu_load_percent": 10}), \
             mock.patch.object(self.worker, "stream_lag", return_value=0), \
             mock.patch.object(self.worker, "start_details", side_effect=self.worker.MigrationSafetyError("source_size_changed")), \
             mock.patch.object(self.worker, "enqueue_source_reinventory", return_value={"reinventory_status": "queued"}) as enqueue, \
             mock.patch.object(self.worker, "append_event") as event:
            self.worker.process_forward(mock.Mock(), {"id": "batch"}, mock.Mock())
        enqueue.assert_called_once()
        blocked = [call for call in event.call_args_list if call.args[3] == "blocked"][0]
        self.assertEqual("queued", blocked.args[5]["reinventory_status"])

    def test_rollback_is_reverse_order_and_append_only(self):
        items = [{"id": "one", "current_status": "verified"}, {"id": "two", "current_status": "verified"}]
        with mock.patch.object(self.worker, "batch_items", return_value=items), \
             mock.patch.object(self.worker, "rollback_item", side_effect=[{"n": 2}, {"n": 1}]) as rollback, \
             mock.patch.object(self.worker, "append_event") as event:
            self.worker.process_rollback(mock.Mock(), {"id": "batch"})
        self.assertEqual("two", rollback.call_args_list[0].args[0]["id"])
        self.assertEqual(["rolled_back", "rolled_back", "rolled_back"],
                         [call.args[3] for call in event.call_args_list])

    def test_container_and_integration_contract_exist(self):
        compose = (ROOT / "docker-compose.yml").read_text("utf-8")
        dockerfile = (ROOT / "Dockerfile.controlled-execution-worker").read_text("utf-8")
        integration = (ROOT / "tests/integration/controlled-execution/compose.yml").read_text("utf-8")
        self.assertIn("controlled_execution_worker:", compose)
        self.assertIn('"/volume1/data:/volume1/data"', compose)
        self.assertIn("controlled_execution_worker.py", dockerfile)
        self.assertIn("postgres:16-alpine", integration)


if __name__ == "__main__": unittest.main()
