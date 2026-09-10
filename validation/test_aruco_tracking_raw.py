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
import os
from pathlib import Path
import re
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
INST = 'i' * 32
SENSOR = 'front_rgb'  # Real contract: sensor_id is a string (profile camera).
FIRST_STEP = 10
EPISODE_STEPS = dict(initial_steps=100, moving_steps=100, occluded_steps=100,
                     recovery_steps=100)
EPISODE_END = FIRST_STEP + sum(EPISODE_STEPS.values())  # 410
PROFILE = dict(schema='wksim.aruco-tracking-profile.v1',
               camera=dict(version=1, sensor_id=SENSOR, width=1920, height=1440,
                           horizontal_fov_degrees=90, position_cm=[30, 20, 10],
                           quaternion_xyzw=[0, 0, 0, 1], interval_steps=100,
                           notify_port=19072),
               target=dict(dictionary='DICT_6X6_250', marker_id=23, side_length_m=0.5,
                           max_age_steps=300, max_distance_m=8, max_speed_mps=2,
                           max_jump_m=0.5, max_reprojection_px=1),
               controller=dict(desired_body_flu_m=[2.3, -0.32, 0.06], gain_per_s=0.6,
                               max_speed_mps=0.5),
               scene=dict(fixture_case=5, **EPISODE_STEPS, world_velocity_mps=[0, 0.25, 0]),
               mission=dict(initial_hold_s=5, binding_timeout_s=30,
                            command_acceptance_timeout_s=0.5))
PROFILE_REL = 'Simulator/wksim_runtime/aruco-tracking-v1.json'
PROFILE_BYTES = json.dumps(PROFILE, sort_keys=True, separators=(',', ':')).encode('utf-8')
PROFILE_SHA = hashlib.sha256(PROFILE_BYTES).hexdigest()
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
               adapter_actions, links, envelopes, status='pass', start_overrides=None,
               binding_override=None):
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
    task_binding = None
    if selected:
        task_binding = dict(first_step=FIRST_STEP, stream_id=STREAM,
                            episode_end_step=EPISODE_END)
        if binding_override:
            task_binding.update(binding_override)
    report = dict(run_id=RUN, scene_epoch=EPOCH, stack=stack, uav_id=uav_id, status=status,
                  task_mode='initial',
                  task=dict(run_id=RUN, control_epoch=CE, protocol='session_v1', sent=[],
                            events=[], control_restarts=[], final={},
                            request_envelopes=envelopes,
                            aruco=dict(selected=selected, profile_sha256=PROFILE_SHA,
                                       binding=task_binding,
                                       observation_links=links,
                                       adapter_actions=adapter_actions, raw_capture=None)))
    (directory / 'result.json').write_text(json.dumps(report), encoding='utf-8')
    return report, messages


BINDING = dict(schema='wksim.aruco-binding.v1', run_id=RUN, epoch=EPOCH, instance_id=INST,
               generation=1, stream_id=STREAM, camera=dict(vehicle_id=2, sensor_id=SENSOR),
               first_step=FIRST_STEP, profile_sha256=PROFILE_SHA)


def _host_temp_root():
    """Tmp dir whose Windows-absolute spelling resolves on this host.

    The audited report stores Windows-absolute frame paths; on WSL they resolve
    through /mnt/<drive>, so fixtures created there must live under /mnt.
    """
    if os.name == 'nt':
        return Path(tempfile.mkdtemp(prefix='wksim-aruco-audit-'))
    for base in ('/mnt/c/Users/PC/AppData/Local/Temp', '/mnt/c/Windows/Temp'):
        if Path(base).is_dir():
            return Path(tempfile.mkdtemp(prefix='wksim-aruco-audit-', dir=base))
    return Path(tempfile.mkdtemp(prefix='wksim-aruco-audit-'))


def _stored_path(real):
    """Store a path as the Windows driver wrote it; WSL fixtures convert /mnt/<drive>."""
    text = str(real)
    if os.name == 'nt':
        return text
    match = re.match(r'^/mnt/([a-z])/(.*)$', text)
    if match:
        return match.group(1).upper() + ':\\' + match.group(2).replace('/', '\\')
    return text


