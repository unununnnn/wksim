"""Offline replay behavior: identity, clock honesty, raw sample order and bad input."""
import json
from pathlib import Path
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
