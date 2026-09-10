"""Offline checks for tools/audit_aruco_tracking_raw.py; synthetic captures, not flight proof.

Fixtures follow the REAL retained layout (capture root = report.json + run/;
task result aruco block at report['task']['aruco']; recorder provenance
reconciled against epochs/<epoch>/source/ and preflight control_candidate pins)
verified against validation/40-aruco-tracking-01. The fake deserializer maps
exact CDR hex to prepared messages; one test does a real rclpy
serialize->deserialize round-trip when the WSL ROS message environment is
present (no nodes). The shared product timeline is stubbed at audit()'s
injection point; it runs for real in the WSL pass.
"""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import audit_aruco_tracking_raw as audit_mod
from tools.audit_aruco_tracking_raw import (INITIAL_HASH_SEED, RAW_NAME, MOVE_AGENT_CMD,
                                            HOVER_AGENT_CMD, XYZ_VEL_BODY_MODE,
                                            DEFAULT_CONTROL, audit, main, quantize32,
                                            record_sha, require_move_fields)

RUN = 'aruco-track-test0001'
EPOCH = 'e' * 32
CE = 'c' * 32
TID = 't' * 32
STREAM = 's' * 32
PROFILE_SHA = 'a' * 64
IMAGE_SHA = 'd' * 64
BUILDER_BYTES = b'# fixture builder source\n'
BUILDER_SHA = hashlib.sha256(BUILDER_BYTES).hexdigest()
RC_SRC_SHA = '1' * 64
RC_LIB_SHA = '2' * 64
VELOCITY = [0.1, 1 / 3, -0.25]  # 0.1 and 1/3 are not float32-exact

try:  # Real message round-trip runs only in the sourced WSL ROS environment.
    from rclpy.serialization import serialize_message, deserialize_message
    from prometheus_msgs.msg import UAVCommand
    ROS_MESSAGES = True
except Exception:
    ROS_MESSAGES = False


def cdr(index):
    return (b'\x00\x01\x00\x00' + bytes([index])).hex()


def sample(topic, type_name, index, seq):
    return dict(schema_version=1, kind='raw_cdr_sample', take_sequence=seq, topic=topic,
                type=type_name, monotonic_ns=1000 + seq, cdr_hex=cdr(index),
                publisher_gid='ab' * 12, source_timestamp=10 + seq, received_timestamp=20 + seq,
                message=None)


def start_record(stack, uav_id, **identity_overrides):
    channels = [(f'/uav{uav_id}/prometheus/v2/setup', 'wksim_msgs/msg/SetupRequest'),
                (f'/uav{uav_id}/prometheus/v2/command', 'wksim_msgs/msg/CommandRequest'),
                (f'/uav{uav_id}/prometheus/v2/state', 'wksim_msgs/msg/SessionState'),
                (f'/uav{uav_id}/prometheus/text_info', 'prometheus_msgs/msg/TextInfo')]
    identity = dict(builder='Simulator/wksim_runtime/aruco_raw_capture.py',
                    builder_sha256=BUILDER_SHA, rc_take_source_sha256=RC_SRC_SHA,
                    rc_take_lib_sha256=RC_LIB_SHA)
    identity.update(identity_overrides)
    return dict(schema_version=1, kind='aruco_raw_capture_start', run_id=RUN, epoch=EPOCH,
                stack=stack, uav_id=uav_id, node_name='wksim_aruco_raw_' + stack,
                source_identity=identity,
                channels=[dict(topic=t, type=n) for t, n in channels],
                start_monotonic_ns=1, start_utc='2026-09-11T00:00:00Z')


