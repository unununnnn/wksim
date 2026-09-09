"""Finite offline Hex live acceptance regressions; never launch native resources."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import audit_hex_live as live
from validation.test_hex_visual import record, ack
from Simulator.ue55.hex_bridge import packet_from_record, display_packet


class HexLive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.raw = self.directory/'native'
        self.raw.mkdir()
        (self.directory/'frames').mkdir()
        self.expected = live.binding('hex-offline', 'a'*32, live.MODEL)
        self.manifest = dict(binding=self.expected, module_sha256=live.MODULE_SHA, cold_reset_from=None,
                             run_dir=str(self.raw), stack='px4',
                             source_sha256={name:live.digest(ROOT/name) for name in live.SOURCES})
        for name in live.SOURCES:
            target = self.directory/'run-source'/name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((ROOT/name).read_bytes())
        self.write('manifest.json', self.manifest)
        self.write('completion.json', dict(flight_returncode=0, bridge_returncode=0,
                                          owned_processes_exited=True, errors=[],
                                          source_unchanged=True, module_unchanged=True))
        labels = [('armed', .8), ('task_control_ready', .9), ('takeoff_reached', 1.5), ('hold_completed', 2.5),
                  ('waypoint_accepted', 2.6), ('waypoint_completed', 3.5),
                  ('land_accepted', 3.6), ('landed_disarmed_public', 4.5)]
        result = dict(run_id='hex-offline', stack='px4',
                      admission=dict(identities=dict(hex_config=dict(model_identity=live.MODEL))),
                      task=dict(hex=dict(phases=[dict(phase=k, physical_cursor=dict(final_time=v)) for k,v in labels])))
        (self.raw/'result.json').write_text(json.dumps(result))
        self.rows, raws, previous = [], [], None
        for tick in (1000, 2000, 3000, 4000):
            raw = record(tick, tick*1_000_000)
            source = packet_from_record(raw, self.expected, tick*1_000_000+10_000_000)
            packet = display_packet(dict(packet=source, relay_monotonic_s=tick/1000+.01, ended=False),
                                    self.expected, .02, 100+tick/1000)
            actual = ack(packet, previous)
            actual.update(self.expected)
            self.rows.append(dict(packet=packet, ack=actual, errors={'forged': 0}))
            raws.append(raw)
            previous = actual
        start = dict(kind='start', run_id='hex-offline', model_identity=live.MODEL)
        (self.raw/'physics-1ms.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in [start]+raws))
        self.write_rows()
        self.flight = dict(passed=True, root=str(self.raw), checks=dict(result=dict(run_id='hex-offline')),
                           inputs_sha256={name:live.digest(self.raw/name) for name in ('result.json','physics-1ms.jsonl')})
        self.write('flight-audit.json', self.flight)
        (self.directory/'frames/frame-0001.png').write_bytes(b'\x89PNG\r\n\x1a\n'+b'fixture-not-real-render')
        (self.directory/'ue.log').write_text('WKSIM_CAPTURE C:/unused/frame-0001.png sequence=2000 sim=2.000000000 stale=0 rejected=0\n')
        self.addCleanup(patch.stopall)
        patch.object(live, 'windows_raw', side_effect=lambda p: Path(p)).start()

    def write(self, name, value):
        (self.directory/name).write_text(json.dumps(value))

    def write_rows(self):
        (self.directory/'readback.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in self.rows))

    def test_numeric_pass_does_not_claim_rendered_pass(self):
        result = live.audit(self.directory)
        self.assertTrue(result['actor_passed'])
        self.assertFalse(result['passed'])
        self.assertEqual(result['status'], 'render_review_required')
        self.assertEqual(result['phase_ack_counts'], dict(takeoff=1,hold=1,waypoint=1,landing=1))

    def test_autonomous_takeoff_before_20ms_control_ready_tail(self):
        # Actual PX4-03 phase times: the vehicle climbs during SET_CONTROL_MODE.
        # State/ACK values here remain synthetic; only retained timing is reused.
        times = dict(armed=4.24, task_control_ready=13.18, takeoff_reached=13.200000000000001,
                     hold_completed=18.22, waypoint_accepted=18.24, waypoint_completed=22.76,
                     land_accepted=22.78, landed_disarmed_public=30.5)
        path = self.raw/'result.json'
        result = json.loads(path.read_text())
        result['task']['hex']['phases'] = [dict(phase=k,physical_cursor=dict(final_time=v)) for k,v in times.items()]
        path.write_text(json.dumps(result))
        self.rows, raws, previous = [], [], None
        for tick in (9000, 15000, 21000, 30000):
            raw = record(tick, tick*1_000_000)
            source = packet_from_record(raw, self.expected, tick*1_000_000+10_000_000)
            packet = display_packet(dict(packet=source,relay_monotonic_s=tick/1000+.01,ended=False),
                                    self.expected,.02,100+tick/1000)
            actual = ack(packet,previous)
            actual.update(self.expected)
            self.rows.append(dict(packet=packet,ack=actual,errors={}))
            raws.append(raw)
            previous = actual
        start = dict(kind='start',run_id='hex-offline',model_identity=live.MODEL)
        (self.raw/'physics-1ms.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in [start]+raws))
        self.write_rows()
        self.flight['inputs_sha256'] = {name:live.digest(self.raw/name) for name in ('result.json','physics-1ms.jsonl')}
        self.write('flight-audit.json',self.flight)
        (self.directory/'ue.log').write_text('WKSIM_CAPTURE C:/unused/frame-0001.png sequence=15000 sim=15.0 stale=0 rejected=0\n')
        self.assertFalse(any(13.18 <= r['packet']['sim_time_s'] <= 13.20 for r in self.rows))
        self.assertEqual(live.audit(self.directory)['phase_ack_counts']['takeoff'],1)

    def test_explicit_review_is_bound_to_capture_hash(self):
        self.write('review.json', dict(binding=self.expected, reviewer='offline fixture only',
                   six_rotor_structure_visible=True, live_hud_visible=True,
                   captures={'frame-0001.png':live.digest(self.directory/'frames/frame-0001.png')}))
        self.assertTrue(live.audit(self.directory, self.directory/'review.json')['passed'])
        (self.directory/'frames/frame-0001.png').write_bytes(b'\x89PNG\r\n\x1a\nchanged')
        with self.assertRaisesRegex(ValueError, 'capture hash'):
            live.audit(self.directory, self.directory/'review.json')

    def test_empty_ack_fails_even_after_successful_bridge(self):
        self.rows = []
        self.write_rows()
        with self.assertRaisesRegex(ValueError, 'Empty Actor'):
            live.audit(self.directory)

    def test_foreign_binding_and_stale_packet_fail(self):
        for key, value in [('run_id','foreign'),('transport_age_bound_s',.76),('rotor_rpm',[0]*5)]:
            before = copy.deepcopy(self.rows)
            self.rows[0]['packet'][key] = value
            self.write_rows()
            with self.subTest(key=key), self.assertRaises(ValueError):
                live.audit(self.directory)
            self.rows = before

    def test_overbudget_ack_is_recomputed_not_trusted(self):
        self.rows[0]['ack']['ue_position_cm'][0] += .001
        self.write_rows()
        with self.assertRaisesRegex(ValueError, 'position_cm'):
            live.audit(self.directory)

    def test_missing_phase_continuity_fails(self):
        self.rows[1]['ack']['previous_step'] = 1500
        self.write_rows()
        with self.assertRaisesRegex(ValueError, 'phase continuity'):
            live.audit(self.directory)

    def test_packet_raw_mismatch_fails_even_with_correct_actor(self):
        self.rows[1]['packet']['source_monotonic_s'] += .001
        self.write_rows()
        with self.assertRaisesRegex(ValueError, 'actual raw tick'):
            live.audit(self.directory)

    def test_missing_phase_coverage_fails(self):
        self.rows.pop()
        self.write_rows()
        with self.assertRaisesRegex(ValueError, 'during landing'):
            live.audit(self.directory)

    def test_no_fresh_render_capture_fails(self):
        (self.directory/'ue.log').write_text('WKSIM_CAPTURE C:/unused/frame-0001.png sequence=2000 sim=2.0 stale=1 rejected=0\n')
        with self.assertRaisesRegex(ValueError, 'No fresh capture'):
            live.audit(self.directory)

    def test_changed_raw_after_physical_audit_fails(self):
        with (self.raw/'physics-1ms.jsonl').open('a') as stream:
            stream.write('\n')
        with self.assertRaisesRegex(ValueError, 'Raw changed'):
            live.audit(self.directory)

    def test_changed_archived_verifier_fails(self):
        (self.directory/'run-source/tools/check_hex_view.py').write_text('LIMITS = {}')
        with self.assertRaisesRegex(ValueError, 'Archived live source changed'):
            live.audit(self.directory)

    def test_changed_native_log_after_physical_audit_fails(self):
        path = self.raw/'fc.log'
        path.write_text('original')
        self.flight['inputs_sha256']['fc.log'] = live.digest(path)
        self.write('flight-audit.json',self.flight)
        path.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'Flight audit input changed: fc.log'):
            live.audit(self.directory)

    def test_readiness_failure_prevents_next_launch(self):
        child = MagicMock()
        child.poll.return_value = 9
        flight_launch = MagicMock()
        with self.assertRaisesRegex(ValueError, 'before readiness'):
            live.wait_ready(child, lambda: False, .1, 'UE')
            flight_launch()
        flight_launch.assert_not_called()

    def test_readiness_timeout_is_bounded(self):
        child = MagicMock()
        child.poll.return_value = None
        with patch.object(live.time, 'monotonic', side_effect=[0, 1]), self.assertRaises(TimeoutError):
            live.wait_ready(child, lambda: False, .5, 'Bridge')

    def test_exclusive_report_save_never_overwrites(self):
        path = self.directory/'flight-audit.json'
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            live.save(path, {'command_metadata': True})
        self.assertEqual(path.read_bytes(), before)

    def test_coordinator_readiness_failure_does_not_launch_flight(self):
        from argparse import Namespace
        # Exercise actual coordinator ordering with all external operations mocked.
        # Known candidate files are harmless placeholders whose digest is stubbed.
        stage = self.directory/'stage'
        stage.mkdir()
        (stage/'WksimVisual.uproject').touch()
        engine = self.directory/'engine'
        engine.touch()
        runner = self.directory/'runner.sh'
        runner.touch()
        target = self.directory/'fresh'
        args = Namespace(run_id='hex-ordering', output=target,
            output_root='/root/wksim-hex-flight-offline', stage=str(stage), engine=str(engine),
            audit_runner=runner, stack='px4', cold_reset_from=None)
        child = MagicMock()
        child.pid = 12345
        child.poll.return_value = 12
        preflight = MagicMock(returncode=0, stderr=b'', stdout=json.dumps(dict(ok=True,
            identities=dict(hex_config=dict(model_identity=live.MODEL)))).encode())
        with patch.object(live.os, 'name', 'nt'), \
             patch.object(live, 'digest', return_value=live.MODULE_SHA), \
             patch.object(live, 'wsl_path', side_effect=str), \
             patch.object(live, 'hidden_startup', return_value=None), \
             patch.object(live.subprocess, 'run', return_value=preflight), \
             patch.object(live.subprocess, 'Popen', return_value=child) as popen:
            with self.assertRaisesRegex(ValueError, 'Live run incomplete'):
                live.coordinate(args)
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(popen.call_args.args[0][0], str(engine))
        self.assertFalse((target/'flight-owner.json').exists())


if __name__ == '__main__':
    unittest.main()
