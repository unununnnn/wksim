"""Read-only console projections; no ROS, processes, publishers or clock mapping."""
from collections import deque
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import time
import re

from ..wksim_runtime import replay
from ..wksim_runtime.config import _unique_object


TAIL_BYTES = 256 * 1024
STALE_AFTER_S = 2.0
SESSION_TOPIC = '/uav1/prometheus/v2/state'
CLOCKS = {
    'source_age_at_publish_s': 'WSL monotonic: published minus source_received',
    'host_observation_age_s': 'host monotonic elapsed since observed source advancement',
    'mapping': 'unknown between host monotonic, WSL monotonic, FC boot and wall clocks; '
               'host observation age is not transport latency or flight readiness',
}


def _integer(value):
    return type(value) is int


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _decode(raw):
    # Keep exact raw_json alongside JSON-safe nonfinite markers, as replay does.
    invalid = []

    def constant(token):
        invalid.append(token)
        return {'nonfinite': token}

    def number(token):
        value = float(token)
        return value if math.isfinite(value) else constant(token)

    row = json.loads(raw, parse_constant=constant, parse_float=number, object_pairs_hook=_unique_object)
    if not isinstance(row, dict):
        raise ValueError('record must be an object')
    return row, invalid


def read_result(path):
    """Native reports may contain NaN for absent telemetry. Preserve exact text.

    The API envelope is strict JSON, while values use explicit nonfinite markers.
    This never rewrites a native result or turns an unknown field into a number.
    """
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 32*1024*1024:
        raise ValueError('Unsafe or oversized result file')
    raw = path.read_bytes()
    if len(raw) > 32*1024*1024:
        raise ValueError('Result grew beyond the size limit')
    value, invalid = _decode(raw)
    return dict(format_version=1, values=value, raw_json=raw.decode('utf-8'),
                sha256=hashlib.sha256(raw).hexdigest(),
                diagnostics=[dict(code='nonfinite_values',values=sorted(set(invalid)))] if invalid else [])


class _Tail:
    """Bounded incremental reads with a cursor anchor to detect in-place rewrites."""

    def __init__(self, path):
        self.path = path
        self.identity = None
        self.offset = 0
        self.anchor = b''

    def read(self, diagnose):
        rows, interrupted = [], False
        try:
            if self.path.resolve().parent != self.path.parent.resolve():
                raise ValueError('Refusing evidence outside run directory')
            with self.path.open('rb') as source:
                stat = os.fstat(source.fileno())
                identity = (stat.st_dev, stat.st_ino)
                changed = self.identity is not None and identity != self.identity
                truncated = stat.st_size < self.offset
                if self.anchor and not changed and not truncated:
                    source.seek(self.offset - len(self.anchor))
                    truncated = source.read(len(self.anchor)) != self.anchor
                if changed or truncated:
                    diagnose('log_rotated' if changed else 'log_truncated', self.path.name)
                    self.offset, self.anchor = 0, b''
                    interrupted = True
                self.identity = identity
                if stat.st_size - self.offset > TAIL_BYTES:
                    self.offset = stat.st_size - TAIL_BYTES
                    source.seek(self.offset - 1)
                    boundary = source.read(1) == b'\n'
                    diagnose('tail_window_skipped', self.path.name)
                    interrupted = True
                else:
                    boundary = True
                source.seek(self.offset)
                data = source.read(TAIL_BYTES)
                end = data.rfind(b'\n') + 1
                if end != len(data):
                    diagnose('partial_tail', self.path.name)
                    interrupted = True
                complete = data[:end]
                self.offset += end
                source.seek(max(0, self.offset - 4096))
                self.anchor = source.read(min(4096, self.offset))
                lines = complete.splitlines()
                if not boundary and lines:
                    lines = lines[1:]
                for line in lines:
                    try:
                        raw = line.decode('utf-8')
                        row, invalid = _decode(raw)
                        rows.append((row, raw, invalid))
                    except (ValueError, UnicodeError, RecursionError) as error:
                        diagnose('malformed_record', self.path.name, str(error))
                        interrupted = True
        except (OSError, ValueError) as error:
            diagnose('missing_file' if isinstance(error, FileNotFoundError) else 'read_error',
                     self.path.name, str(error))
            interrupted = True
        return rows, interrupted