def write_capture(path, start, samples, end_overrides=None):
    """Chain exactly like ArucoRawCapture: the end record carries the pre-end chain head."""
    counts = {}
    for row in samples:
        counts[row['topic']] = counts.get(row['topic'], 0) + 1
    end = dict(schema_version=1, kind='aruco_raw_capture_end', status='complete',
               total_samples=len(samples), samples_per_topic=counts, write_failures=0,
               write_failure_reports=[], close_monotonic_ns=9999,
               close_utc='2026-09-11T00:00:01Z')
    if end_overrides:
        end.update(end_overrides)
    rows, previous = [start] + list(samples), INITIAL_HASH_SEED
    out = []
    for row in rows:
        row = dict(row, prev_record_sha256=previous)
        sha = record_sha(row)
        row['record_sha256'] = sha
        previous = sha
        out.append(row)
    end = dict(end, prev_record_sha256=previous, final_hash_chain=previous)
    end['record_sha256'] = record_sha(end)
    out.append(end)
    path.write_text(''.join(json.dumps(r, sort_keys=True, separators=(',', ':')) + '\n'
                            for r in out), encoding='utf-8')


def text_event(index, seq, uav_id, **event):
    event = dict(run_id=RUN, control_epoch=CE, **event)
    return (sample(f'/uav{uav_id}/prometheus/text_info', 'prometheus_msgs/msg/TextInfo',
                   index, seq), NS(message=json.dumps(event)))


def move_body(command_id):
    return NS(command_id=command_id, agent_cmd=MOVE_AGENT_CMD, move_mode=XYZ_VEL_BODY_MODE,
              control_level=DEFAULT_CONTROL, yaw_rate_mode=True, yaw_rate_ref=0.0,
              velocity_ref=[quantize32(v) for v in VELOCITY])


def move_fields():
    return dict(agent_cmd='MOVE', move_mode='XYZ_VEL_BODY', velocity_ref=list(VELOCITY),
                yaw_rate_mode=True, yaw_rate_ref=0)


def make_stack(root, stack, uav_id, cdr_base, *, selected, requests, terminal_events,
               adapter_actions, links, envelopes, status='pass', start_overrides=None):
    directory = root / 'run' / 'epochs' / EPOCH / 'tasks' / TID / stack
    directory.mkdir(parents=True)
    messages, samples = {}, []
    seq = 0
    for index, (kind, body) in enumerate(requests, 1):
        seq += 1
        type_name = 'wksim_msgs/msg/SetupRequest' if kind == 'setup' else 'wksim_msgs/msg/CommandRequest'
        row = sample(f'/uav{uav_id}/prometheus/v2/{kind}', type_name, cdr_base + index, seq)
        field = 'setup' if kind == 'setup' else 'command'
        messages[row['cdr_hex']] = NS(version=1, run_id=RUN, control_epoch=CE,
                                      request_id=index, **{field: body})
        samples.append(row)
        entry = terminal_events.get(index)
        if entry is None:
            continue  # Fixture knob: a request whose terminal event never arrived.
        event_index, event = entry
        seq += 1
        row, message = text_event(event_index, seq, uav_id, request_id=index, **event)
        messages[row['cdr_hex']] = message
        samples.append(row)
    seq += 1
    state = sample(f'/uav{uav_id}/prometheus/v2/state', 'wksim_msgs/msg/SessionState',
                   cdr_base + 30, seq)
    messages[state['cdr_hex']] = NS(version=1, run_id=RUN, control_epoch=CE,
                                    state=NS(uav_id=uav_id))
    samples.append(state)
    write_capture(directory / RAW_NAME,
                  start_record(stack, uav_id, **(start_overrides or {})), samples)
    report = dict(run_id=RUN, scene_epoch=EPOCH, stack=stack, uav_id=uav_id, status=status,
                  task_mode='initial',
                  task=dict(run_id=RUN, control_epoch=CE, protocol='session_v1', sent=[],
                            events=[], control_restarts=[], final={},
                            request_envelopes=envelopes,
                            aruco=dict(selected=selected, profile_sha256=PROFILE_SHA,
                                       binding=(dict(first_step=10, stream_id=STREAM,
                                                     episode_end_step=90)
                                                if selected else None),
                                       observation_links=links,
                                       adapter_actions=adapter_actions, raw_capture=None)))
    (directory / 'result.json').write_text(json.dumps(report), encoding='utf-8')
    return report, messages


