"""Synthetic host counters and Redis snapshots; no financial data or live services."""
import json
import unittest
from unittest import mock

from core.runtime import capacity


class CapacityTests(unittest.TestCase):
    def snapshot(self, **changes):
        return dict(version=1, sampled_at=100, cpu_percent=25, memory_total=1000,
                    memory_available=600, memory_used=400, memory_estimated=False,
                    load_1m=5, **changes)

    def test_cpu_is_counter_delta_not_load_average(self):
        before = capacity.cpu_counters('cpu 100 0 100 700 100 0 0 0 50 0')
        after = capacity.cpu_counters('cpu 125 0 100 750 125 0 0 0 75 0')
        self.assertEqual(25, capacity.cpu_percent(before, after))
        self.assertEqual((1000, 200), before)  # guest excluded, I/O wait not busy

    def test_invalid_or_reset_counters_are_rejected(self):
        for before, after in [((100, 20), (100, 20)), ((100, 20), (90, 10)),
                              ((100, 20), (110, 40)), ((100, 20), (110, 10))]:
            with self.assertRaises(ValueError):
                capacity.cpu_percent(before, after)

    def test_memory_preserves_pulse_cache_correction(self):
        cases = [
            ('MemTotal: 1000 kB\nMemAvailable: 600 kB', 400, False),
            ('MemTotal: 1000 kB\nMemAvailable: 0 kB', 1000, False),
            ('MemTotal: 1000 kB\nMemFree: 100 kB\nBuffers: 50 kB\nCached: 400 kB\nSReclaimable: 100 kB\nShmem: 50 kB', 400, True),
            ('MemTotal: 1000 kB\nMemFree: 100 kB\nCached: 2000 kB', 0, True),
            ('MemTotal: 1000 kB\nMemFree: 100 kB\nShmem: 200 kB', 900, True),
        ]
        for text, used, estimated in cases:
            result = capacity.memory_metrics(text)
            self.assertEqual(used*1024, result['memory_used'])
            self.assertEqual(estimated, result['memory_estimated'])

    def test_missing_invalid_stale_and_future_snapshots_fail_closed(self):
        valid = self.snapshot()
        cases = [None, '{', 'null'] + [json.dumps({**valid, **change}) for change in
            ({'sampled_at': 79}, {'sampled_at': 101}, {'cpu_percent': 127},
             {'cpu_percent': True}, {'memory_available': 1001}, {'memory_used': 1},
             {'version': 2}, {'cpu_percent': float('nan')})]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(capacity.CapacityUnavailable):
                capacity.read_snapshot(mock.Mock(get=mock.Mock(return_value=value)), now=100)
        with self.assertRaises(capacity.CapacityUnavailable):
            capacity.read_snapshot(mock.Mock(get=mock.Mock(side_effect=OSError('offline'))))

    def test_consumer_uses_snapshot_without_resampling(self):
        connection = mock.Mock(get=mock.Mock(return_value=json.dumps(self.snapshot())))
        value = capacity.read_snapshot(connection, now=110)
        with mock.patch.object(capacity, 'read_snapshot', return_value=value), \
             mock.patch.object(capacity.Path, 'read_text', side_effect=AssertionError('local read')):
            result = capacity.worker_resources()
        self.assertEqual(25, result['cpu_load_percent'])
        self.assertEqual(100, result['sampled_at'])
        with mock.patch.object(capacity, 'read_snapshot', side_effect=capacity.CapacityUnavailable):
            self.assertEqual({'capacity_available': 0}, capacity.worker_resources())

    def test_collector_warms_up_publishes_and_expires(self):
        connection = mock.Mock()
        with mock.patch.object(capacity, 'client', return_value=connection), \
             mock.patch.object(capacity.Path, 'read_text', side_effect=[
                 'cpu 100 0 100 700 100 0 0 0', 'cpu 125 0 100 750 125 0 0 0',
                 'MemTotal: 1000 kB\nMemAvailable: 600 kB', '5.0 4.0 3.0']), \
             mock.patch.object(capacity.time, 'monotonic', side_effect=[1, 6]), \
             mock.patch.object(capacity.time, 'sleep', side_effect=[None, KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt):
                capacity.main()
        connection.delete.assert_called_once_with(capacity.KEY)
        call = connection.set.call_args_list[0]
        self.assertEqual(capacity.KEY, call.args[0])
        self.assertEqual(20, call.kwargs['ex'])
        self.assertEqual(25, json.loads(call.args[1])['cpu_percent'])

    def test_workers_wait_for_missing_capacity(self):
        import finance_worker
        import controlled_execution_worker
        import workset_ai_worker
        self.assertEqual('capacity_unavailable', controlled_execution_worker.resource_block(
            {'capacity_available': 0}, 0))
        self.assertEqual('capacity_unavailable', workset_ai_worker.resource_gate(
            {'capacity_available': 0}, 0))
        with mock.patch.object(finance_worker, 'host_resources', return_value={'capacity_available': 0}):
            self.assertEqual('capacity_unavailable', finance_worker.gate(mock.Mock(), mock.Mock()))

    def test_ocr_does_not_claim_work_without_snapshot(self):
        import workset_ocr_worker as worker
        with mock.patch.object(worker.redis, 'Redis', return_value=mock.Mock()), \
             mock.patch.object(worker, 'service_gate', return_value=None), \
             mock.patch.object(worker, 'host_resources', return_value={'capacity_available': 0}), \
             mock.patch.object(worker, 'set_waiting_reason') as waiting, \
             mock.patch.object(worker, 'claim_job') as claim, \
             mock.patch.object(worker.time, 'sleep', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                worker.main()
        waiting.assert_called_once_with('capacity_unavailable')
        claim.assert_not_called()
