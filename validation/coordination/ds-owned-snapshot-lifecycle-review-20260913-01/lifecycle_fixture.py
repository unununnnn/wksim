"""Pure-event fixture for the owned-scheduling snapshot lifecycle.

No model, ROS, WSL, compile or network. Every event carries the verbatim source line
that produces it, so the ordering claims are claims about the real control flow:

  v2 candidate (the gap)
    with ExitStack() as resources:                 (v2 line 907)
        resources.callback(owned_snapshot_after)   (v2 line 1094, registered LAST)
        ...
        clock.request(... action='stop' ...)       (v2 line 1244)
        for child in workers.values():
            child.stdin.close(); child.wait(...)   (v2 lines 1249-1250)  <- model close
    finally:
        cleanup_children(...)                      (v2 line 1262)
    # only now does the with-block unwind the ExitStack, so the after capture still
    # has not run when the model is closed and the groups are cleaned up.

  v3 candidate (the fix)
    with ExitStack() as resources:
        resources.callback(owned_snapshot_after_once)   (v3 line 1115, error backstop)
        ...
        owned_snapshot_after_once()                     (v3 line 1271, success path)
        clock.request(... action='stop' ...)            (v3 line 1273)
        for child in workers.values():
            child.stdin.close(); child.wait(...)        (v3 lines 1278-1279)
    finally:
        cleanup_children(...)                           (v3 line 1288)
    with an explicit once-state guard (v3 line 1088) and a per-phase validated flag
    (v3 line 1084) that the metadata refresh honours (v3 lines 1386-1396).
"""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

DIR = ROOT / 'validation/coordination/claude-owned-snapshot-wiring-20260913-01'
V1 = DIR / 'run_joint_flight-owned-snapshot-candidate.py.txt'
V2 = DIR / 'run_joint_flight-owned-snapshot-candidate-v2.py.txt'
V3 = DIR / 'run_joint_flight-owned-snapshot-candidate-v3.py.txt'
BASELINE = DIR / 'baseline-run_joint_flight-08e20642.py.txt'
HELPER = ROOT / 'tools/capture_owned_scheduling.py'
HELPER_PIN = 'a3f3baddbe6e77bed5727e840ef6a4c7066291ce5f50c706f848e7b1716f8e9e'

# source key -> (file, line, verbatim text) for the real lifecycle sites
ANCHORS = {
    'v2_exitstack_open':     (V2, 907,  'with ExitStack() as resources:'),
    'v2_after_registration': (V2, 1094, 'resources.callback(owned_snapshot_after)'),
    'v2_stop_action':        (V2, 1244, "clock.request(dict(version=1,epoch=clock.epoch,request_id=clock.last_request+1,action='stop'))"),
    'v2_model_close':        (V2, 1249, 'for child in workers.values():'),
    'v2_model_stdin_close':  (V2, 1250, 'child.stdin.close(); child.wait(timeout=3)'),
    'v2_pass_status':        (V2, 1252, "result['status']='pass'"),
    'v2_finally_cleanup':    (V2, 1262, 'cleanup_children(result, children, child_specs,'),
    'v2_retire_workers':     (V2, 233,  'def retire_model_workers(children, child_specs, *, timeout=3):'),
    'v2_retire_stdin_close': (V2, 252,  'stream.close()'),
    'v2_after_capture':      (V2, 1088, "outcome = owned_snapshot_capture('after')"),
    'v2_before_capture':     (V2, 1070, "outcome = owned_snapshot_capture('before')"),
    'v2_connect':            (V2, 1079, 'physics.connect()'),
    'v2_refresh_lookup':     (V2, 1355, "for phase in ('before', 'after'):"),
    'v2_refresh_adopt':      (V2, 1357, 'refreshed[phase] = (dict(file=path.name, sha256=digest(path))'),
    'v2_status_downgrade':   (V2, 1370, "if owned_snapshot and result['status'] == 'pass':"),
    'v3_exitstack_open':     (V3, 917,  'with ExitStack() as resources:'),
    'v3_once_def':           (V3, 1086, 'def owned_snapshot_after_once():'),
    'v3_once_guard':         (V3, 1088, "if meta.get('after_attempted'):"),
    'v3_validated_flag':     (V3, 1084, "meta[phase + '_validated'] = True  # only a validated capture earns this"),
    'v3_before_capture':     (V3, 1099, "owned_snapshot_capture('before')"),
    'v3_connect':            (V3, 1107, 'physics.connect()'),
    'v3_after_registration': (V3, 1115, 'resources.callback(owned_snapshot_after_once)'),
    'v3_success_after':      (V3, 1271, 'owned_snapshot_after_once()'),
    'v3_stop_action':        (V3, 1273, "clock.request(dict(version=1,epoch=clock.epoch,request_id=clock.last_request+1,action='stop'))"),
    'v3_model_close':        (V3, 1278, 'for child in workers.values():'),
    'v3_model_stdin_close':  (V3, 1279, 'child.stdin.close(); child.wait(timeout=3)'),
    'v3_pass_status':        (V3, 1281, "result['status']='pass'"),
    'v3_finally_cleanup':    (V3, 1291, 'cleanup_children(result, children, child_specs,'),
    'v3_refresh_validated':  (V3, 1386, "validated = bool(meta.get(phase + '_validated'))"),
    'v3_refresh_adopt':      (V3, 1388, 'refreshed[phase] = dict(file=path.name, sha256=digest(path),'),
    'v3_refresh_raw_note':   (V3, 1392, "refreshed[phase]['note'] = 'raw file retained; capture did not validate'"),
    'v3_refresh_missing':    (V3, 1394, "raise ValueError('validated %s capture file is missing' % phase)"),
    'helperside_write':      (HELPER, 462, 'with self.output.open("x", encoding="utf-8") as stream:'),
}