class LiveRunReader:
    """Project the pinned run/first valid epoch, requiring cross-poll advancement.

    Epoch replacement is latched stale: this reader cannot authorize a new task.
    Invalid matching packets remain visible with their raw text and diagnostics.
    """

    def __init__(self, directory, run_id):
        if not isinstance(run_id, str) or not run_id:
            raise ValueError('run_id must be a nonempty string')
        self.directory, self.run_id = Path(directory), run_id
        self.tails = {name: _Tail(self.directory / (name + '.jsonl'))
                      for name in ('prometheus', 'mission')}
        self.diagnostics = deque(maxlen=100)
        self.events = deque(maxlen=50)
        self.mission = self.packet = self.raw_json = None
        self.epoch = None
        self.sequence = 0
        self.signature = None
        self.observed_at = None
        self.qualified = self.invalid = self.epoch_changed = False
        self.source_age = None

    def _diagnose(self, code, file='prometheus.jsonl', detail=None):
        record = {'code': code, 'file': file}
        if detail is not None:
            record['detail'] = detail
        if not self.diagnostics or self.diagnostics[-1] != record:
            self.diagnostics.append(record)

    def _identity(self, row, *, mission=False):
        version = row.get('version')
        epoch = row.get('control_epoch')
        if not _integer(version) or version != 1 or row.get('run_id') != self.run_id:
            return False
        return ((mission and epoch is None) or
                (isinstance(epoch, str) and re.fullmatch('[0-9a-f]{32}', epoch) and
                 (self.epoch is None or epoch == self.epoch)))

    def _mission(self):
        path = self.directory / 'mission-status.json'
        try:
            if path.resolve().parent != self.directory.resolve():
                raise ValueError('Refusing mission status outside run directory')
            with path.open('rb') as source:
                data = source.read(TAIL_BYTES + 1)
            if len(data) > TAIL_BYTES:
                raise ValueError('mission status exceeds projection limit')
            row, invalid = _decode(data)
            if invalid or not self._identity(row, mission=True):
                raise ValueError('Invalid mission status values or identity')
            self.mission = row
        except (OSError, ValueError, UnicodeError, RecursionError) as error:
            self.mission = None
            self._diagnose('missing_file' if isinstance(error, FileNotFoundError)
                           else 'invalid_mission_status', path.name, str(error))

    def _session(self, row, raw, nonfinite, now, previous_signature):
        msg = row.get('message')
        if not isinstance(msg, dict) or not self._identity(msg):
            if (isinstance(msg, dict) and msg.get('run_id') == self.run_id
                    and self.epoch is not None and msg.get('control_epoch') != self.epoch):
                self.epoch_changed = True
            self.invalid = True
            self._diagnose('session_identity_mismatch')
            return
        seq = msg.get('sequence')
        if not _integer(seq) or not 0 < seq < 2**64 or seq < self.sequence:
            self.invalid = True
            self._diagnose('invalid_or_regressed_sequence')
            return
        if seq == self.sequence:
            self._diagnose('duplicate_sequence')
            if msg != self.packet:
                self.invalid = True
                self._diagnose('conflicting_duplicate_sequence')
            return
        self.epoch, self.sequence = msg['control_epoch'], seq
        self.packet, self.raw_json = msg, raw
        self.source_age = None
        self.invalid = True
        state, control = msg.get('state'), msg.get('control')
        received, published = msg.get('source_received_monotonic_s'), msg.get('published_monotonic_s')
        if _finite(received) and _finite(published):
            age = published - received
            self.source_age = age if _finite(age) else None
        if nonfinite:
            self._diagnose('nonfinite_values', detail=','.join(sorted(set(nonfinite))))
        if (not isinstance(state, dict) or not isinstance(control, dict)
                or msg.get('source_received_valid') is not True
                or self.source_age is None or not 0 <= self.source_age <= STALE_AFTER_S
                or received < 0 or published < 0):
            self._diagnose('invalid_session_values')
            return
        header = state.get('header')
        stamp = header.get('stamp') if isinstance(header, dict) else None
        if (state.get('connected') is not True or state.get('odom_valid') is not True
                or type(state.get('armed')) is not bool
                or type(state.get('uav_id')) is not int or state['uav_id'] != 1
                or not isinstance(header, dict) or header.get('frame_id') != 'map' or not isinstance(stamp, dict)
                or not _integer(stamp.get('sec')) or not _integer(stamp.get('nanosec'))
                or stamp['sec'] < 0 or not 0 <= stamp['nanosec'] < 10**9
                or any(not isinstance(state.get(key), list) or len(state[key]) != 3
                       or not all(_finite(v) for v in state[key])
                       for key in ('position', 'velocity', 'attitude'))):
            self._diagnose('invalid_public_state')
            return
        if (type(control.get('uav_id')) is not int or control['uav_id'] != 1
                or type(control.get('control_state')) is not int
                or type(control.get('failsafe')) is not bool):
            self._diagnose('invalid_public_control')
            return
        boot = stamp['sec'] * 10**9 + stamp['nanosec']
        if boot <= 0 or msg.get('source_clock') != 'fc_boot':
            self._diagnose('unknown_or_invalid_source_clock')
            return
        signature = (received, boot)
        if self.signature is not None and any(a <= b for a, b in zip(signature, self.signature)):
            self._diagnose('source_frozen_or_regressed')
            return
        self.signature, self.observed_at = signature, now
        self.invalid = False
        # Multiple rows already on disk in one poll cannot prove live progression.
        if previous_signature is not None and all(a > b for a, b in zip(signature, previous_signature)):
            self.qualified = True

    def _action_offer(self, freshness):
        """A conservative host projection, not authority to fly or an ACK.

        Never compare host and WSL monotonic origins. Require actual cross-poll
        source advancement and matching mission/native identities; the runtime
        still validates its own live state when consuming a submitted request.
        """
        offer = dict(version=1, mission_id=None, action_token=None, control_epoch=None,
                     native_generation=None, allowed_actions=[], reason='feedback_not_live')
        if freshness != 'live':
            return offer
        mission, packet = self.mission or {}, self.packet or {}
        if any(not isinstance(mission.get(key), str) or re.fullmatch('[0-9a-f]{32}', mission[key]) is None
               for key in ('mission_id', 'action_token', 'control_epoch')):
            return dict(offer, reason='missing_mission_identity')
        generation = mission.get('native_generation')
        if (not _integer(generation) or not 0 <= generation < 2**64
                or not _integer(packet.get('native_generation'))
                or generation != packet['native_generation']
                or mission['control_epoch'] != packet.get('control_epoch')):
            return dict(offer, reason='generation_mismatch')
        offer.update({key: mission[key] for key in ('mission_id', 'action_token', 'control_epoch', 'native_generation')})
        action = {'takeover': 'pause', 'running': 'pause', 'paused': 'resume'}.get(mission.get('state'))
        if action is None:
            return dict(offer, reason='mission_not_actionable')
        if mission.get('allowed_actions') != [action]:
            return dict(offer, reason='action_not_offered')
        state, control = packet.get('state', {}), packet.get('control', {})
        if state.get('armed') is not True:
            return dict(offer, reason='not_armed')
        if action == 'pause' and (control.get('control_state') != 2 or control.get('failsafe') is not False
                                   or state.get('mode') not in ('OFFBOARD', 'GUIDED')):
            return dict(offer, reason='task_control_not_observed')
        return dict(offer, allowed_actions=[action], reason='ready')

    def poll(self, terminal=False):
        now = time.monotonic()
        previous_signature = self.signature
        rows, interrupted = self.tails['prometheus'].read(self._diagnose)
        if interrupted:
            self.qualified = False
            previous_signature = None
        for row, raw, invalid in rows:
            if row.get('topic') == SESSION_TOPIC:
                self._session(row, raw, invalid, now, previous_signature)
            elif row.get('topic') == '/uav1/prometheus/text_info':
                msg = row.get('message')
                try:
                    event, bad = _decode(msg['message'])
                    if (bad or event.get('run_id') != self.run_id or self.epoch is None
                            or event.get('control_epoch') != self.epoch):
                        raise ValueError('Event identity or values invalid')
                    self.events.append({'stream': 'prometheus', 'payload': row, 'raw_json': raw})
                except (TypeError, KeyError, ValueError, RecursionError):
                    self._diagnose('invalid_text_event')
        self._mission()
        mission_rows, _ = self.tails['mission'].read(self._diagnose)
        for row, raw, invalid in mission_rows:
            if not invalid and self._identity(row, mission=True):
                self.events.append({'stream': 'mission', 'payload': row, 'raw_json': raw})
            else:
                self._diagnose('invalid_mission_event', 'mission.jsonl')
        age = None if self.observed_at is None else now - self.observed_at
        status = 'waiting'
        if self.invalid or self.epoch_changed or (age is not None and age > STALE_AFTER_S):
            status = 'stale'
        elif interrupted and self.packet is not None:
            status = 'stale'
        elif self.qualified:
            status = 'live'
        if terminal:
            status = 'recorded'
        packet = self.packet or {}
        return deepcopy({'mission': self.mission,
                         'action_offer': self._action_offer(status),
                         'state': packet.get('state') if isinstance(packet.get('state'), dict) else None,
                         'control': packet.get('control') if isinstance(packet.get('control'), dict) else None,
                         'events': list(self.events),
                         'raw': self.packet, 'raw_json': self.raw_json,
                         'freshness': {'status': status, 'source_age_at_publish_s': self.source_age,
                                       'host_observation_age_s': age, 'clock': CLOCKS},
                         'diagnostics': list(self.diagnostics)})


def replay_page(directory, stream='prometheus', offset=0, limit=50):
    """Page the existing offline loader without transforming or writing evidence."""
    if not isinstance(stream, str) or stream not in replay.STREAMS:
        raise ValueError('Unknown evidence stream')
    if not _integer(offset) or offset < 0:
        raise ValueError('offset must be a nonnegative integer')
    if not _integer(limit) or not 1 <= limit <= 100:
        raise ValueError('limit must be an integer between 1 and 100')
    evidence = replay.load_evidence(directory)
    records = [row for row in evidence['records'] if row['stream'] == stream]
    return {'records': records[offset:offset + limit], 'diagnostics': evidence['diagnostics'],
            'total': len(records), 'offset': offset, 'limit': limit}
