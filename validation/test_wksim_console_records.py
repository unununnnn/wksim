"""Console evidence projection without FC, UE, ROS or writes to the input run."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from Simulator.wksim_console import records


def session(sequence=1, received=900000.0, boot=10, **changes):
    message = dict(version=1, run_id='run-a', control_epoch='a' * 32,
                   sequence=sequence, source_clock='fc_boot', source_received_valid=True,
                   source_received_monotonic_s=received, published_monotonic_s=received + .25,
                   state=dict(uav_id=1, connected=True, odom_valid=True, armed=False,
                              header={'frame_id': 'map', 'stamp': {'sec': boot, 'nanosec': 0}},
                              position=[0, 0, 0], velocity=[0, 0, 0], attitude=[0, 0, 0]),
                   control=dict(uav_id=1, control_state=0, failsafe=False),
                   future_field={'unrecognized': [1, 'retained']})
    message.update(changes)
    return {'wall': 12345, 'topic': records.SESSION_TOPIC, 'message': message}


class LiveRecordsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 12.0
        self.clock = patch.object(records.time, 'monotonic', side_effect=lambda: self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.reader = records.LiveRunReader(self.root, 'run-a')

    def append(self, row, stream='prometheus'):
        with (self.root / (stream + '.jsonl')).open('a', encoding='utf-8') as out:
            out.write(json.dumps(row) + '\n')

    def codes(self, result):
        return {row['code'] for row in result['diagnostics']}

    def establish(self):
        self.append(session())
        self.assertEqual(self.reader.poll()['freshness']['status'], 'waiting')
        self.now += .5
        self.append(session(2, 900001, 11))
        self.assertEqual(self.reader.poll()['freshness']['status'], 'live')

    def test_cross_host_dates_and_first_batch_are_not_live(self):
        self.append(session())
        self.append(session(2, 900001, 11))
        with patch.object(records.time, 'time', side_effect=AssertionError('wall clock used')):
            first = self.reader.poll()
            self.assertEqual(first['freshness']['status'], 'waiting')
            self.assertEqual(first['freshness']['source_age_at_publish_s'], .25)
            self.assertEqual(first['freshness']['host_observation_age_s'], 0)
            self.now += .5
            self.append(session(3, 900002, 12))
            self.assertEqual(self.reader.poll()['freshness']['status'], 'live')
            self.now += 3
            self.assertEqual(self.reader.poll()['freshness']['status'], 'stale')
        self.assertIn('unknown', first['freshness']['clock']['mapping'])

    def action_mission(self, **changes):
        value = dict(version=1, run_id='run-a', mission_id='b' * 32,
                     control_epoch='a' * 32, native_generation=2,
                     action_token='c' * 32, state='running', allowed_actions=['pause'])
        value.update(changes)
        (self.root / 'mission-status.json').write_text(json.dumps(value), encoding='utf-8')
        return value

    def action_session(self, sequence, state=None, control=None, **changes):
        row = session(sequence, 900000 + sequence, 10 + sequence, native_generation=2, **changes)
        row['message']['state'].update(armed=True, mode='OFFBOARD')
        row['message']['state'].update(state or {})
        row['message']['control'].update(control_state=2)
        row['message']['control'].update(control or {})
        self.append(row)

    def test_action_offer_requires_live_source_and_never_updates_input(self):
        mission = self.action_mission()
        self.action_session(1)
        first = self.reader.poll()
        self.assertEqual(first['action_offer']['allowed_actions'], [])
        self.action_session(2)
        live = self.reader.poll()
        self.assertEqual(live['action_offer'], dict(version=1, reason='ready', **{
            k: mission[k] for k in ('mission_id', 'action_token', 'control_epoch',
                                   'native_generation', 'allowed_actions')}))
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        live['action_offer']['allowed_actions'].append('resume')
        self.assertEqual(self.reader.poll()['action_offer']['allowed_actions'], ['pause'])
        self.assertEqual(self.reader.poll(terminal=True)['action_offer']['allowed_actions'], [])
        self.now += 3
        self.assertEqual(self.reader.poll()['action_offer']['reason'], 'feedback_not_live')
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_action_offer_identity_and_lifecycle_fail_closed(self):
        self.action_session(1)
        self.reader.poll()
        self.action_session(2)
        for change in (dict(mission_id='not-a-uuid'), dict(action_token=None),
                       dict(action_token='C' * 32), dict(control_epoch='d' * 32),
                       dict(native_generation=True), dict(native_generation=2.0),
                       dict(native_generation=3), dict(native_generation=2**64),
                       dict(allowed_actions=['pause', 'resume']), dict(allowed_actions=[]),
                       dict(state='pausing'), dict(state='resuming'), dict(state='landing'),
                       dict(state='completed'), dict(run_id='old')):
            with self.subTest(change=change):
                self.action_mission(**change)
                self.assertEqual(self.reader.poll()['action_offer']['allowed_actions'], [])
        self.action_mission(state='takeover')
        self.assertEqual(self.reader.poll()['action_offer']['allowed_actions'], ['pause'])
        self.action_mission(state='paused', allowed_actions=['resume'])
        self.action_session(3, state=dict(mode='AUTO.LOITER'), control=dict(control_state=0))
        self.assertEqual(self.reader.poll()['action_offer']['allowed_actions'], ['resume'])
        self.action_session(4, state=dict(armed=False))
        self.assertEqual(self.reader.poll()['action_offer']['reason'], 'not_armed')

    def test_pause_requires_observed_task_control_and_valid_packet_generation(self):
        self.action_mission()
        self.action_session(1)
        self.reader.poll()
        self.action_session(2)
        self.reader.poll()
        for sequence, change in enumerate((dict(state=dict(mode='AUTO.LOITER')),
                dict(state=dict(mode='BRAKE')), dict(control=dict(control_state=0)),
                dict(control=dict(failsafe=True))), start=3):
            with self.subTest(change=change):
                self.action_session(sequence, **change)
                self.assertEqual(self.reader.poll()['action_offer']['reason'], 'task_control_not_observed')
        for sequence, generation in enumerate((True, 2.0, 3, None), start=7):
            row = session(sequence, 900000 + sequence, 10 + sequence, native_generation=generation)
            row['message']['state'].update(armed=True, mode='GUIDED')
            row['message']['control'].update(control_state=2)
            self.append(row)
            self.assertEqual(self.reader.poll()['action_offer']['reason'], 'generation_mismatch')

    def test_repeated_source_sequence_and_mtime_do_not_refresh(self):
        self.establish()
        self.now += 1
        self.append(session(2, 900001, 11))
        os.utime(self.root / 'prometheus.jsonl', (2000000000, 2000000000))
        result = self.reader.poll()
        self.assertEqual(result['freshness']['host_observation_age_s'], 1)
        self.append(session(3, 900001, 11, published_monotonic_s=900001.5))
        self.now += 1
        result = self.reader.poll()
        self.assertEqual(result['freshness']['status'], 'stale')
        self.assertEqual(result['freshness']['host_observation_age_s'], 2)
        self.assertIn('source_frozen_or_regressed', self.codes(result))
        # New receipt time with an unchanged FC stamp also cannot renew freshness.
        self.append(session(4, 900003, 11))
        self.assertEqual(self.reader.poll()['freshness']['host_observation_age_s'], 2)

    def test_identity_epoch_and_sequence_fail_closed_preserve_history(self):
        for changes in ({'run_id': 'foreign'}, {'version': True}, {'version': 2},
                        {'control_epoch': 'short'}, {'control_epoch': 'b' * 32},
                        {'sequence': 1}, {'sequence': True}):
            with self.subTest(changes=changes):
                self.reader = records.LiveRunReader(self.root, 'run-a')
                (self.root / 'prometheus.jsonl').write_text('')
                self.establish()
                prior = self.reader.poll()['state']
                row = session(3, 900002, 12)
                row['message'].update(changes)
                self.append(row)
                result = self.reader.poll()
                self.assertEqual(result['freshness']['status'], 'stale')
                self.assertEqual(result['state'], prior)

    def test_invalid_flags_nonfinite_and_missing_fields(self):
        for change in ('flag', 'nan', 'overflow', 'header', 'old_source', 'unknown_clock'):
            with self.subTest(change=change):
                self.reader = records.LiveRunReader(self.root, 'run-a')
                (self.root / 'prometheus.jsonl').write_text('')
                self.establish()
                row = session(3, 900002, 12)
                msg = row['message']
                if change == 'flag':
                    msg['state']['odom_valid'] = False
                elif change == 'nan':
                    msg['state']['position'][0] = float('nan')
                elif change == 'overflow':
                    msg['source_received_monotonic_s'] = float('inf')
                elif change == 'header':
                    del msg['state']['header']
                elif change == 'old_source':
                    msg['published_monotonic_s'] += 10
                else:
                    msg['source_clock'] = 'unknown'
                self.append(row)
                result = self.reader.poll()
                self.assertEqual(result['freshness']['status'], 'stale')
                self.assertEqual(result['raw']['future_field'], msg['future_field'])
                self.assertEqual(result['raw_json'], json.dumps(row))
                json.dumps(result, allow_nan=False)

    def test_optional_unknown_telemetry_does_not_invalidate_required_navigation(self):
        self.establish()
        row=session(3,900002,12)
        row['message']['state']['range']=float('nan')
        row['message']['state']['rel_alt']=float('nan')
        self.append(row)
        result=self.reader.poll()
        self.assertEqual(result['freshness']['status'],'live')
        self.assertEqual(result['state']['range'],{'nonfinite':'NaN'})
        self.assertIn('nonfinite_values',self.codes(result))
        self.assertIn('NaN',result['raw_json'])
        row=session(4,900003,13)
        row['message']['state']['position'][0]=float('nan')
        self.append(row)
        self.assertEqual(self.reader.poll()['freshness']['status'],'stale')

    def test_native_result_envelope_retains_raw_hash_and_nonfinite_markers(self):
        raw='{"status":"pass","children_reaped":true,"range":NaN,"overflow":1e999}\n'
        path=self.root/'result.json'
        path.write_text(raw,encoding='utf-8')
        before=path.read_bytes()
        result=records.read_result(path)
        self.assertEqual(result['raw_json'],before.decode('utf-8'))
        self.assertEqual(result['values']['range'],{'nonfinite':'NaN'})
        self.assertEqual(result['values']['overflow'],{'nonfinite':'1e999'})
        self.assertEqual(result['sha256'],records.hashlib.sha256(before).hexdigest())
        self.assertEqual(path.read_bytes(),before)
        json.dumps(result,allow_nan=False)
        path.write_text('{"status":"pass","status":"failed"}',encoding='utf-8')
        with self.assertRaises(ValueError):
            records.read_result(path)

    def test_missing_partial_rotation_and_truncation(self):
        result = self.reader.poll()
        self.assertIsNone(result['state'])
        self.assertEqual(result['freshness']['status'], 'waiting')
        self.assertIn('missing_file', self.codes(result))
        self.establish()
        path = self.root / 'prometheus.jsonl'
        next_line = json.dumps(session(3, 900002, 12))
        with path.open('a') as out:
            out.write(next_line[:30])
        result = self.reader.poll()
        self.assertIn('partial_tail', self.codes(result))
        self.assertEqual(result['raw']['sequence'], 2)
        with path.open('a') as out:
            out.write(next_line[30:] + '\n')
        self.now += .1
        self.assertEqual(self.reader.poll()['raw']['sequence'], 3)
        path.rename(self.root / 'old.jsonl')
        self.append(session(4, 900003, 13))
        result = self.reader.poll()
        self.assertIn('log_rotated', self.codes(result))
        self.assertNotEqual(result['freshness']['status'], 'live')
        path.write_text(json.dumps(session(5, 900004, 14)) + '\n')
        result = self.reader.poll()
        self.assertIn('log_truncated', self.codes(result))
        self.assertNotEqual(result['freshness']['status'], 'live')

    def test_large_tail_is_bounded(self):
        path = self.root / 'prometheus.jsonl'
        with path.open('wb') as out:
            out.seek(100 * 1024 * 1024)
            out.write(b'\n' + json.dumps(session()).encode() + b'\n')
        result = self.reader.poll()
        self.assertIn('tail_window_skipped', self.codes(result))
        self.assertEqual(result['raw']['sequence'], 1)
        self.assertNotEqual(result['freshness']['status'], 'live')
        self.assertEqual(self.reader.tails['prometheus'].offset, path.stat().st_size)

    def test_malformed_conflicting_duplicate_and_epoch_latch(self):
        self.establish()
        with (self.root / 'prometheus.jsonl').open('a') as out:
            out.write('{bad json}\n')
        result = self.reader.poll()
        self.assertIn('malformed_record', self.codes(result))
        self.assertEqual(result['freshness']['status'], 'stale')
        self.append(session(2, 900001, 11, source_received_valid=False))
        result = self.reader.poll()
        self.assertIn('conflicting_duplicate_sequence', self.codes(result))
        self.assertEqual(result['freshness']['status'], 'stale')
        self.append(session(3, 900002, 12, control_epoch='b' * 32))
        self.reader.poll()
        self.append(session(4, 900003, 13))
        self.assertEqual(self.reader.poll()['freshness']['status'], 'stale')

    def test_overflow_literal_retains_exact_raw(self):
        raw = json.dumps(session()).replace('900000.0', '1e999')
        (self.root / 'prometheus.jsonl').write_text(raw + '\n')
        result = self.reader.poll()
        self.assertEqual(result['freshness']['status'], 'stale')
        self.assertEqual(result['raw_json'], raw)
        self.assertEqual(result['raw']['source_received_monotonic_s'], {'nonfinite': '1e999'})
        json.dumps(result, allow_nan=False)

    def test_mission_events_raw_terminal_and_no_legacy_state(self):
        self.append({'topic': '/uav1/prometheus/state', 'message': {'armed': True}})
        self.assertIsNone(self.reader.poll()['state'])
        self.establish()
        mission = dict(version=1, run_id='run-a', control_epoch='a' * 32,
                       mission_id='mission-a', state='accepted', received_monotonic_s=800000,
                       event='mission_accepted', future={'x': 1})
        (self.root / 'mission-status.json').write_text(json.dumps(mission))
        self.append(mission, 'mission')
        event = dict(run_id='run-a', control_epoch='a' * 32, event='command_accepted')
        self.append({'topic': '/uav1/prometheus/text_info', 'message': {'message': json.dumps(event)}})
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        result = self.reader.poll(terminal=True)
        self.assertEqual(result['freshness']['status'], 'recorded')
        self.assertEqual(result['mission'], mission)
        self.assertEqual([r['stream'] for r in result['events']], ['prometheus', 'mission'])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        result['state']['armed'] = 'mutated'
        self.assertIs(self.reader.poll()['state']['armed'], False)
        mission['run_id'] = 'foreign'
        (self.root / 'mission-status.json').write_text(json.dumps(mission))
        self.assertIsNone(self.reader.poll()['mission'])


class ReplayPageTest(unittest.TestCase):
    def test_loader_order_raw_diagnostics_and_no_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'result.json').write_text('{"run_id":"run-a","epoch":null}')
            for stream in records.replay.STREAMS:
                (root / (stream + '.jsonl')).write_text(''.join(
                    json.dumps(session(i, 900000 + i, i)) + '\n' for i in range(1, 5)))
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            evidence = records.replay.load_evidence(root)
            with patch.object(records.replay, 'load_evidence', wraps=records.replay.load_evidence) as loader, \
                    patch('socket.socket', side_effect=AssertionError('network')), \
                    patch('subprocess.Popen', side_effect=AssertionError('process')):
                for stream in records.replay.STREAMS:
                    page = records.replay_page(root, stream, 1, 2)
                    self.assertEqual(page['records'], [r for r in evidence['records'] if r['stream'] == stream][1:3])
                    self.assertEqual(page['diagnostics'], evidence['diagnostics'])
                    self.assertEqual((page['total'], page['offset'], page['limit']), (4, 1, 2))
                self.assertEqual(loader.call_count, 4)
                self.assertEqual(records.replay_page(root, offset=100)['records'], [])
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            with patch.object(records.replay, 'MAX_BYTES', 1):
                with self.assertRaisesRegex(ValueError, 'limit'):
                    records.replay_page(root)

    def test_strict_page_arguments(self):
        for arguments in ({'offset': True}, {'offset': -1}, {'offset': 1.0},
                          {'limit': False}, {'limit': 101}, {'limit': 0}, {'limit': '2'},
                          {'stream': 'mission'}, {'stream': []}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                records.replay_page('nonexistent', **arguments)

    def test_missing_stream_and_partial_remain_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'prometheus.jsonl').write_text(json.dumps(session()) + '\n{"partial":')
            page = records.replay_page(root)
            self.assertEqual(page['total'], 1)
            self.assertIn('unterminated_last_line', {d['code'] for d in page['diagnostics']})
            self.assertEqual(records.replay_page(root, 'dds')['total'], 0)


if __name__ == '__main__':
    unittest.main()