def action(act, command_id, **extra):
    base = dict(schema=audit_mod.ACTION_SCHEMA, run_id=RUN, scene_epoch=EPOCH, stream_id=STREAM,
                authority_step=100, authority_now_step=101, seam_reason='track', action=act,
                command_id=command_id, send_failed=False, ack_unconfirmed=False,
                public_fields=None)
    base.update(extra)
    return base


def make_run(case, *, peer_move=False, drop_hover_raw=False, drop_move_terminal=False,
             rejected_terminal=False, failed_task=False, bad_state_epoch=False,
             bad_terminal_epoch=False, px4_start_overrides=None, preflight_lib_sha=RC_LIB_SHA,
             builder_bytes=BUILDER_BYTES):
    tmp = Path(tempfile.mkdtemp(prefix='wksim-aruco-audit-'))
    case.addCleanup(shutil.rmtree, tmp, True)
    root = tmp / 'case'
    move_env = dict(version=1, run_id=RUN, control_epoch=CE, request_id=2,
                    command=dict(command_id=1, agent_cmd=MOVE_AGENT_CMD,
                                 move_mode=XYZ_VEL_BODY_MODE, control_level=DEFAULT_CONTROL,
                                 velocity_ref=list(VELOCITY), yaw_rate_mode=True,
                                 yaw_rate_ref=0))
    hover_env = dict(version=1, run_id=RUN, control_epoch=CE, request_id=3,
                     command=dict(command_id=2, agent_cmd=HOVER_AGENT_CMD,
                                  control_level=DEFAULT_CONTROL))
    px4_requests = [('setup', NS(cmd=1)), ('command', move_body(1))]
    px4_events = {1: (40, dict(event='setup_completed')),
                  2: (41, dict(event='command_accepted', command_id=1))}
    px4_envelopes = [dict(version=1, run_id=RUN, control_epoch=CE, request_id=1,
                          setup=dict(cmd=1)), move_env]
    if not drop_hover_raw:
        px4_requests.append(('command', NS(command_id=2, agent_cmd=HOVER_AGENT_CMD,
                                           control_level=DEFAULT_CONTROL)))
        px4_events[3] = (42, dict(event='command_accepted', command_id=2))
        px4_envelopes.append(hover_env)
    if drop_move_terminal:
        del px4_events[2]
    if rejected_terminal:
        px4_events[2] = (41, dict(event='command_rejected', command_id=1, reason='stale'))
    actions = [action('move', 1, public_fields=move_fields()),
               action('hover', 2, seam_reason='expired_move:target_lost',
                      public_fields=dict(agent_cmd='CURRENT_POS_HOVER'))]
    links = [dict(sequence=1, capture_step=100, frame_id=5, image_sha256=IMAGE_SHA,
                  authority_step=100, action='move', command_id=1)]
    px4_report, messages = make_stack(root, 'px4', 2, 16, selected=True,
                                      requests=px4_requests, terminal_events=px4_events,
                                      adapter_actions=actions, links=links,
                                      envelopes=px4_envelopes,
                                      status='failed' if failed_task else 'pass',
                                      start_overrides=px4_start_overrides)
    ap_requests = [('setup', NS(cmd=1))]
    ap_events = {1: (43, dict(event='setup_completed'))}
    ap_envelopes = [dict(version=1, run_id=RUN, control_epoch=CE, request_id=1,
                         setup=dict(cmd=1))]
    if peer_move:
        ap_requests.append(('command', NS(command_id=7, agent_cmd=MOVE_AGENT_CMD,
                                          move_mode=XYZ_VEL_BODY_MODE,
                                          control_level=DEFAULT_CONTROL, yaw_rate_mode=False,
                                          yaw_rate_ref=0.0, velocity_ref=[0.0, 0.0, 0.0])))
        ap_events[2] = (44, dict(event='command_accepted', command_id=7))
        ap_envelopes.append(dict(version=1, run_id=RUN, control_epoch=CE, request_id=2,
                                 command=dict(command_id=7, agent_cmd=MOVE_AGENT_CMD,
                                              move_mode=XYZ_VEL_BODY_MODE,
                                              control_level=DEFAULT_CONTROL,
                                              velocity_ref=[0.0, 0.0, 0.0],
                                              yaw_rate_mode=False, yaw_rate_ref=0)))
    ap_report, ap_messages = make_stack(root, 'arducopter', 1, 100, selected=False,
                                        requests=ap_requests, terminal_events=ap_events,
                                        adapter_actions=None, links=[], envelopes=ap_envelopes)
    messages.update(ap_messages)
    if bad_state_epoch:
        key = cdr(16 + 30)
        messages[key] = NS(version=1, run_id=RUN, control_epoch='f' * 32, state=NS(uav_id=2))
    preflight = dict(ok=True, identities=dict(control_candidate=dict(
        python_sha256={'rc_transport.py': RC_SRC_SHA}, rc_transport_sha256=preflight_lib_sha)))
    epoch_result = dict(epoch=EPOCH, run_id=RUN, status='stopped', cleanup_errors=[],
                        authority=dict(tick=8, phase='stopped', pending_tick=None,
                                       time_ns=8000000),
                        clock_publications=9, preflight=preflight,
                        tasks={'px4-task-' + TID: px4_report, 'arducopter-task-' + TID: ap_report})
    epoch_dir = root / 'run' / 'epochs' / EPOCH
    epoch_dir.mkdir(parents=True, exist_ok=True)
    (epoch_dir / 'result.json').write_text(json.dumps(epoch_result), encoding='utf-8')
    (epoch_dir / 'preflight.json').write_text(json.dumps(preflight), encoding='utf-8')
    builder = epoch_dir / 'source' / 'Simulator' / 'wksim_runtime' / 'aruco_raw_capture.py'
    builder.parent.mkdir(parents=True)
    builder.write_bytes(builder_bytes)
    (root / 'run').mkdir(exist_ok=True)
    (root / 'run' / 'result.json').write_text(json.dumps(dict(
        run_id=RUN, status='pass', epochs=[dict(epoch=EPOCH, result=epoch_result)])),
        encoding='utf-8')
    (root / 'report.json').write_text(json.dumps(dict(
        session=dict(version=1, run_id=RUN, instance_id='i' * 32))), encoding='utf-8')

    def fake_deserialize(data, type_name):
        return messages[data.hex()]
    timeline = lambda directory, result: ({'simultaneous_height_above_1m_ticks': 4000}, 2,
                                          {'permissions': 1})
    return root, dict(deserialize=fake_deserialize, product_timeline=timeline)