def target_dict(valid_until=150, step=100, frame_id=5):
    """Real Consumer contract: step/frame_id are decimal strings, valid_until int."""
    return dict(schema='wksim.aruco-target.v1', run_id=RUN, epoch=EPOCH, instance_id=INST,
                generation=1, stream_id=STREAM, vehicle_id='2', sensor_id=SENSOR,
                step=str(step), frame_id=str(frame_id), valid_until_step=valid_until,
                move_mode='XYZ_VEL_BODY', position_body_flu_m=[2.3, -0.32, 0.06],
                distance_m=2.32)


def frame_entry(root, name, step, frame_id, target, tick):
    """One report['frames'] entry plus its real retained PNG/metadata/scene files."""
    rgb = root / 'view' / 'view-test' / 'rgb'
    rgb.mkdir(parents=True, exist_ok=True)
    png = rgb / (name + '.png')
    png.write_bytes(b'png-bytes-' + name.encode())
    metadata = dict(schema='wksim.rgb.v2', run_id=RUN, epoch=EPOCH, instance_id=INST,
                    stream_id=STREAM, step=str(step), frame_id=str(frame_id),
                    vehicle_id='2', sensor_id=SENSOR, image=png.name)
    meta = rgb / (name + '.json')
    meta.write_text(json.dumps(metadata) + '\n', encoding='utf-8')
    notice = dict(schema='wksim.rgb-ready.v2', run_id=RUN, instance_id=INST, epoch=EPOCH,
                  stream_id=STREAM, generation=1, metadata=meta.name)
    scene_path = rgb / ('aruco-%s-%d.json' % (EPOCH, step))
    scene_path.write_text(json.dumps(dict(first_step=FIRST_STEP, step=step)) + '\n',
                          encoding='utf-8')
    image_sha = hashlib.sha256(png.read_bytes()).hexdigest()
    return dict(frame=dict(notification=notice, metadata=metadata,
                           metadata_path=_stored_path(meta), image_path=_stored_path(png)),
                scene_path=_stored_path(scene_path),
                scene_sha256=hashlib.sha256(scene_path.read_bytes()).hexdigest(),
                now_step=tick, image_sha256=image_sha,
                authority=dict(epoch=EPOCH, generation=1, tick=tick),
                participants=None, target=target, reason='test')


def observation_row(sequence, step, frame_id, image_sha, target):
    return dict(schema='wksim.aruco-observation.v1', run_id=RUN, epoch=EPOCH,
                instance_id=INST, generation=1, stream_id=STREAM, sequence=sequence,
                capture_step=step, frame_id=frame_id, target=target, image_sha256=image_sha)


def link(sequence, capture_step, frame_id, image_sha, authority_step, act, command_id):
    return dict(sequence=sequence, capture_step=capture_step, frame_id=frame_id,
                image_sha256=image_sha, authority_step=authority_step, action=act,
                command_id=command_id)


def action(act, command_id, **extra):
    base = dict(schema=audit_mod.ACTION_SCHEMA, run_id=RUN, scene_epoch=EPOCH, stream_id=STREAM,
                authority_step=100, authority_now_step=101, seam_reason='track', action=act,
                command_id=command_id, send_failed=False, ack_unconfirmed=False,
                public_fields=None)
    base.update(extra)
    return base


