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
        sys.modules.setdefault("redis", redis_module)
        cls.worker = importlib.import_module("controlled_execution_worker")

    def test_resource_gate_prioritizes_memory_and_core_streams(self):
        self.assertEqual("waiting_for_memory", self.worker.resource_block(
            {"available_memory_mib": 100, "load_per_cpu": 0.1}, 0))
        self.assertEqual("waiting_for_cpu", self.worker.resource_block(
            {"available_memory_mib": 9000, "load_per_cpu": 9}, 0))
        self.assertEqual("core_pipeline_priority", self.worker.resource_block(
            {"available_memory_mib": 9000, "load_per_cpu": 0.1}, 999999))

    def test_forward_batch_records_started_and_verified(self):
        item = {"id": "item", "current_status": "queued", "action_type": "migrate_active"}
        conn = mock.Mock()
        with mock.patch.object(self.worker, "batch_items", return_value=[item]), \
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

    def test_resource_change_between_items_returns_batch_to_queue(self):
        item = {"id": "item", "current_status": "queued", "action_type": "migrate_active"}
        with mock.patch.object(self.worker, "batch_items", return_value=[item]), \
             mock.patch.object(self.worker, "latest_batch_status", return_value="started"), \
             mock.patch.object(self.worker, "host_resources", return_value={"available_memory_mib": 10, "load_per_cpu": 0.1}), \
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