REQUIRED_ORDER = ['after_capture', 'stop_action', 'cleanup_children', 'model_close',
                  'exitstack_unwind']
FLIGHT_PHASES = ('exitstack_open', 'before_capture', 'connect', 'after_registration',
                 'success_after_call', 'stop_action', 'model_close', 'model_stdin_close',
                 'pass_status', 'exitstack_unwind', 'cleanup_children', 'retire_workers',
                 'retire_stdin_close')


def anchor_text(key):
    path, line, _ = ANCHORS[key]
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    return lines[line - 1].strip()


def anchors_verified():
    """The fixture only means something if every cited line still holds its text."""
    return {key: anchor_text(key) == expected
            for key, (_, _, expected) in ANCHORS.items()}


def source_variants():
    return {'v1': V1, 'v2': V2, 'v3': V3, 'baseline': BASELINE}


class Engine:
    """Traced model of the runner snapshot lifecycle.

    variant='v1'/'v2'            ExitStack-only after capture (the recorded gap)
    variant='v3'                 v3 call sites: explicit once-guarded success call,
                                 once-guarded ExitStack backstop, validated-flag refresh
    variant='v3-stale'           same, but the helper refuses before writing, to show a
                                 stale after file is not re-designated as captured
    variant='v3-legacy-refresh'  v3 call sites with v2's unguarded refresh, to isolate
                                 the capture-file acceptance question from the ordering
    """

    def __init__(self, variant='v2', *, live=None, children=('ap-model', 'px4-model'),
                 worker_stdin_pids=('ap-model',), after_mode='before-stop',
                 wrong_phase=None, capture_error=None, boot_changed=False,
                 stale_file=False, fail_before_capture=False, close_error=None):
        self.variant = variant
        self.anchor = 'v3' if variant.startswith('v3') else 'v2'
        self.live = Path(live) if live is not None else None
        self.children = list(children)
        self.worker_stdin_pids = set(worker_stdin_pids)
        self.after_mode = after_mode
        self.wrong_phase = wrong_phase
        self.capture_error = capture_error
        self.boot_changed = boot_changed
        self.stale_file = stale_file
        self.fail_before_capture = fail_before_capture
        self.close_error = close_error
        self.events = []
        self.after_attempts = 0
        self.after_validations = 0
        self.after_adopted_by_refresh = False
        self.connected = False
        self.result = {'status': None, 'children': {name: {} for name in self.children}}

    def v3(self):
        return self.anchor == 'v3'

    # --- event plumbing -----------------------------------------------------
    def _emit(self, name, source=None, **detail):
        line = ANCHORS[source][1] if source else None
        self.events.append(dict(seq=len(self.events) + 1, event=name, source=source,
                                line=line, **detail))

    def names(self):
        return [event['event'] for event in self.events]

    def first(self, name):
        return next((event for event in self.events if event['event'] == name), None)

    def count(self, name):
        return sum(1 for event in self.events if event['event'] == name)

    def order(self):
        return [event['event'] for event in self.events if event['event'] in REQUIRED_ORDER]

    def before_after(self):
        """Required events that happened before the after capture (any is a defect)."""
        order = self.order()
        if 'after_capture' not in order:
            return list(order)
        return order[:order.index('after_capture')]

    def after_after(self):
        order = self.order()
        if 'after_capture' not in order:
            return []
        return order[order.index('after_capture') + 1:]

    def phases(self, *names):
        wanted = names or FLIGHT_PHASES
        return [event['event'] for event in self.events if event['event'] in wanted]

    # --- lifecycle steps ----------------------------------------------------
    def capture(self, phase):
        """Mirror of owned_snapshot_capture() (v2 1037-1067 / v3 1047-1084)."""
        meta = self.result['owned_scheduling']
        v3 = self.v3()
        if phase == 'after':
            self.after_attempts += 1
        self._emit('before_capture_call' if phase == 'before' else 'after_capture_call',
                   source='v3_before_capture' if (v3 and phase == 'before') else
                          ('v2_before_capture' if phase == 'before' else 'v2_after_capture'))
        try:
            if phase == 'after' and self.capture_error is not None:
                raise self.capture_error
            if phase == 'after' and self.boot_changed:
                meta['after_error'] = "boot changed: %r != %r" % ('boot-b', 'boot-a')
                return None
            if phase == 'after' and self.stale_file and v3:
                raise ValueError('frozen targets missing for the after capture')
            written_phase = phase if v3 else (self.wrong_phase or phase)
            if self.live is not None:
                target = self.live / ('owned-scheduling-%s.json' % phase)
                if target.exists():
                    # mirrors the helper's exclusive create (mode 'x'): an existing
                    # file is never replaced, and a mismatching one is an error
                    raise FileExistsError('capture output already exists: %s' % target.name)
                target.write_text(
                    json.dumps(dict(schema='wksim.owned-scheduling-snapshot.v1',
                                    phase=written_phase, host={'boot_id': 'boot-a'})) + '\n',
                    encoding='utf-8')
            if v3:
                meta[phase] = 'owned-scheduling-%s.json' % phase
                meta[phase + '_validated'] = True
                if phase == 'after':
                    self.after_validations += 1
            self._emit('before_capture' if phase == 'before' else 'after_capture',
                       source='v3_before_capture' if (v3 and phase == 'before') else
                              ('v2_before_capture' if phase == 'before' else 'v2_after_capture'))
            return dict(name='owned-scheduling-%s.json' % phase)
        except Exception as error:  # mirrors the runner's `except Exception`
            meta[phase + '_error'] = repr(error)
            self._emit('before_capture_failed' if phase == 'before' else 'after_capture_failed',
                       source='v3_before_capture' if (v3 and phase == 'before') else
                              ('v2_before_capture' if phase == 'before' else 'v2_after_capture'),
                       error=repr(error))
            return None

    def after_once(self):
        """Mirror of v3 owned_snapshot_after_once() (v3 lines 1086-1095)."""
        meta = self.result['owned_scheduling']
        if self.v3() and self.variant != 'v3-legacy-refresh':
            if meta.get('after_attempted'):
                self._emit('after_skipped_once', source='v3_once_guard')
                return
            if not self.connected:
                # no before capture and no timed segment ever ran; the backstop must
                # not invent an after capture for a run that never connected
                self._emit('after_skipped_unconnected', source='v3_once_guard')
                return
            meta['after_attempted'] = True
            self._emit('after_attempted_flag', source='v3_once_guard')
        try:
            self.capture('after')
        except Exception as error:
            meta['after_error'] = repr(error)

    def run(self, *, connect=True, business_error=None, pause_complete=False):
        v3 = self.v3()
        meta = self.result.setdefault('owned_scheduling', dict(
            classification='diagnostic_only', full_acceptance=False, initialized=False,
            before=None, after=None, boot_id=None,
            helper='tools/capture_owned_scheduling.py'))
        try:
            with ExitStack() as resources:
                self._emit('exitstack_open',
                           source='v3_exitstack_open' if v3 else 'v2_exitstack_open')
                resources.callback(lambda: self._emit('rclpy_shutdown'))
                resources.callback(lambda: self._emit('node_destroy'))
                if v3:
                    resources.callback(self.after_once)
                    self._emit('after_registered', source='v3_after_registration')
                if not connect:
                    self._emit('connect_failed', source='v3_connect' if v3 else 'v2_connect')
                    raise RuntimeError('physics connect failed')
                self._emit('connect', source='v3_connect' if v3 else 'v2_connect')
                self.connected = True
                if self.fail_before_capture:
                    # v3 lines 1098-1103: an ordinary before-capture failure is recorded
                    self._emit('before_capture_failed', source='v3_before_capture')
                    self.result['owned_scheduling']['before_error'] = 'before capture failed'
                if not v3:
                    resources.callback(self.after_once)
                    self._emit('after_registered', source='v2_after_registration')
                if pause_complete:
                    raise LookupError('PauseProbeComplete')
                if business_error is not None:
                    raise business_error
                # ---- success path tail ----
                if v3 and self.after_mode == 'before-stop':
                    self._emit('success_after_call', source='v3_success_after')
                    self.after_once()
                self._emit('stop_action', source='v3_stop_action' if v3 else 'v2_stop_action')
                if v3 and self.after_mode == 'after-stop':
                    self.after_once()
                self._emit('model_close', source='v3_model_close' if v3 else 'v2_model_close')
                for child in self.children:
                    self._emit('model_stdin_close',
                               source='v3_model_stdin_close' if v3 else 'v2_model_stdin_close',
                               child=child)
                if self.close_error is not None:
                    # v3 lines 1278-1280: a model that does not close normally raises,
                    # and the already-attempted after capture must stay the only one
                    raise self.close_error
                self.result['status'] = 'pass'
                self._emit('pass_status', source='v3_pass_status' if v3 else 'v2_pass_status')
            self._emit('exitstack_unwind')
        except BaseException as error:
            self._emit('exception_caught', error=repr(error))
            if self.variant == 'v3-legacy-refresh':
                self.after_once()
            self.result['error'] = repr(error)
            if self.result['status'] is None:
                self.result['status'] = 'failed'
        finally:
            self.cleanup_children()
        self.refresh()
        return self.result

    def cleanup_children(self):
        """Mirror of cleanup_children() -> retire_model_workers() (v2 217-262 / v3 243-288)."""
        self._emit('cleanup_children',
                   source='v3_finally_cleanup' if self.v3() else 'v2_finally_cleanup')
        for child in self.children:
            if child in self.worker_stdin_pids:
                self._emit('retire_workers', source='v2_retire_workers', child=child)
                self._emit('retire_stdin_close', source='v2_retire_stdin_close', child=child)

    def refresh(self):
        """Mirror of the metadata refresh: v2 lines 1350-1369, v3 lines 1379-1407."""
        meta = self.result['owned_scheduling']
        guarded = self.v3() and self.variant != 'v3-legacy-refresh'
        refreshed = {}
        for phase in ('before', 'after'):
            path = self.live / ('owned-scheduling-%s.json' % phase) if self.live else None
            exists = bool(path and path.is_file())
            self._emit('refresh_lookup', source='v2_refresh_lookup', phase=phase, exists=exists)
            if not guarded:
                # v2: any file at the path is re-labelled with name+sha256
                if exists:
                    refreshed[phase] = dict(file=path.name,
                                            sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                    if phase == 'after':
                        self.after_adopted_by_refresh = True
                    self._emit('refresh_adopt', source='v2_refresh_adopt', phase=phase)
                else:
                    refreshed[phase] = None
                continue
            # v3: the validated flag decides whether a file may be presented as evidence
            validated = bool(meta.get(phase + '_validated'))
            self._emit('refresh_validated', source='v3_refresh_validated', phase=phase,
                       validated=validated)
            if exists:
                refreshed[phase] = dict(file=path.name,
                                        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                        validated=validated)
                if not validated:
                    refreshed[phase]['note'] = 'raw file retained; capture did not validate'
                    self._emit('refresh_raw_note', source='v3_refresh_raw_note', phase=phase)
                elif phase == 'after':
                    self.after_adopted_by_refresh = True
                self._emit('refresh_adopt', source='v3_refresh_adopt', phase=phase,
                           validated=validated)
            elif validated:
                meta['metadata_error'] = 'validated %s capture file is missing' % phase
                self._emit('refresh_missing', source='v3_refresh_missing', phase=phase)
            else:
                refreshed[phase] = None
        meta.update(refreshed)
        if self.result['status'] == 'pass':
            self.result['status'] = 'observed'
            self._emit('status_downgrade', source='v2_status_downgrade')
