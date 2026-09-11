"""Offline proof cases for the diagnostic first-step capture gate."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT/'validation/rate-remediation-ff63c72/sitecustomize.py'


def load_hook():
    spec = importlib.util.spec_from_file_location('wksim_scheduler_gate_hook', HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FirstStepGateTests(unittest.TestCase):
    def test_hook_publishes_tick_zero_release_bound_to_bootstrap_token(self):
        hook = load_hook()
        epoch = 'a'*32
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); capture = root/'capture'; capture.mkdir()
            ready = root/'gate-ready.json'; release = root/'gate-release.json'
            token = capture/'capture-bootstrap-active.json'
            owner = dict(schema='wksim.private-tracefs.instance-owner.v1',
                         collector_pid=456, collector_start_ticks=457,
                         supervisor_pid=os.getpid(), supervisor_start_ticks=789,
                         instance='/sys/kernel/tracing/instances/wksim-rate-'+epoch,
                         instance_inode=[1, 2], run_id='run', epoch=epoch)
            active = dict(schema='wksim.private-tracefs.capture-bootstrap-active.v1',state='bootstrap_active',phase='bootstrap_sched_switch',
                          collector_pid=456, collector_start_ticks=457,
                          supervisor_pid=os.getpid(), supervisor_start_ticks=789,
                          instance=owner['instance'], instance_inode=[1, 2],
                          run_id='run', epoch=epoch, started_monotonic_ns=100,
                          )
            (capture/'instance-owner.json').write_text(json.dumps(owner))
            active['instance_owner_sha256'] = hashlib.sha256(
                (capture/'instance-owner.json').read_bytes()).hexdigest()
            active['published_monotonic_ns'] = 200
            token.write_text(json.dumps(active,sort_keys=True)+'\n')
            hook.run_id, hook.epoch = 'run', epoch
            previous = os.environ.copy()
            try:
                os.environ.update(WKSIM_TRACE_GATE_READY=str(ready),
                                  WKSIM_TRACE_GATE_RELEASE=str(release),
                                  WKSIM_TRACE_CAPTURE_BOOTSTRAP_TOKEN=str(token),
                                  WKSIM_TRACE_CAPTURE_ACTIVE_TOKEN=str(capture/'capture-active.json'))
                frame = SimpleNamespace(f_locals={'self': SimpleNamespace(clock=SimpleNamespace(tick=0))})
                with patch.object(hook, '_self_start_ticks', return_value=789):
                    hook._first_step_gate(frame)
            finally:
                os.environ.clear(); os.environ.update(previous)
            ready_value = json.loads(ready.read_text())
            release_value = json.loads(release.read_text())
            self.assertEqual(ready_value['tick'], 0)
            self.assertEqual(release_value['run_id'], 'run')
            self.assertEqual(release_value['epoch'], epoch)
            self.assertEqual(release_value['collector_pid'], 456)
            self.assertEqual(release_value['collector_start_ticks'], 457)
            self.assertEqual(release_value['supervisor_start_ticks'], 789)
            self.assertEqual(release_value['instance_owner_sha256'],
                             active['instance_owner_sha256'])
            self.assertEqual(release_value['capture_token_sha256'],
                             hashlib.sha256(token.read_bytes()).hexdigest())
            self.assertEqual(release_value['capture_token_schema'], active['schema'])

    def test_hook_fails_closed_when_first_step_is_not_tick_zero(self):
        hook = load_hook()
        frame = SimpleNamespace(f_locals={'self': SimpleNamespace(clock=SimpleNamespace(tick=1))})
        with self.assertRaisesRegex(RuntimeError, 'requires clock tick 0'):
            hook._first_step_gate(frame)

    def test_hook_accepts_bootstrap_token_and_labels_release_boundary(self):
        hook = load_hook()
        epoch='a'*32
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); capture=root/'capture'; capture.mkdir()
            ready=root/'gate-ready.json'; release=root/'gate-release.json'
            token=capture/'capture-bootstrap-active.json'
            owner=dict(schema='wksim.private-tracefs.instance-owner.v1',collector_pid=456,
                       collector_start_ticks=457,supervisor_pid=os.getpid(),supervisor_start_ticks=789,
                       instance='/sys/kernel/tracing/instances/wksim-rate-'+epoch,
                       instance_inode=[1,2],run_id='run',epoch=epoch)
            owner_path=capture/'instance-owner.json'; owner_path.write_text(json.dumps(owner))
            payload=dict(schema='wksim.private-tracefs.capture-bootstrap-active.v1',
                         state='bootstrap_active',phase='bootstrap_sched_switch',collector_pid=456,
                         collector_start_ticks=457,supervisor_pid=os.getpid(),supervisor_start_ticks=789,
                         instance=owner['instance'],instance_inode=[1,2],run_id='run',epoch=epoch,
                         started_monotonic_ns=100,published_monotonic_ns=200,
                         instance_owner_sha256=hashlib.sha256(owner_path.read_bytes()).hexdigest())
            token.write_text(json.dumps(payload,sort_keys=True)+'\n')
            hook.run_id,hook.epoch='run',epoch
            previous=os.environ.copy()
            try:
                os.environ.update(WKSIM_TRACE_GATE_READY=str(ready),WKSIM_TRACE_GATE_RELEASE=str(release),
                                  WKSIM_TRACE_CAPTURE_BOOTSTRAP_TOKEN=str(token),
                                  WKSIM_TRACE_CAPTURE_ACTIVE_TOKEN=str(capture/'capture-active.json'))
                frame=SimpleNamespace(f_locals={'self':SimpleNamespace(clock=SimpleNamespace(tick=0))})
                with patch.object(hook,'_self_start_ticks',return_value=789):hook._first_step_gate(frame)
            finally:
                os.environ.clear();os.environ.update(previous)
            value=json.loads(release.read_text())
            self.assertEqual(value['capture_token_schema'],payload['schema'])
            self.assertEqual(value['capture_token_sha256'],hashlib.sha256(token.read_bytes()).hexdigest())

    def test_hook_requires_bootstrap_token_for_tick_zero_release(self):
        hook = load_hook()
        with self.assertRaisesRegex(RuntimeError, 'requires a bootstrap capture token'):
            hook._first_step_gate(SimpleNamespace(
                f_locals={'self':SimpleNamespace(clock=SimpleNamespace(tick=0))}))

    def test_hook_rejects_active_state_and_publication_time_tamper(self):
        hook = load_hook()
        epoch = 'a'*32
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); capture = root/'capture'; capture.mkdir()
            token = capture/'capture-active.json'
            owner = dict(schema='wksim.private-tracefs.instance-owner.v1',
                         collector_pid=456, collector_start_ticks=457,
                         supervisor_pid=os.getpid(), supervisor_start_ticks=789,
                         instance='/sys/kernel/tracing/instances/wksim-rate-'+epoch,
                         instance_inode=[1, 2], run_id='run', epoch=epoch)
            owner_path = capture/'instance-owner.json'
            owner_path.write_text(json.dumps(owner, sort_keys=True)+'\n')
            ready = dict(schema='wksim.private-tracefs.capture-gate-ready.v1', state='ready',
                         run_id='run', epoch=epoch, pid=os.getpid(), start_ticks=789,
                         tick=0, published_monotonic_ns=100)
            def write_active(state='active', published=200):
                active = dict(schema='wksim.private-tracefs.capture-active.v1', state=state, phase='filtered',
                              collector_pid=456, collector_start_ticks=457,
                              supervisor_pid=os.getpid(), supervisor_start_ticks=789,
                              instance=owner['instance'], instance_inode=[1, 2],
                              run_id='run', epoch=epoch, started_monotonic_ns=150,
                              published_monotonic_ns=published,
                              instance_owner_sha256=hashlib.sha256(owner_path.read_bytes()).hexdigest())
                token.write_text(json.dumps(active, sort_keys=True)+'\n')
            for state, published in (('tampered', 200), ('active', 50)):
                write_active(state, published)
                with self.subTest(state=state, published=published), self.assertRaisesRegex(
                        RuntimeError, 'Capture-active token identity differs|publication precedes'):
                    hook._capture_active(token, ready)


if __name__ == '__main__':
    unittest.main()
