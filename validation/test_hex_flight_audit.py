"""Adversarial #65 tests. Real-run tests read PX4-03 without altering originals.

Set WK_HEX_AUDIT_RUN to another retained PX4-03 copy if necessary. All temporary
mutations are test artifacts, not new flights; only test_real_px4 audits a flight.
"""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import audit_hex_flight as audit
from validation.test_hex_physics_evidence import _px4_case, _ap_case, _write_case

REAL = Path(os.environ.get('WK_HEX_AUDIT_RUN', '/root/wksim-hex-flight-px4-03/hex-px4-03'))


class PureGuards(unittest.TestCase):
    def test_legacy_compatibility_requires_both_exact_pins_and_px4(self):
        for name, pairs in audit.LEGACY_PX4_SOURCE_PAIRS.items():
            for old, reviewed in pairs:
                with self.subTest(name=name, old=old, reviewed=reviewed):
                    self.assertTrue(audit.compatible_source('px4', name, old, reviewed))
                    self.assertFalse(audit.compatible_source('px4', name, old, 'f'*64))
                    self.assertFalse(audit.compatible_source('px4', name, 'f'*64, reviewed))
                    self.assertFalse(audit.compatible_source('arducopter', name, old, reviewed))
                    self.assertTrue(audit.compatible_source('arducopter', name, reviewed, reviewed))

    def test_duplicate_keys_and_nonfinite_rejected(self):
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                audit.parse(raw)

    def test_truncated_jsonl(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'rows.jsonl'
            p.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'Incomplete JSONL'):
                list(audit.lines(p))

    def test_wrong_channel_foundation(self):
        for factory in (_px4_case, _ap_case):
            rows = factory()
            r = next(r for r in reversed(rows) if r['kind'] == 'step')
            r['input16'][4], r['input16'][5] = r['input16'][5], r['input16'][4]
            with tempfile.TemporaryDirectory() as d:
                value = audit.core.check(_write_case(Path(d), rows))
                self.assertFalse(value['passed'])
                self.assertIn('input_mismatch', [e['code'] for e in value['errors']])

    def test_false_observed_cannot_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'result.json').write_text(json.dumps(dict(status='observed', model_profile='hex_x',
                run_id='fake', safe_landing=True, children_reaped=True, cleanup_errors=[],
                processes_absent_after_stop=True)))
            report = audit.check(root)
            self.assertFalse(report['passed'])
            self.assertGreaterEqual(len(report['errors']), 3)

    def test_empty_input_cannot_pass(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(audit.check(Path(d))['passed'])

    def test_static_fixture_cannot_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root = _write_case(Path(d), _px4_case())
            self.assertTrue(audit.core.check(root)['passed'])
            (root/'result.json').write_text('{"status":"observed","run_id":"hex-px4-03"}')
            self.assertFalse(audit.check(root)['passed'])

    def test_output_inside_original_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d)/'audit.json'
            with patch('sys.argv', ['audit', '--run-dir', d, '--output', str(target)]):
                with self.assertRaisesRegex(ValueError, 'outside original'):
                    audit.main()
            self.assertFalse(target.exists())

    def test_existing_output_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)/'run'; root.mkdir()
            target = Path(d)/'audit.json'; target.write_text('keep')
            with patch('sys.argv', ['audit', '--run-dir', str(root), '--output', str(target)]):
                with self.assertRaises(ValueError):
                    audit.main()
            self.assertEqual(target.read_text(), 'keep')