def make_run(case, *, peer_move=False, drop_hover_raw=False, drop_move_terminal=False,
             rejected_terminal=False, failed_task=False, bad_state_epoch=False,
             px4_start_overrides=None, preflight_lib_sha=RC_LIB_SHA,
             builder_bytes=BUILDER_BYTES, bare=False, expire_hold=False, old_frame=False,
             tamper_png=False, escape_path=False, unmapped_move=False,
             move_after_expiry=False, unjustified_hold=False, orphan_suppress=False,
             move_on_null=False, bad_obs_identity=False, consume_expired=False,
             expired_duplicate=False, with_duplicate=False, final_early=False,
             move_past_end=False, no_loss=False, no_recovery=False, lax_step=False,
             entry_target_drift=False, bad_task_binding=False, bad_profile_file=False,
             bad_sensor_type=False):
    tmp = _host_temp_root()
    case.addCleanup(shutil.rmtree, tmp, True)
    root = tmp / 'case'

    def hover_body(cid):
        return NS(command_id=cid, agent_cmd=HOVER_AGENT_CMD, control_level=DEFAULT_CONTROL)

    def envelope(rid, kind, cid):
        command = (dict(command_id=cid, agent_cmd=MOVE_AGENT_CMD,
                        move_mode=XYZ_VEL_BODY_MODE, control_level=DEFAULT_CONTROL,
                        velocity_ref=list(VELOCITY), yaw_rate_mode=True, yaw_rate_ref=0)
                   if kind == 'move' else
                   dict(command_id=cid, agent_cmd=HOVER_AGENT_CMD,
                        control_level=DEFAULT_CONTROL))
        return dict(version=1, run_id=RUN, control_epoch=CE, request_id=rid, command=command)

    # Happy public chain: setup + initial HOLD, MOVE, loss HOLD, recovery MOVE,
    # final HOLD — one full null-invalidation -> TTL withdrawal -> recovery cycle
    # plus a suppressed_hold absorbing the second null observation.
    sends = [('hover', 1), ('move', 2), ('hover', 3), ('move', 4), ('hover', 5)]
    if no_loss:
        sends = [('hover', 1), ('move', 2), ('move', 3), ('move', 4), ('move', 5),
                 ('hover', 6)]
    if bare:
        sends = []
    if no_recovery:
        sends = [s for s in sends if s != ('move', 4)]
    if orphan_suppress:
        sends = [s for s in sends if s not in (('hover', 1), ('hover', 3))]
    raw_sends = [s for s in sends if not (drop_hover_raw and s == ('hover', 3))]
    px4_requests = [('setup', NS(cmd=1))]
    px4_envelopes = [dict(version=1, run_id=RUN, control_epoch=CE, request_id=1,
                          setup=dict(cmd=1))]
    px4_events = {1: (40, dict(event='setup_completed'))}
    for rid, (kind, cid) in enumerate(raw_sends, 2):
        px4_requests.append(('command', move_body(cid) if kind == 'move' else hover_body(cid)))
        px4_envelopes.append(envelope(rid, kind, cid))
        # Event CDR indices must stay disjoint from request/state indices and
        # from the peer stack's: the fake deserializer is keyed by hex alone.
        px4_events[rid] = (60 + rid, dict(event='command_accepted', command_id=cid))
    if drop_move_terminal:
        del px4_events[3]  # The first MOVE request's terminal event never arrived.
    if rejected_terminal:
        px4_events[3] = (63, dict(event='command_rejected', command_id=2, reason='stale'))
    # Report-level gate evidence.
    frames, observations, links, actions = [], [], [], []
    if not bare:
        hover_fields = dict(agent_cmd='CURRENT_POS_HOVER')
        target1 = None if move_on_null else target_dict(valid_until=150, step=100, frame_id=5)
        entry1 = frame_entry(root, 'f1', 100, 5, target1, 100)
        obs1 = observation_row(1, 100, 5, entry1['image_sha256'], target1)
        if bad_obs_identity:
            obs1['stream_id'] = 'x' * 32
        if entry_target_drift and target1 is not None:
            entry1['target'] = dict(target1, valid_until_step=151)
        if lax_step:
            entry1['frame']['metadata']['step'] = ' 100'  # Lax int() would accept this.
        frames.append(entry1)
        observations.append(obs1)
        if no_loss:
            specs = [(2, 'f2', 200, 6, 250), (3, 'f3', 210, 7, 260), (4, 'f4', 250, 8, 300)]
            for seq, name, step, fid, valid in specs:
                target = target_dict(valid_until=valid, step=step, frame_id=fid)
                entry = frame_entry(root, name, step, fid, target, step)
                frames.append(entry)
                observations.append(observation_row(seq, step, fid, entry['image_sha256'],
                                                    target))
                links.append(link(seq, step, fid, entry['image_sha256'], step,
                                  'move', seq + 1))
            links.insert(0, link(1, 100, 5, obs1['image_sha256'], 100, 'move', 2))
            actions = [action('hover', 1, seam_reason='target_missing', authority_step=50,
                              authority_now_step=50, public_fields=hover_fields),
                       action('move', 2, public_fields=move_fields()),
                       action('move', 3, authority_step=200, authority_now_step=201,
                              public_fields=move_fields()),
                       action('move', 4, authority_step=210, authority_now_step=211,
                              public_fields=move_fields()),
                       action('move', 5, authority_step=250, authority_now_step=251,
                              public_fields=move_fields()),
                       action('hover', 6, seam_reason='target_missing',
                              authority_step=EPISODE_END, authority_now_step=EPISODE_END,
                              public_fields=hover_fields)]
        else:
            target2 = (target_dict(valid_until=150, step=140, frame_id=6)
                       if consume_expired else None)  # Consumed at 200: already expired.
            entry2 = frame_entry(root, 'f2', 140 if consume_expired else 200, 6, target2,
                                 200)
            obs2 = observation_row(2, 140 if consume_expired else 200, 6,
                                   entry2['image_sha256'], target2)
            frame3_id = 6 if old_frame else 7
            entry3 = frame_entry(root, 'f3', 210, frame3_id, None, 210)
            obs3 = observation_row(3, 210, frame3_id, entry3['image_sha256'], None)
            target4 = target_dict(valid_until=300, step=250, frame_id=8)
            entry4 = frame_entry(root, 'f4', 250, 8, target4, 250)
            obs4 = observation_row(4, 250, 8, entry4['image_sha256'], target4)
            frames += [entry2, entry3] + ([] if no_recovery else [entry4])
            observations += [obs2, obs3] + ([] if no_recovery else [obs4])
            if not (expire_hold or unjustified_hold or orphan_suppress):
                links.append(link(2, 140 if consume_expired else 200, 6,
                                  entry2['image_sha256'], 200, 'hover', 3))
            links.append(link(3, 210, frame3_id, entry3['image_sha256'], 210,
                              'suppressed_hold', None))
            if not (unmapped_move or no_recovery):
                links.append(link(4, 250, 8, entry4['image_sha256'],
                                  420 if move_past_end else 250, 'move', 4))
            links.insert(0, link(1, 100, 5, obs1['image_sha256'], 100, 'move', 2))
            move1 = action('move', 2, public_fields=move_fields())
            if move_after_expiry:
                move1['authority_now_step'] = 160  # target valid_until_step is 150
            hover3 = action('hover', 3, seam_reason='target_lost',
                            authority_step=120 if unjustified_hold else 200,
                            authority_now_step=120 if unjustified_hold else 200,
                            public_fields=hover_fields)
            move4 = action('move', 4, authority_step=420 if move_past_end else 250,
                           authority_now_step=420 if move_past_end else 251,
                           public_fields=move_fields())
            final_step = 300 if final_early else (420 if move_past_end else EPISODE_END)
            hover5 = action('hover', 5, seam_reason='target_missing',
                            authority_step=final_step, authority_now_step=final_step,
                            public_fields=hover_fields)
            if not orphan_suppress:
                actions.append(action('hover', 1, seam_reason='target_missing',
                                      authority_step=50, authority_now_step=50,
                                      public_fields=hover_fields))
            actions.append(move1)
            if expired_duplicate:
                actions.append(action('duplicate_record', None, authority_step=100,
                                      authority_now_step=200))  # Past validity: illegal.
            if with_duplicate:
                actions.append(action('duplicate_record', None, authority_step=100,
                                      authority_now_step=120))  # Still fresh: legal.
            if not orphan_suppress:
                actions.append(hover3)
            actions.append(action('suppressed_hold', None, authority_step=210,
                                  authority_now_step=210))
            if not no_recovery:
                actions.append(move4)
            actions.append(hover5)
        if tamper_png:  # Recorded sha no longer matches the retained PNG bytes.
            (root / 'view' / 'view-test' / 'rgb' / 'f1.png').write_bytes(b'tampered')
        if escape_path:  # A real file with the same basename, but outside the root.
            outside = tmp / 'f1.png'
            outside.write_bytes(b'outside')
            entry1['frame']['image_path'] = _stored_path(outside)
    px4_report, messages = make_stack(root, 'px4', 2, 16, selected=True,
                                      requests=px4_requests, terminal_events=px4_events,
                                      adapter_actions=actions, links=links,
                                      envelopes=px4_envelopes,
                                      status='failed' if failed_task else 'pass',
                                      start_overrides=px4_start_overrides,
                                      binding_override=(dict(episode_end_step=EPISODE_END + 1)
                                                        if bad_task_binding else None))
    ap_requests = [('setup', NS(cmd=1))]
    ap_events = {1: (150, dict(event='setup_completed'))}
    ap_envelopes = [dict(version=1, run_id=RUN, control_epoch=CE, request_id=1,
                         setup=dict(cmd=1))]
    if peer_move:
        ap_requests.append(('command', NS(command_id=7, agent_cmd=MOVE_AGENT_CMD,
                                          move_mode=XYZ_VEL_BODY_MODE,
                                          control_level=DEFAULT_CONTROL, yaw_rate_mode=False,
                                          yaw_rate_ref=0.0, velocity_ref=[0.0, 0.0, 0.0])))
        ap_events[2] = (151, dict(event='command_accepted', command_id=7))
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
    profile_file = root / 'sources' / Path(PROFILE_REL)
    profile_file.parent.mkdir(parents=True, exist_ok=True)
    profile_file.write_bytes(b'{"tampered":true}' if bad_profile_file else PROFILE_BYTES)
    report_top = dict(session=dict(version=1, run_id=RUN, instance_id=INST),
                      profile=json.loads(PROFILE_BYTES), profile_sha256=PROFILE_SHA,
                      source_sha256={PROFILE_REL: PROFILE_SHA},
                      stream_id=STREAM, binding=BINDING, frames=frames,
                      observations=observations)
    if bad_sensor_type:
        report_top['binding'] = dict(BINDING, camera=dict(vehicle_id=2, sensor_id=7))
    if bare:  # Early failure shape: no binding/stream and empty frame lists retained.
        report_top = dict(session=dict(version=1, run_id=RUN, instance_id=INST),
                          profile_sha256=PROFILE_SHA, frames=[], observations=[])
    (root / 'report.json').write_text(json.dumps(report_top), encoding='utf-8')

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
        self.assertEqual(report['stacks']['px4']['adapter'], dict(actions=6, sent=5))
        self.assertEqual(report['stacks']['arducopter']['adapter'], dict(actions=0, sent=0))
        self.assertEqual(report['stacks']['px4']['provenance']['builder_sha256'], BUILDER_SHA)
        self.assertIn('capture_report_sha256', report['entry'])
        # Full cycle proven: null invalidation -> TTL withdrawal HOLD -> recovery MOVE.
        # The suppressed_hold at step 210 followed by the recovery MOVE at 250 is also
        # the regression for the bounded hold window (a future recovery must not
        # invalidate an earlier occlusion hover).
        gate = report['loss_hold']
        self.assertEqual(gate['gate'], 'closed')
        self.assertEqual((gate['cycles'], gate['moves'], gate['holds']), (1, 2, 3))
        self.assertEqual(gate['frames_verified'], 4)
        self.assertFalse(any(u.startswith('loss_hold_correlation')
                             for u in report['uncovered']))
        self.assertTrue(any(u.startswith('native_setpoint_correlation')
                            for u in report['uncovered']))

    def test_run_root_entry(self):
        root, inject = make_run(self)
        report = audit(root, run_root=root / 'run', **inject)
        self.assertEqual(report['status'], 'pending')
        self.assertIn('run_root', report['entry'])
        self.assertIsNone(report['loss_hold'])  # No capture report layer, gate not run.
        self.assertTrue(any(u.startswith('loss_hold_correlation')
                            for u in report['uncovered']))

    def test_loss_hold_gate_not_exercised_keeps_uncovered(self):
        root, inject = make_run(self, bare=True)
        report = audit(root, **inject)
        self.assertEqual(report['status'], 'pending')
        self.assertEqual(report['loss_hold']['gate'], 'not_exercised')
        self.assertTrue(any(u.startswith('loss_hold_correlation')
                            for u in report['uncovered']))

    def test_moves_without_invalidation_do_not_close(self):
        root, inject = make_run(self, no_loss=True)
        report = audit(root, **inject)
        self.assertEqual(report['loss_hold']['gate'], 'not_exercised')
        self.assertTrue(any(u.startswith('loss_hold_correlation')
                            for u in report['uncovered']))

    def test_withdrawal_without_recovery_does_not_close(self):
        root, inject = make_run(self, no_recovery=True)
        report = audit(root, **inject)
        self.assertEqual(report['loss_hold']['gate'], 'not_exercised')
        self.assertTrue(any(u.startswith('loss_hold_correlation')
                            for u in report['uncovered']))

    def test_expired_move_hold_closes_without_new_link(self):
        root, inject = make_run(self, expire_hold=True)
        report = audit(root, **inject)
        self.assertEqual(report['loss_hold']['gate'], 'closed')
        self.assertFalse(any(u.startswith('loss_hold_correlation')
                             for u in report['uncovered']))

    def test_consumed_expired_target_justifies_hold(self):
        root, inject = make_run(self, consume_expired=True)
        report = audit(root, **inject)
        self.assertEqual(report['loss_hold']['gate'], 'closed')

    def test_fresh_duplicate_record_is_legal(self):
        root, inject = make_run(self, with_duplicate=True)
        report = audit(root, **inject)
        self.assertEqual(report['loss_hold']['gate'], 'closed')

    def test_expired_duplicate_record_fails(self):
        root, inject = make_run(self, expired_duplicate=True)
        with self.assertRaisesRegex(ValueError, 'duplicate_record kept an expired MOVE'):
            audit(root, **inject)

    def test_final_hold_before_boundary_fails(self):
        root, inject = make_run(self, final_early=True)
        with self.assertRaisesRegex(ValueError, 'without invalidation, expiry or boundary'):
            audit(root, **inject)

    def test_move_at_episode_boundary_fails(self):
        root, inject = make_run(self, move_past_end=True)
        with self.assertRaisesRegex(ValueError, 'episode end must be the single final HOLD'):
            audit(root, **inject)

    def test_old_record_step_cannot_hide_current_episode_end(self):
        root, _ = make_run(self, with_duplicate=True)
        reports = {p.parent.name: json.loads(p.read_text())
                   for p in root.glob('run/epochs/*/tasks/*/*/result.json')}
        aruco = reports['px4']['task']['aruco']
        duplicate = next(a for a in aruco['adapter_actions'] if a['action'] == 'duplicate_record')
        duplicate['authority_now_step'] = aruco['binding']['episode_end_step']
        case = json.loads((root/'report.json').read_text())
        with self.assertRaisesRegex(ValueError, 'episode end must be the single final HOLD'):
            audit_mod.loss_hold_chain(root, case, run_id=RUN, epoch=EPOCH, reports=reports, chains={})

    def test_tampered_frame_png_fails(self):
        root, inject = make_run(self, tamper_png=True)
        with self.assertRaisesRegex(ValueError, 'PNG rehash differs'):
            audit(root, **inject)

    def test_frame_path_escape_fails(self):
        root, inject = make_run(self, escape_path=True)
        with self.assertRaisesRegex(ValueError, 'escapes the capture-root boundary'):
            audit(root, **inject)

    def test_unmapped_move_fails(self):
        root, inject = make_run(self, unmapped_move=True)
        with self.assertRaisesRegex(ValueError, 'MOVE without its consumed observation link'):
            audit(root, **inject)

    def test_move_after_expiry_fails(self):
        root, inject = make_run(self, move_after_expiry=True)
        with self.assertRaisesRegex(ValueError, 'validity expired'):
            audit(root, **inject)

    def test_old_frame_refeed_fails(self):
        root, inject = make_run(self, old_frame=True)
        with self.assertRaisesRegex(ValueError, 'Old frame re-fed'):
            audit(root, **inject)

    def test_unjustified_hold_fails(self):
        root, inject = make_run(self, unjustified_hold=True)
        with self.assertRaisesRegex(ValueError, 'without invalidation, expiry or boundary'):
            audit(root, **inject)

    def test_orphan_suppressed_hold_fails(self):
        root, inject = make_run(self, orphan_suppress=True)
        with self.assertRaisesRegex(ValueError, 'suppressed_hold without a prior'):
            audit(root, **inject)

    def test_move_consuming_null_observation_fails(self):
        root, inject = make_run(self, move_on_null=True)
        with self.assertRaisesRegex(ValueError, 'MOVE consumed a null observation'):
            audit(root, **inject)

    def test_observation_identity_mismatch_fails(self):
        root, inject = make_run(self, bad_obs_identity=True)
        with self.assertRaisesRegex(ValueError, 'observation identity differs'):
            audit(root, **inject)

    def test_lax_step_string_fails(self):
        root, inject = make_run(self, lax_step=True)
        with self.assertRaisesRegex(ValueError, 'not a strict decimal step'):
            audit(root, **inject)

    def test_entry_target_drift_fails(self):
        root, inject = make_run(self, entry_target_drift=True)
        with self.assertRaisesRegex(ValueError, 'Frame entry target differs'):
            audit(root, **inject)

    def test_task_binding_boundary_mismatch_fails(self):
        root, inject = make_run(self, bad_task_binding=True)
        with self.assertRaisesRegex(ValueError, 'Task binding differs'):
            audit(root, **inject)

    def test_profile_file_mismatch_fails(self):
        root, inject = make_run(self, bad_profile_file=True)
        with self.assertRaisesRegex(ValueError, 'Frozen profile identity differs'):
            audit(root, **inject)

    def test_sensor_id_type_mismatch_fails(self):
        root, inject = make_run(self, bad_sensor_type=True)
        with self.assertRaisesRegex(ValueError, 'Binding camera identity differs'):
            audit(root, **inject)

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
        root, inject = make_run(self)
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


