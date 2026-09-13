"""Offline replay behavior: identity, clock honesty, raw sample order and bad input."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from Simulator.wksim_runtime.replay import load_evidence, main, select_records


class ReplayTest(unittest.TestCase):
    def test_recorded_order_unknown_epoch_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'result.json').write_text('{"stack":"px4","status":"pass"}')
            original = ('{"time":1.0,"sequence":1,"vehicle":[NaN]}\n'
                        '{"time":2.0,"sequence":3,"vehicle":[1]}\n'
                        '{"time":')
            (root / 'truth.jsonl').write_text(original)
            (root / 'prometheus.jsonl').write_text(json.dumps({'topic': '/uav1/prometheus/state', 'message': {
                'header': {'stamp': {'sec': 7, 'nanosec': 500000000}}, 'connected': False}}) + '\n')
            with patch('socket.socket', side_effect=AssertionError('offline reader opened network')), \
                    patch('subprocess.Popen', side_effect=AssertionError('offline reader created a process')):
                evidence = load_evidence(root)
            self.assertIsNone(evidence['epoch'])
            self.assertEqual([r['source_time_s'] for r in evidence['records']], [7.5, 1.0, 2.0])
            truth = list(select_records(evidence, clock='physics', start=1, end=2))
            self.assertEqual([r['raw_json'] for r in truth],
                             (root / 'truth.jsonl').read_bytes().decode('utf-8').splitlines(keepends=True)[:2])
            codes = {d['code'] for d in evidence['diagnostics']}
            self.assertTrue({'nonfinite_values', 'sequence_discontinuity', 'malformed_record',
                             'unterminated_last_line', 'missing_file', 'unknown_run_identity'} <= codes)
            self.assertTrue(evidence['records'][0]['recorded_invalid'])
            self.assertEqual(truth[0]['payload']['vehicle'], [{'nonfinite': 'NaN'}])
            json.dumps(evidence, allow_nan=False)
            with self.assertRaisesRegex(ValueError, 'explicit --clock'):
                list(select_records(evidence, start=0))
            self.assertEqual((root / 'truth.jsonl').read_text(), original)
            self.assertEqual(main([directory, '--output', str(root / 'result.json')]), 2)

    def test_nonfinite_results_and_rows_export_without_changing_raw(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as output:
            root = Path(directory)
            result = b'{"run_id":"run-A","epoch":1,"stack":NaN,"status":1e999}'
            raw = b'{"time":1e999,"vehicle":[-1e999,Infinity,NaN]}\n'
            (root / 'result.json').write_bytes(result)
            (root / 'truth.jsonl').write_bytes(raw)
            evidence = load_evidence(root)
            row = evidence['records'][0]
            self.assertEqual(row['payload']['time'], {'nonfinite': '1e999'})
            self.assertEqual(evidence['recorded_run_status'], {'nonfinite': '1e999'})
            self.assertEqual(row['raw_json'], raw.decode())
            self.assertEqual(row['raw_sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(evidence['files']['result.json']['sha256'], hashlib.sha256(result).hexdigest())
            self.assertTrue(any(d.get('file') == 'result.json' and d['code'] == 'nonfinite_values'
                                for d in evidence['diagnostics']))
            self.assertEqual(main([directory, '--output', str(Path(output) / 'replay.json')]), 0)
            self.assertEqual((root / 'truth.jsonl').read_bytes(), raw)
            self.assertEqual((root / 'result.json').read_bytes(), result)

    def test_huge_integer_timestamps_remain_raw_without_clock_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'result.json').write_text('{"run_id":"A","epoch":1}')
            huge = 10**400
            rows = [{'time': huge}, {'message': {'header': {'stamp': {'sec': huge, 'nanosec': 0}}}},
                    {'message': {'header': {'stamp': {'sec': sys.float_info.max,
                                                    'nanosec': sys.float_info.max}}}}]
            (root / 'truth.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
            evidence = load_evidence(root)
            self.assertEqual([r['clock'] for r in evidence['records']], ['unknown'] * 3)
            self.assertEqual([r['source_time_s'] for r in evidence['records']], [None] * 3)
            self.assertEqual([r['payload'] for r in evidence['records']], rows)
            json.dumps(evidence, allow_nan=False)

    def test_duplicate_keys_are_rejected_in_result_and_nested_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'result.json').write_text('{"run_id":"A","run_id":"B","epoch":1}')
            (root / 'truth.jsonl').write_text('{"message":{"epoch":1,"epoch":2}}\n')
            evidence = load_evidence(root)
            self.assertIsNone(evidence['run_id'])
            self.assertEqual(evidence['records'], [])
            self.assertEqual(evidence['reader_status'], 'partial')
            self.assertTrue({'invalid_result', 'malformed_record'} <=
                            {d['code'] for d in evidence['diagnostics']})

    def test_explicit_record_identity_is_not_overwritten_by_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'result.json').write_text('{"run_id":"A","epoch":1}')
            for stream in ('prometheus', 'dds', 'telemetry'):
                (root / (stream + '.jsonl')).write_text('')
            rows = [{'run_id': 'B', 'epoch': 2}, {'message': {'run_id': 'C', 'epoch': 3}},
                    {'run_id': 'A', 'message': {'run_id': 'B'}}, {'time': 1}]
            (root / 'truth.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
            evidence = load_evidence(root)
            self.assertEqual([r['run_id'] for r in evidence['records']], ['B', 'C', None, 'A'])
            self.assertEqual([r['epoch'] for r in evidence['records']], [2, 3, 1, 1])
            self.assertEqual(evidence['reader_status'], 'partial')
            self.assertEqual(sum(d['code'] == 'identity_mismatch' for d in evidence['diagnostics']), 3)

    def test_public_command_and_ack_are_not_action_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'result.json').write_text('{"run_id":"run-A","epoch":2}')
            rows = [{'published': 'UAVCommand', 'message': {'header': {'stamp': {'sec': 1000, 'nanosec': 0}}}},
                    {'topic': '/uav1/prometheus/text_info', 'message': {'message': '{"event":"command_accepted"}'}}]
            (root / 'prometheus.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
            evidence = load_evidence(root)
            self.assertEqual([r['kind'] for r in evidence['records']], ['command', 'command_accepted'])
            self.assertEqual(evidence['records'][0]['clock'], 'ros')
            self.assertEqual(evidence['records'][1]['clock'], 'unknown')
            self.assertEqual(evidence['epoch'], 2)


if __name__ == '__main__':
    unittest.main()
