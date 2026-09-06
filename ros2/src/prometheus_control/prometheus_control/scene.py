# SPDX-License-Identifier: Apache-2.0
"""Opt-in scene permission. It carries time identity, never advances physics.

Same-host monotonic timestamps are valid only in the private joint ROS graph.
An expired scene cannot revive through a later heartbeat. Communication-fault
recovery needs a new explicit request and never restores prior task ownership.
Clock regression and incomplete state remain terminal until a new epoch.
"""
import json
import re
import time

TOPIC = '/wksim/scene/lifecycle'
PERIOD_SECONDS, LEASE_SECONDS = .1, .5
PHASES = frozenset(('running', 'paused', 'stepping', 'resuming', 'recovering', 'faulted', 'stopped'))
FIELDS = frozenset(('version', 'run_id', 'scene_epoch', 'sequence', 'request_id', 'phase',
                    'tick', 'time_ns', 'issued_monotonic_s', 'lease_seconds'))


class SceneLease:
    def __init__(self, run_id, scene_epoch, clock=time.monotonic):
        if (not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', run_id)
                or not isinstance(scene_epoch, str) or not re.fullmatch('[0-9a-f]{32}', scene_epoch)):
            raise ValueError('Invalid explicit scene/run identity')
        self.run_id, self.epoch, self.clock = run_id, scene_epoch, clock
        self.value, self.error = None, None

    def accept(self, payload):
        if not isinstance(payload, str) or len(payload.encode()) > 4096:
            raise ValueError('Invalid scene permission frame')
        def pairs(items):
            values = {}
            for key, value in items:
                if key in values:
                    raise ValueError('Duplicate scene permission field')
                values[key] = value
            return values
        value = json.loads(payload, object_pairs_hook=pairs)
        expected_fields=FIELDS|{'faulted_uav_ids'} if isinstance(value,dict) and value.get('version')==2 else FIELDS
        if not isinstance(value, dict) or set(value) != expected_fields:
            raise ValueError('Unexpected scene permission fields')
        if value['run_id'] != self.run_id or value['scene_epoch'] != self.epoch:
            return False  # Foreign/retired envelopes cannot bind or refresh this scene.
        if self.value is not None and type(value['sequence']) is int and value['sequence'] <= self.value['sequence']:
            return False  # Delayed old leases cannot revoke or refresh newer authority.
        now = self.clock()
        faulted_ids=value.get('faulted_uav_ids',[])
        if (type(value['version']) is not int or value['version'] not in (1,2)
                or not isinstance(faulted_ids,list) or len(faulted_ids)>2
                or any(type(uid) is not int or uid not in (1,2) for uid in faulted_ids)
                or len(set(faulted_ids))!=len(faulted_ids)
                or any(type(value[key]) is not int or not 0 <= value[key] < 2**63
                       for key in ('sequence', 'request_id', 'tick', 'time_ns'))
                or value['sequence'] == 0 or not isinstance(value['phase'], str) or value['phase'] not in PHASES
                or value['time_ns'] != value['tick']*1000000
                or type(value['issued_monotonic_s']) not in (float, int)
                or not now-LEASE_SECONDS <= value['issued_monotonic_s'] <= now
                or type(value['lease_seconds']) not in (float, int) or value['lease_seconds'] != LEASE_SECONDS):
            raise ValueError('Invalid or expired scene permission')
        previous = self.value
        if previous is not None and value['version']!=previous['version']:
            raise ValueError('Scene protocol version changed without a new epoch')
        if (previous is not None and faulted_ids!=previous.get('faulted_uav_ids',[])
                and value['phase']!='faulted'):
            raise ValueError('Native retirement scope may change only on a recorded fault')
        recovering = (previous is not None and value['phase'] == 'recovering'
                      and previous['phase'] != 'recovering'
                      and value['request_id'] > previous['request_id']
                      and (previous['phase'] == 'faulted' or self.error in
                           ('scene_permission_expired_no_automatic_recovery', 'scene_faulted_control_released')))
        if self.error and not recovering:
            raise ValueError(self.error)
        if (value['phase'] == 'recovering' and not recovering
                and (previous is None or previous['phase'] != 'recovering')):
            raise ValueError('scene_recovery_requires_new_fault_request')
        if previous is not None:
            if value['sequence'] <= previous['sequence']:
                return False
            if recovering:
                if (value['tick'] < previous['tick'] or value['issued_monotonic_s'] < previous['issued_monotonic_s']
                        or self.error not in (None,'scene_permission_expired_no_automatic_recovery','scene_faulted_control_released')):
                    raise ValueError('scene_recovery_cannot_repair_regressed_or_invalid_state')
                self.error = None
            elif now-previous['issued_monotonic_s'] > LEASE_SECONDS:
                self.error = 'scene_permission_expired_no_automatic_recovery'
            elif (value['tick'] < previous['tick'] or value['request_id'] < previous['request_id']
                    or value['issued_monotonic_s'] < previous['issued_monotonic_s']):
                self.error = 'scene_time_or_request_regressed'
            elif (previous['phase'] == value['phase'] == 'paused' and previous['tick'] != value['tick']):
                self.error = 'paused_scene_time_advanced_without_step'
            elif (previous['phase'] != value['phase'] and value['request_id'] == previous['request_id']
                    and (previous['phase'], value['phase']) not in
                    (('stepping', 'paused'), ('resuming', 'running'), ('recovering', 'running'))
                    and value['phase'] not in ('faulted', 'stopped')):
                self.error = 'scene_transition_without_new_request'
            if self.error:
                raise ValueError(self.error)
        self.value = value
        return True

    def check(self):
        if self.error:
            raise ValueError(self.error)
        if self.value is None:
            raise ValueError('scene_permission_not_received')
        age = self.clock()-self.value['issued_monotonic_s']
        if not 0 <= age <= LEASE_SECONDS:
            self.error = 'scene_permission_expired_no_automatic_recovery'
        elif self.value['phase'] in ('faulted', 'stopped'):
            self.error = 'scene_'+self.value['phase']+'_control_released'
        if self.error:
            raise ValueError(self.error)
        return self.value
