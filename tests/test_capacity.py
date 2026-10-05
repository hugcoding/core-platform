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


class CpuAdmissionTests(unittest.TestCase):
    def test_short_spike_is_ignored_and_five_of_six_pauses(self):
        policy=capacity.CpuAdmission(60,50)
        for tick,value in enumerate([20,20,90,20,20,20]):
            self.assertFalse(policy.update(value,tick*5)['paused'])
        policy=capacity.CpuAdmission(60,50)
        for tick,value in enumerate([90,90,40,90,90]):
            self.assertFalse(policy.update(value,tick*5)['paused'])
        self.assertTrue(policy.update(90,25)['paused'])

    def test_hysteresis_requires_continuous_low_and_ignores_middle_band(self):
        policy=capacity.CpuAdmission(60,50)
        for tick in range(6):policy.update(90,tick*5)
        for tick in range(30,60,5):self.assertTrue(policy.update(40,tick)['paused'])
        self.assertTrue(policy.update(55,60)['paused'])
        for tick in range(65,95,5):self.assertTrue(policy.update(40,tick)['paused'])
        self.assertFalse(policy.update(40,95)['paused'])
        self.assertFalse(policy.update(90,100)['paused'])

    def test_missing_samples_do_not_count_as_low_or_high(self):
        policy=capacity.CpuAdmission(60,50)
        for tick in range(6):policy.update(90,tick*5)
        policy.update(40,30)
        self.assertTrue(policy.update(40,70)['paused'])
        for tick in range(75,100,5):self.assertTrue(policy.update(40,tick)['paused'])
        self.assertFalse(policy.update(40,100)['paused'])

    def test_configurable_profiles_and_invalid_settings(self):
        with mock.patch.dict(capacity.os.environ,{'CORE_FINANCE_MAX_CPU_PERCENT':'65','CORE_FINANCE_CPU_RESUME_PERCENT':'45','CORE_CPU_WINDOW_SAMPLES':'4','CORE_CPU_HIGH_SAMPLES':'3','CORE_CPU_RESUME_SECONDS':'20'}):
            policy=capacity.cpu_policies()['finance']
            self.assertEqual((65,45,4,3,20),(policy.limit,policy.resume,policy.window,policy.high,policy.resume_seconds))
        for args in [(60,60),(60,70),(101,50),(60,50,6,7),(60,50,6,5,0)]:
            with self.assertRaises(ValueError):capacity.CpuAdmission(*args)

    def test_workers_use_central_state_even_when_instantaneous_cpu_disagrees(self):
        import finance_worker,controlled_execution_worker,workset_ai_worker
        state={name:dict(paused=False) for name in ('finance','ai','ocr','execution')}
        resources=dict(capacity_available=1,cpu_load_percent=90,available_memory_mib=99999,cpu_admission=state)
        self.assertIsNone(controlled_execution_worker.resource_block(resources,0))
        self.assertIsNone(workset_ai_worker.resource_gate(resources,0))
        with mock.patch.object(finance_worker,'host_resources',return_value=resources),mock.patch.object(finance_worker,'stream_lag',return_value=0):
            conn=mock.MagicMock();conn.cursor.return_value.__enter__.return_value.fetchone.return_value={'busy':False,'sessions':0}
            self.assertIsNone(finance_worker.gate(conn,mock.Mock()))
            resources['cpu_load_percent']=20;state['finance']['paused']=True
            self.assertEqual('waiting_for_cpu',finance_worker.gate(conn,mock.Mock()))
        state['execution']['paused']=True;state['ai']['paused']=True
        self.assertEqual('waiting_for_cpu',controlled_execution_worker.resource_block(resources,0))
        self.assertEqual('waiting_for_cpu',workset_ai_worker.resource_gate(resources,0))

    def test_bad_central_state_is_rejected(self):
        value=CapacityTests().snapshot(cpu_admission={'finance':{'paused':'false'}})
        with self.assertRaises(capacity.CapacityUnavailable):
            capacity.read_snapshot(mock.Mock(get=mock.Mock(return_value=json.dumps(value))),now=100)

    def test_ocr_obeys_same_central_pause_without_claiming(self):
        import workset_ocr_worker as worker
        for paused,cpu in [(True,20),(False,90)]:
            resources=dict(capacity_available=1,cpu_load_percent=cpu,available_memory_mib=99999,
                           cpu_admission={'ocr':{'paused':paused}})
            with mock.patch.object(worker.redis,'Redis',return_value=mock.Mock()), \
                 mock.patch.object(worker,'service_gate',return_value=None), \
                 mock.patch.object(worker,'host_resources',return_value=resources), \
                 mock.patch.object(worker,'stream_lag',return_value=0), \
                 mock.patch.object(worker,'set_waiting_reason') as waiting, \
                 mock.patch.object(worker,'claim_job',return_value=None) as claim, \
                 mock.patch.object(worker,'discover_ocr_near_duplicates'), \
                 mock.patch.object(worker.time,'sleep',side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):worker.main()
            waiting.assert_called_once_with('waiting_for_cpu' if paused else None)
            self.assertEqual(0 if paused else 1,claim.call_count)

    def test_exact_thresholds_do_not_count_as_high_or_low(self):
        policy=capacity.CpuAdmission(60,50)
        for tick in range(6):self.assertFalse(policy.update(60,tick*5)['paused'])
        for tick in range(30,60,5):policy.update(90,tick)
        for tick in range(60,100,5):self.assertTrue(policy.update(50,tick)['paused'])