@unittest.skipUnless(REAL.is_dir(), 'Retained PX4-03 requires WSL; synthetic data is not substituted')
class RealEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = audit.read(REAL/'result.json')
        cls.raw = list(audit.lines(REAL/'physics-1ms.jsonl'))
        cls.steps = [r for r in cls.raw if r['kind'] == 'step']
        cls.trace = list(audit.lines(REAL/'truth.jsonl'))
        cls.native_rows = list(audit.lines(REAL/'hex-native.jsonl'))
        _, cls.data, cls.messages, cls.rows, cls.services = audit.decode(REAL, cls.result)
        _, cls.phases = audit.phases_and_public(cls.result, cls.trace, cls.data)

    def test_real_px4(self):
        value = audit.check(REAL)
        self.assertTrue(value['passed'], value['errors'])
        self.assertEqual(value['checks']['physics']['counts']['step'], 30924)
        self.assertEqual(value['checks']['native_parameters']['count'], 77)
        self.assertEqual(value['checks']['cold_reset']['status'], 'not_present')
        self.assertTrue(value['checks']['immutability']['passed'])

    def test_cold_reset_required_is_not_implied(self):
        value = audit.check(REAL, require_cold_reset=True)
        self.assertFalse(value['passed'])
        self.assertIn('cold_reset', [e['check'] for e in value['errors']])

    def test_missing_step(self):
        rows = [r for r in self.raw if not (r['kind'] == 'step' and r['tick'] == 14001)]
        with tempfile.TemporaryDirectory() as d:
            root = _write_case(Path(d), rows)
            value = audit.core.check(root)
            self.assertFalse(value['passed'])
            self.assertIn('tick_discontinuity', [e['code'] for e in value['errors']])

    def test_missing_terminal(self):
        with tempfile.TemporaryDirectory() as d:
            value = audit.core.check(_write_case(Path(d), self.raw[:-1]))
            self.assertFalse(value['passed'])
            self.assertIn('terminal_count', [e['code'] for e in value['errors']])

    def test_changed_model_binding(self):
        rows = self.raw.copy(); rows[0] = dict(rows[0], model_identity='sha256:'+'0'*64)
        with tempfile.TemporaryDirectory() as d:
            value = audit.core.check(_write_case(Path(d), rows), expected_model_identity=audit.MODEL_IDENTITY)
            self.assertFalse(value['passed'])

    def test_unsampled_one_ms_violation(self):
        steps = self.steps.copy()
        steps[14000] = copy.deepcopy(steps[14000])
        steps[14000]['output120'][8] = -4.
        report = audit.gates(self.result, steps, self.phases, self.data)
        self.assertEqual(report['hold']['violation_ticks'], [14001])
        self.assertFalse(report['hold']['passed'])

    def test_landing_to_terminal_violation(self):
        steps = self.steps.copy(); steps[-1] = copy.deepcopy(steps[-1]); steps[-1]['output120'][8] = -.3
        report = audit.gates(self.result, steps, self.phases, self.data)
        self.assertFalse(report['landing_to_terminal']['passed'])

    def test_short_dwell_rejected(self):
        phases = copy.deepcopy(self.phases)
        phases['hold_completed']['physical_cursor']['final_time'] = 18.18
        with self.assertRaisesRegex(ValueError, 'incomplete model/native dwell'):
            audit.gates(self.result, self.steps, phases, self.data)

    def test_wrong_phase_cursor(self):
        r = copy.deepcopy(self.result)
        r['task']['hex']['phases'][-1]['physical_cursor']['records'] -= 1
        with self.assertRaisesRegex(ValueError, 'cursor'):
            audit.phases_and_public(r, self.trace, self.data)

    def test_missing_public_request(self):
        data = self.data.copy(); data[audit.PUBLIC+'v2/command'] = []
        with self.assertRaisesRegex(ValueError, 'request chain'):
            audit.phases_and_public(self.result, self.trace, data)

    def test_native_wrong_channel_target(self):
        data = self.data.copy()
        topic = next(t for t in data if '/in/trajectory_setpoint' in t)
        data[topic] = [(r, dict(v, position=[2., 3., -3.])) for r, v in data[topic]]
        with self.assertRaisesRegex(ValueError, 'position target/axes'):
            audit.native_delivery(REAL, self.result, data, self.messages, self.phases)

    def test_missing_parameter(self):
        rows = [r for r in self.rows if not (r['kind'] == 'parameter_request_read_tx' and r['name'] == 'CA_ROTOR_COUNT')]
        with self.assertRaisesRegex(ValueError, 'parameter requests'):
            audit.parameters(self.result, rows, self.messages, self.services, self.phases, self.trace)

    def test_forged_parameter_payload(self):
        messages = copy.deepcopy(self.messages)
        for r in messages:
            if r['message']['mavpackettype'] == 'PARAM_VALUE' and r['message']['param_id'] == 'CA_ROTOR_COUNT':
                r['payload_hex'] = '04000000'+r['payload_hex'][8:]
        with self.assertRaisesRegex(ValueError, 'Parameter value differs'):
            audit.parameters(self.result, self.rows, messages, self.services, self.phases, self.trace)

    def test_deleted_datagram(self):
        rows = self.native_rows.copy()
        idx = next(i for i, r in enumerate(rows) if r['kind'] == 'mavlink_rx' and r['monotonic'] > 70)
        del rows[idx]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'hex-native.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            with self.assertRaisesRegex(ValueError, 'count differs'):
                audit.decode(root, self.result)

    def test_fake_publisher_gid(self):
        rows = self.native_rows.copy()
        idx = next(i for i, r in enumerate(rows) if r['kind'] == 'dds')
        rows[idx] = dict(rows[idx], publisher_gid='fake')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'hex-native.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            with self.assertRaisesRegex(ValueError, 'Fabricated DDS'):
                audit.decode(root, self.result)

    def test_cold_reset_link_guards(self):
        parent = self.result
        child = copy.deepcopy(parent)
        child.update(run_id='synthetic-new', run_dir='/synthetic-new')
        child['task']['control_epoch'] = 'synthetic-new'
        child['supervisor']['pid'] += 100000
        child['cold_reset_from'] = dict(sha256='a'*64, run_id=parent['run_id'], children=parent['children'],
            control_epoch=parent['task']['control_epoch'], configuration_identity=parent['admission']['configuration_identity'])
        for c in child['children'].values():
            c['pid'] += 100000; c['identity']['pid'] = c['pid']; c['cwd'] = '/synthetic-new'
        # This passes only metadata guards, never the recursive flight audit.
        audit.reset_links(child, parent, 'a'*64)
        for kind in ('hash', 'run', 'epoch', 'tick', 'process', 'config', 'storage'):
            bad = copy.deepcopy(child)
            if kind == 'hash': bad['cold_reset_from']['sha256'] = 'b'*64
            if kind == 'run': bad['run_id'] = parent['run_id']
            if kind == 'epoch': bad['task']['control_epoch'] = parent['task']['control_epoch']
            if kind == 'tick': bad['model_initialization']['initial_tick'] = 1
            if kind == 'process': bad['children']['fc'] = parent['children']['fc']
            if kind == 'config': bad['admission']['configuration_identity'] = 'wrong'
            if kind == 'storage': bad['run_dir'] = parent['run_dir']
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                audit.reset_links(bad, parent, 'a'*64)

    def test_legacy_recipe_rejects_unreviewed_current_source(self):
        actual_digest = audit.digest
        target = audit.REPO/'tools/hex_launch_plan.py'
        with patch.object(audit, 'digest', side_effect=lambda p: 'f'*64 if Path(p) == target else actual_digest(p)):
            with self.assertRaisesRegex(ValueError, 'Shared decoding/identity recipe changed: tools/hex_launch_plan.py'):
                audit.identity(REAL, self.result)

    def test_live_process_is_not_retired(self):
        pid = os.getpid(); text = Path(f'/proc/{pid}/stat').read_text()
        identity = dict(pid=pid, boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            starttime_ticks=int(text[text.rfind(')')+2:].split()[19]), argv=['unittest'], cwd=str(Path.cwd()))
        self.assertFalse(audit.process_absent(identity))


if __name__ == '__main__':
    unittest.main()