SCENE03 = ROOT / 'validation' / '40-aruco-flight-scene-03'


class RealSceneFramesTest(unittest.TestCase):
    """Real retained scene-03 frames through the auditor's frame/observation verifier.

    Observations are generated exactly as run_aruco_tracking.observation() builds
    them; the binding is synthesized from the frames' own identities. This pins
    the REAL schema (decimal-string metadata/target steps, string sensor_id, int
    valid_until_step) instead of fixture-invented int targets.
    """
    @unittest.skipUnless((SCENE03 / 'report.json').is_file(),
                         'retained 40-aruco-flight-scene-03 capture missing')
    def test_real_frames_pass_and_tamper_fails(self):
        report = json.loads((SCENE03 / 'report.json').read_text(encoding='utf-8'))
        frames = report['frames'][:5]
        notice = frames[0]['frame']['notification']
        binding = dict(schema='wksim.aruco-binding.v1', run_id=notice['run_id'],
                       epoch=notice['epoch'], instance_id=notice['instance_id'],
                       generation=notice['generation'], stream_id=notice['stream_id'],
                       camera=dict(vehicle_id=2, sensor_id='front_rgb'),
                       first_step=0, profile_sha256='0' * 64)
        observations = [dict(schema='wksim.aruco-observation.v1', run_id=notice['run_id'],
                             epoch=notice['epoch'], instance_id=notice['instance_id'],
                             generation=notice['generation'], stream_id=notice['stream_id'],
                             sequence=index,
                             capture_step=int(entry['frame']['metadata']['step']),
                             frame_id=int(entry['frame']['metadata']['frame_id']),
                             target=entry['target'], image_sha256=entry['image_sha256'])
                        for index, entry in enumerate(frames, 1)]
        detected = [entry['target'] for entry in frames if entry['target'] is not None]
        self.assertTrue(detected, 'scene-03 retained frames lack a real detected target')
        # Pin the real contract the review cited: decimal strings + string sensor id.
        self.assertIsInstance(frames[0]['frame']['metadata']['step'], str)
        self.assertIsInstance(frames[0]['frame']['metadata']['sensor_id'], str)
        self.assertIsInstance(detected[0]['step'], str)
        self.assertIsInstance(detected[0]['frame_id'], str)
        self.assertIsInstance(detected[0]['valid_until_step'], int)
        verified = audit_mod._verify_frames(SCENE03, frames, observations, binding,
                                            binding['camera'], notice['epoch'])
        self.assertEqual(len(verified), 5)
        frames_t = json.loads(json.dumps(frames))
        observations_t = json.loads(json.dumps(observations))
        frames_t[0]['target']['step'] = '1'
        observations_t[0]['target']['step'] = '1'
        with self.assertRaisesRegex(ValueError, 'target step/frame differs'):
            audit_mod._verify_frames(SCENE03, frames_t, observations_t, binding,
                                     binding['camera'], notice['epoch'])


if __name__ == '__main__':
    unittest.main()