class ArucoRawAuditTest(unittest.TestCase):
    def test_happy_path_is_pending_with_uncovered(self):
        root, inject = make_run(self)
        report = audit(root, **inject)
        self.assertEqual(report['status'], 'pending')
        self.assertTrue(report['uncovered'])
        self.assertEqual(report['stacks']['px4']['adapter'], dict(actions=2, sent=2))
        self.assertEqual(report['stacks']['arducopter']['adapter'], dict(actions=0, sent=0))
        self.assertEqual(report['stacks']['px4']['provenance']['builder_sha256'], BUILDER_SHA)
        self.assertIn('capture_report_sha256', report['entry'])

    def test_run_root_entry(self):
        root, inject = make_run(self)
        report = audit(root, run_root=root / 'run', **inject)
        self.assertEqual(report['status'], 'pending')
        self.assertIn('run_root', report['entry'])

    def test_wrong_layer_rejected(self):
        root, inject = make_run(self)
        with self.assertRaisesRegex(ValueError, 'report.json'):
            audit(root / 'run', **inject)  # A run root is not a capture root.
        with self.assertRaisesRegex(ValueError, 'result.json'):
            audit(root, run_root=root / 'epochs', **inject)

    def test_mock_provenance_rejected(self):
        root, inject = make_run(self, px4_start_overrides=dict(rc_take_lib_sha256='mock'))
        with self.assertRaisesRegex(ValueError, 'provenance'):
            audit(root, **inject)

    def test_builder_source_mismatch_rejected(self):
        root, inject = make_run(self, builder_bytes=b'# tampered builder\n')
        with self.assertRaisesRegex(ValueError, 'builder differs'):
            audit(root, **inject)

    def test_rc_take_pin_mismatch_rejected(self):
        root, inject = make_run(self, preflight_lib_sha='9' * 64)
        with self.assertRaisesRegex(ValueError, 'library differs'):
            audit(root, **inject)

    def test_rejected_terminal_event_fails(self):
        root, inject = make_run(self, rejected_terminal=True)
        with self.assertRaisesRegex(ValueError, 'rejected/revoked'):
            audit(root, **inject)

    def test_failed_task_cannot_be_pending(self):
        root, inject = make_run(self, failed_task=True)
        with self.assertRaisesRegex(ValueError, 'did not pass'):
            audit(root, **inject)

    def test_session_state_epoch_mismatch_fails(self):
        root, inject = make_run(self, bad_state_epoch=True)
        with self.assertRaisesRegex(ValueError, 'session state identity/epoch'):
            audit(root, **inject)

    def test_terminal_event_epoch_mismatch_fails(self):
        root, inject = make_run(self, bad_terminal_epoch=True)
        inject['deserialize']  # placeholder for clarity
        original = inject['deserialize']
        def bad(data, type_name):
            message = original(data, type_name)
            if type_name == 'prometheus_msgs/msg/TextInfo':
                event = json.loads(message.message)
                event['control_epoch'] = 'f' * 32
                return NS(message=json.dumps(event))
            return message
        with self.assertRaisesRegex(ValueError, 'event identity/epoch'):
            audit(root, deserialize=bad, product_timeline=inject['product_timeline'])

    def test_hash_chain_tamper_fails(self):
        root, inject = make_run(self)
        path = root / 'run' / 'epochs' / EPOCH / 'tasks' / TID / 'px4' / RAW_NAME
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[2]['source_timestamp'] += 1  # Content changed; hashes now stale.
        path.write_text(''.join(json.dumps(r, sort_keys=True, separators=(',', ':')) + '\n'
                                for r in rows))
        with self.assertRaisesRegex(ValueError, 'hash'):
            audit(root, **inject)

    def test_missing_end_record_fails(self):
        root, inject = make_run(self)
        path = root / 'run' / 'epochs' / EPOCH / 'tasks' / TID / 'px4' / RAW_NAME
        lines_ = path.read_text().splitlines(keepends=True)
        path.write_text(''.join(lines_[:-1]))
        with self.assertRaisesRegex(ValueError, 'start and one end'):
            audit(root, **inject)

    def test_end_count_mismatch_fails(self):
        root, inject = make_run(self)
        path = root / 'run' / 'epochs' / EPOCH / 'tasks' / TID / 'px4' / RAW_NAME
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        write_capture(path, rows[0], rows[1:-1],
                      end_overrides=dict(total_samples=len(rows) - 1))
        with self.assertRaisesRegex(ValueError, 'end counts/hash'):
            audit(root, **inject)

    def test_take_sequence_gap_fails(self):
        root, inject = make_run(self)
        path = root / 'run' / 'epochs' / EPOCH / 'tasks' / TID / 'px4' / RAW_NAME
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        samples = rows[1:-1]
        samples[1]['take_sequence'] = 99
        write_capture(path, rows[0], samples)
        with self.assertRaisesRegex(ValueError, 'gapped or reordered'):
            audit(root, **inject)

    def test_write_failed_capture_fails(self):
        root, inject = make_run(self)
        path = root / 'run' / 'epochs' / EPOCH / 'tasks' / TID / 'px4' / RAW_NAME
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        write_capture(path, rows[0], rows[1:-1],
                      end_overrides=dict(status='write_failed', write_failures=1))
        with self.assertRaisesRegex(ValueError, 'write failures'):
            audit(root, **inject)

    def test_hover_action_without_raw_request_fails(self):
        root, inject = make_run(self, drop_hover_raw=True)
        with self.assertRaisesRegex(ValueError, 'no raw CommandRequest'):
            audit(root, **inject)

    def test_peer_visual_move_fails(self):
        root, inject = make_run(self, peer_move=True)
        with self.assertRaisesRegex(ValueError, 'Peer published a visual MOVE'):
            audit(root, **inject)

    def test_command_without_terminal_event_fails(self):
        root, inject = make_run(self, drop_move_terminal=True)
        with self.assertRaisesRegex(ValueError, 'terminal event'):
            audit(root, **inject)

    def test_float32_quantization_boundary(self):
        fields = move_fields()
        body = move_body(1)
        require_move_fields(fields, body, 1, 'test')  # doubles vs float32 twins pass
        drifted = move_body(1)
        drifted.velocity_ref = [quantize32(0.1 + 1e-8), *drifted.velocity_ref[1:]]
        with self.assertRaisesRegex(ValueError, 'velocity axes'):
            require_move_fields(fields, drifted, 1, 'test')
        with self.assertRaisesRegex(ValueError, 'Non-finite'):
            require_move_fields(dict(fields, velocity_ref=[float('nan'), 0.0, 0.0]),
                                body, 1, 'test')

    def test_main_exit_codes_and_no_overwrite(self):
        root, _ = make_run(self)
        out = root.parent / 'audit.json'
        with mock.patch.object(audit_mod, 'audit', return_value=dict(status='pending',
                                                                     uncovered=['x'])):
            self.assertEqual(main([str(root), '--output', str(out)]), 2)
            with self.assertRaises(FileExistsError):
                main([str(root), '--output', str(out)])
            self.assertEqual(main([str(root), '--run-root', str(root / 'run'),
                                   '--output', str(root.parent / 'audit-rr.json')]), 2)
        with mock.patch.object(audit_mod, 'audit',
                               return_value=dict(status='fail', error='x', uncovered=['x'])):
            self.assertEqual(main([str(root), '--output', str(root.parent / 'audit-f.json')]), 1)
        with self.assertRaises(ValueError):
            main([str(root), '--output', str(root / 'inside.json')])


