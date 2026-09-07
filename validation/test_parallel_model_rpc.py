"""Batch transport and real two-process numerical checks; not FC/G6 flight proof."""
import hashlib
import json
import os
import sys
import time
import unittest
from pathlib import Path

from Simulator.wksim_core.worker import receive_worker, receive_workers
from validation import test_joint_model_worker as worker_tests
from validation.test_joint_model_worker import OwnedChildren, EPOCH, snapshot, step


@unittest.skipUnless(sys.platform == 'linux', 'WSL/Linux pipes')
class BatchTransportTests(OwnedChildren):
    def test_partial_progress_still_services_operator_abort(self):
        peer, _ = self.launch([sys.executable, '-c',
            "import sys,time; sys.stdin.readline(); [(sys.stdout.write(' '),sys.stdout.flush(),time.sleep(.005)) for _ in range(2000)]"],
            'transport-only continuous partial response')
        begun=time.monotonic()
        def health():
            if time.monotonic()-begun>=.07:
                raise RuntimeError('explicit operator abort')
        with self.assertRaisesRegex(RuntimeError,'explicit operator abort'):
            receive_worker(peer,snapshot(),EPOCH,timeout=.3,health=health)
        self.assertTrue(peer._wksim_rpc['failed'])

    def test_keyboard_interruption_poisons_a_transmitting_channel(self):
        peer, _ = self.launch([sys.executable, '-c',
            "import sys,time; sys.stdin.readline(); time.sleep(10)"], 'transport-only interrupted wait')
        def interrupted():raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            receive_worker(peer,snapshot(),EPOCH,timeout=.3,health=interrupted)
        self.assertTrue(peer._wksim_rpc['failed'])

    def test_partial_failure_preserves_confirmation_and_poisons_every_member(self):
        good, _ = self.launch([sys.executable, '-c',
            "import sys,json,time; r=json.loads(sys.stdin.readline()); print(json.dumps(dict(version=1,epoch=r['epoch'],tick=1,state=[0.]*120)),flush=True); time.sleep(10)"], 'transport-only success')
        stalled, _ = self.launch([sys.executable, '-c',
            "import sys,time; sys.stdin.readline(); time.sleep(10)"], 'transport-only timeout')
        with self.assertRaises(TimeoutError):
            receive_workers(dict(good=(good, step()), stalled=(stalled, step())), EPOCH, timeout=.3)
        self.assertEqual(good._wksim_rpc['tick'], 1)
        self.assertEqual(stalled._wksim_rpc['tick'], 0)
        for child in (good, stalled):
            self.assertGreater(child._wksim_rpc['sent_bytes'], 0)
            self.assertTrue(child._wksim_rpc['failed'])
            with self.assertRaisesRegex(RuntimeError, 'retired'):
                receive_worker(child, snapshot(), EPOCH)

    def test_exit_and_stale_epoch_poison_batch(self):
        for code in ("import sys; sys.stdin.readline()",
                     "import sys,json; sys.stdin.readline(); print(json.dumps(dict(version=1,epoch='b'*32,tick=0,state=None)),flush=True)"):
            child, _ = self.launch([sys.executable, '-c', code], 'transport-only bad peer')
            peer, _ = self.launch([sys.executable, '-c',
                "import sys,time; sys.stdin.readline(); time.sleep(10)"], 'transport-only peer')
            with self.assertRaises((ValueError, RuntimeError)):
                receive_workers(dict(bad=(child, snapshot()), peer=(peer, snapshot())), EPOCH, timeout=.3)
            self.assertTrue(child._wksim_rpc['failed'])
            self.assertTrue(peer._wksim_rpc['failed'])


@unittest.skipUnless(os.environ.get('WK_MODEL_LIBRARY'), 'real library not supplied')
class BatchRealModelTests(OwnedChildren):
    model = worker_tests.RealModelTests.model

    def test_real_model_exit_and_stall_retire_both_channels(self):
        import signal
        for stopped in (False, True):
            good, _ = self.model()
            bad, _ = self.model()
            receive_workers(dict(good=(good, snapshot()), bad=(bad, snapshot())), EPOCH)
            if stopped:
                os.kill(bad.pid, signal.SIGSTOP)
            else:
                bad.terminate()
                bad.wait(timeout=3)
            try:
                with self.assertRaises((TimeoutError, RuntimeError, BrokenPipeError)):
                    receive_workers(dict(good=(good, step()), bad=(bad, step())), EPOCH, timeout=.2)
                for child in (good, bad):
                    self.assertTrue(child._wksim_rpc['failed'])
                    with self.assertRaisesRegex(RuntimeError, 'retired'):
                        receive_worker(child, snapshot(), EPOCH)
                if stopped:
                    self.assertEqual(good._wksim_rpc['tick'], 1)
                    self.assertEqual(bad._wksim_rpc['tick'], 0)
            finally:
                if stopped:
                    os.kill(bad.pid, signal.SIGCONT)

    def test_same_inputs_exact_states_and_throughput(self):
        library = Path(os.environ['WK_MODEL_LIBRARY'])
        self.assertEqual(hashlib.sha256(library.read_bytes()).hexdigest(),
                         'cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3')
        runs = {}
        for mode in ('sequential', 'batch'):
            pair = {name: self.model() for name in ('ap', 'px4')}
            children = {name: value[0] for name, value in pair.items()}
            initial = receive_workers({name: (child, snapshot()) for name, child in children.items()}, EPOCH)
            self.assertTrue(all(value['tick'] == 0 and value['state'] is None for value in initial.values()))
            states = []
            started = time.perf_counter()
            for tick in range(1, 1001):
                requests = {name: (child, dict(step(tick), commands=[.35 + (tick % 7)*.005 + index*.01]*16))
                            for index, (name, child) in enumerate(children.items())}
                if mode == 'batch':
                    response = receive_workers(requests, EPOCH)
                else:
                    response = {name: receive_worker(child, request, EPOCH) for name, (child, request) in requests.items()}
                states.append(response)
            elapsed = time.perf_counter() - started
            for child in children.values():
                child.stdin.close()
                self.assertEqual(child.wait(timeout=3), 0)
            traces = {name: [json.loads(line) for line in trace.read_text().splitlines()]
                      for name, (_, trace) in pair.items()}
            for name, rows in traces.items():
                self.assertEqual(len(rows), 1000)
                for tick, row in enumerate(rows, 1):
                    self.assertEqual(row['request'], json.loads(row['input']))
                    self.assertEqual(row['state'], states[tick-1][name]['state'])
                    self.assertEqual((row['epoch'], row['tick']), (EPOCH, tick))
            runs[mode] = dict(wall_seconds=elapsed, states=states, traces=traces)
        self.assertEqual(runs['sequential']['states'], runs['batch']['states'])
        self.assertEqual(runs['sequential']['traces'], runs['batch']['traces'])
        result = dict(not_flight_or_G6=True, ticks=1000, model_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),
                      **{mode: dict(wall_seconds=value['wall_seconds'], ticks_per_second=1000/value['wall_seconds']) for mode,value in runs.items()})
        (self.root/'comparison.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    unittest.main()
