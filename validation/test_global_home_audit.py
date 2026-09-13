"""Mutate a retained complete home-change flight; no simulator is started."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.audit_global_flight import audit
from validation import test_global_audit as base_tests


@unittest.skipUnless(os.environ.get('WKSIM_GLOBAL_AUDIT_ROOT'), 'Explicit retained v2 flight required')
class GlobalHomeAuditTests(unittest.TestCase):
    clone = base_tests.GlobalAuditTests.clone

    def test_px4_requires_configured_origin_not_a_noisy_gps_sample(self):
        source = Path(os.environ['WKSIM_GLOBAL_AUDIT_ROOT'])
        if json.loads((source/'result.json').read_text())['stack'] != 'px4':
            self.skipTest('AP truth origin is independently bound by its native --home input')
        with tempfile.TemporaryDirectory() as directory:
            root = self.clone(directory, 'datum-model-origin.json')
            (root/'datum-model-origin.json').unlink()
            with self.assertRaisesRegex(ValueError, 'Configured model origin evidence missing'): audit(root)

    def test_operator_command_missing_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.clone(directory, 'home-operator-wire.jsonl')
            path = root/'home-operator-wire.jsonl'
            lines = path.read_text().splitlines()
            path.write_text('\n'.join(line for line in lines if json.loads(line)['direction'] != 'out')+'\n')
            with self.assertRaisesRegex(ValueError, 'single native home request/ACK'): audit(root)

    def test_setpoint_replay_inside_quiet_window_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.clone(directory, 'rc-dds.jsonl')
            path = root/'rc-dds.jsonl'
            records = [json.loads(line) for line in path.read_text().splitlines()]
            revoked = []
            for row in records:
                if row['topic'].endswith('/text_info'):
                    event = json.loads(row['message']['message'])
                    if event['event'] == 'control_revoked' and event.get('reason') == 'global_home_changed':
                        revoked.append(event)
            self.assertTrue(revoked)
            packet = next(dict(r) for r in records if '/in/trajectory_setpoint' in r['topic'] or r['topic'] == '/ap/cmd_gps_pose')
            packet['source_timestamp'] = revoked[0]['emitted_unix_ns']+500_000_000
            packet['monotonic_ns'] = revoked[0]['emitted_monotonic_ns']+500_000_000
            with path.open('a') as stream: stream.write(json.dumps(packet)+'\n')
            with self.assertRaisesRegex(ValueError, 'setpoint replay'): audit(root)

    def test_missing_new_takeover_request_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.clone(directory, 'rc-dds.jsonl')
            path = root/'rc-dds.jsonl'
            records = [json.loads(line) for line in path.read_text().splitlines()]
            takeovers = [r['message']['request_id'] for r in records if r['topic'].endswith('/v2/setup')
                         and r['message']['setup']['control_state'] == 'COMMAND_CONTROL']
            self.assertGreaterEqual(len(takeovers), 2)
            records = [r for r in records if not (r['topic'].endswith('/v2/setup') and r['message']['request_id'] == max(takeovers))]
            path.write_text(''.join(json.dumps(r)+'\n' for r in records))
            with self.assertRaisesRegex(ValueError, 'raw explicit takeover'): audit(root)


if __name__ == '__main__': unittest.main()