class RealMessageQuantizationTest(unittest.TestCase):
    """Real rclpy serialize->deserialize round-trip; no nodes. Runs in the WSL ROS env."""
    @unittest.skipUnless(ROS_MESSAGES, 'requires the WSL ROS message environment')
    def test_uavcommand_float32_roundtrip(self):
        for value in (0.1, 1 / 3, 3.0):
            msg = UAVCommand()
            msg.agent_cmd = UAVCommand.MOVE
            msg.move_mode = UAVCommand.XYZ_VEL_BODY
            msg.control_level = UAVCommand.DEFAULT_CONTROL
            msg.velocity_ref = [float(value), 0.0, 3.0]
            msg.yaw_rate_mode = True
            msg.yaw_rate_ref = 0.0
            msg.command_id = 1
            back = deserialize_message(serialize_message(msg), UAVCommand)
            self.assertEqual(back.velocity_ref[0], quantize32(value))
            self.assertEqual(back.velocity_ref[2], 3.0)
            if value != 3.0:
                # NEP 50: np.float32(0.1) == 0.1 is True; the wire value differs as float64.
                self.assertNotEqual(float(back.velocity_ref[0]), value)
        msg = UAVCommand()
        msg.agent_cmd = UAVCommand.MOVE
        msg.move_mode = UAVCommand.XYZ_VEL_BODY
        msg.control_level = UAVCommand.DEFAULT_CONTROL
        msg.velocity_ref = [float(v) for v in VELOCITY]
        msg.yaw_rate_mode = True
        msg.yaw_rate_ref = 0.0
        msg.command_id = 7
        back = deserialize_message(serialize_message(msg), UAVCommand)
        require_move_fields(move_fields(), back, 7, 'real-roundtrip')  # Must not raise.


if __name__ == '__main__':
    unittest.main()
