"""Stdlib protocol checks, then opt-in real isolated model checks.

WK_MODEL_LIBRARY=/tmp/.../libwksim_model.so python3 -B -m unittest
validation.test_joint_model_worker -v
Evidence is retained in a printed temporary root, including every owned PID.
Transport-only Python children below are not model or trajectory evidence.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from Simulator.wksim_core.worker import (
    REQUEST_LIMIT, RESPONSE_LIMIT, encoded, parse_frame, receive_worker,
    step_request, validate_response,
)

EPOCH = 'a' * 32
OTHER = 'b' * 32
REPO = Path(__file__).resolve().parents[1]


def snapshot(epoch=EPOCH):
    return dict(version=1, epoch=epoch, snapshot=True)


def step(tick=1, epoch=EPOCH):
    return dict(version=1, epoch=epoch, tick=tick, commands=[0.0] * 16)


class ProtocolTests(unittest.TestCase):
    def test_requests_and_boundaries(self):
        self.assertIsNone(step_request(snapshot(), 0, EPOCH))
        self.assertEqual(step_request(step(), 0, EPOCH), [0.0] * 16)
        valid = step()
        valid['commands'] = [0, 1] * 8
        step_request(valid, 0, EPOCH)
        invalid = [dict(step(), extra=1), step(0), step(2), step(True), step(1, OTHER),
                   dict(step(), version=True), dict(snapshot(), snapshot=1),
                   dict(snapshot(), tick=0), dict(step(), epoch='A' * 32)]
        for value in (True, None, '0', -0.01, 1.01, float('nan'), float('inf'), 10**400):
            invalid.append(dict(step(), commands=[value] * 16))
        invalid += [dict(step(), commands=[0] * 15), dict(step(), commands=[0] * 17)]
        for request in invalid:
            with self.subTest(request=request), self.assertRaises(ValueError):
                step_request(request, 0, EPOCH)
        base = encoded(step())
        line = base + ' ' * (REQUEST_LIMIT - len(base) - 1) + '\n'
        self.assertEqual(parse_frame(line, REQUEST_LIMIT), step())
        for line in (line + '\n', base, '{"tick":1,"tick":1}\n',
                     '{"x":NaN}\n', '{"x":Infinity}\n', '[]\n' + ' ' * REQUEST_LIMIT):
            with self.subTest(line=line[:40]), self.assertRaises(ValueError):
                parse_frame(line, REQUEST_LIMIT)

    def test_response_validation(self):
        initial = dict(version=1, epoch=EPOCH, tick=0, state=None)
        validate_response(initial, EPOCH, 0)
        response = dict(initial, tick=1, state=[0.0] * 120)
        validate_response(response, EPOCH, 1)
        for value in (dict(response, tick=True), dict(response, tick=2),
                      dict(response, version=True), dict(response, epoch=OTHER),
                      dict(response, extra=1), dict(response, state=None),
                      dict(response, state=[0.0] * 119),
                      dict(response, state=[True] * 120),
                      dict(response, state=[float('inf')] * 120)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_response(value, EPOCH, 1)


class OwnedChildren(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='wksim-worker-test-'))
        self.children = []
        print('Evidence root: ' + str(self.root), flush=True)

    def launch(self, argv, kind):
        directory = self.root / str(len(self.children))
        directory.mkdir()
        stderr = (directory / 'stderr.log').open('w')
        env = dict(os.environ, PYTHONPATH=str(REPO), PYTHONDONTWRITEBYTECODE='1')
        child = subprocess.Popen(argv, cwd=directory, env=env, text=True,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=stderr, start_new_session=True)
        record = dict(pid=child.pid, parent_pid=os.getpid(), argv=argv,
                      cwd=str(directory), kind=kind)
        if sys.platform == 'linux':
            record['proc_stat'] = Path(f'/proc/{child.pid}/stat').read_text()
            record['pgid'] = os.getpgid(child.pid)
            self.assertEqual(record['pgid'], child.pid)
        self.children.append((child, stderr, record))
        self.save()
        return child, directory

    def save(self):
        (self.root / 'children.json').write_text(
            json.dumps([record for _, _, record in self.children], indent=2) + '\n')

    def tearDown(self):
        for child, stderr, record in self.children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)
            record['returncode'] = child.wait(timeout=3)
            record['reaped'] = True
            if sys.platform == 'linux':
                record['proc_absent'] = not Path(f'/proc/{child.pid}').exists()
                self.assertTrue(record['proc_absent'])
            for stream in (child.stdin, child.stdout, stderr):
                stream.close()
        self.save()


@unittest.skipUnless(sys.platform == 'linux', 'WSL/Linux model pipe transport')
class TransportTests(OwnedChildren):
    def test_single_outstanding_rpc(self):
        marker = self.root / 'received'
        child, _ = self.launch([sys.executable, '-c',
            'import sys,time,pathlib; sys.stdin.readline(); pathlib.Path(' + repr(str(marker)) +
            ').touch(); time.sleep(10)'], 'transport-only outstanding request')
        errors = []

        def call():
            try:
                receive_worker(child, snapshot(), EPOCH, timeout=1)
            except Exception as error:
                errors.append(error)

        caller = threading.Thread(target=call)
        caller.start()
        try:
            deadline = time.monotonic() + 0.8
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertTrue(marker.exists())
            with self.assertRaisesRegex(RuntimeError, 'one outstanding'):
                receive_worker(child, snapshot(), EPOCH)
        finally:
            caller.join(timeout=2)
        self.assertFalse(caller.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], TimeoutError)

    def test_partial_line_deadline_and_poison(self):
        child, _ = self.launch([sys.executable, '-c',
            "import sys,time; sys.stdin.readline(); sys.stdout.write('{'); "
            "sys.stdout.flush(); time.sleep(10)"], 'transport-only partial frame')
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            receive_worker(child, snapshot(), EPOCH, timeout=0.2)
        self.assertLess(time.monotonic() - started, 1.5)
        with self.assertRaises(RuntimeError):
            receive_worker(child, snapshot(), EPOCH)

    def test_bad_response_frames(self):
        initial = dict(version=1, epoch=EPOCH, tick=0, state=None)
        for line in ('', '{"version":1,"version":1}\n',
                     encoded(dict(initial, epoch=OTHER)) + '\n',
                     encoded(dict(initial, tick=True)) + '\n',
                     ' ' * (RESPONSE_LIMIT + 1) + '\n'):
            child, _ = self.launch([sys.executable, '-c',
                'import sys; sys.stdin.readline(); sys.stdout.write(' + repr(line) +
                '); sys.stdout.flush()'], 'transport-only invalid frame')
            with self.assertRaises((ValueError, RuntimeError)):
                receive_worker(child, snapshot(), EPOCH)


@unittest.skipUnless(os.environ.get('WK_MODEL_LIBRARY'), 'real library not supplied')
class RealModelTests(OwnedChildren):
    def model(self, epoch=EPOCH):
        trace = self.root / f'trace-{len(self.children)}.jsonl'
        child, _ = self.launch([sys.executable, '-B', '-m', 'Simulator.wksim_core.worker',
            '--library', os.environ['WK_MODEL_LIBRARY'], '--trace', str(trace),
            '--epoch', epoch], 'real generated Model')
        return child, trace

    def test_two_processes_snapshot_and_eof(self):
        first, trace1 = self.model()
        second, trace2 = self.model(OTHER)
        self.assertNotEqual(first.pid, second.pid)
        self.assertIsNone(receive_worker(first, snapshot(), EPOCH)['state'])
        self.assertIsNone(receive_worker(second, snapshot(OTHER), OTHER)['state'])
        last = None
        for tick in range(1, 4):
            last = receive_worker(first, step(tick), EPOCH)
            self.assertAlmostEqual(last['state'][2], tick * 0.001)
        self.assertEqual(receive_worker(second, snapshot(OTHER), OTHER)['tick'], 0)
        one = receive_worker(second, step(1, OTHER), OTHER)
        self.assertAlmostEqual(one['state'][2], 0.001)
        for _ in range(2):
            self.assertEqual(receive_worker(first, snapshot(), EPOCH), last)
            self.assertEqual(receive_worker(second, snapshot(OTHER), OTHER), one)
        for child in (first, second):
            child.stdin.close()
            self.assertEqual(child.wait(timeout=3), 0)
        for trace, count, epoch in ((trace1, 3, EPOCH), (trace2, 1, OTHER)):
            rows = [json.loads(line) for line in trace.read_text().splitlines()]
            self.assertEqual(len(rows), count)
            for tick, row in enumerate(rows, 1):
                self.assertEqual(row['tick'], tick)
                self.assertEqual(row['version'], 1)
                self.assertEqual(row['epoch'], epoch)
                self.assertEqual(row['request'], step(tick, epoch))
                self.assertEqual(json.loads(row['input']), row['request'])
                self.assertEqual(row['commands'], [0.0] * 16)
                self.assertEqual(len(row['state']), 120)

    def test_rejections_do_not_step(self):
        bad = [encoded(dict(step(2), extra=1)), encoded(step(2, OTHER)),
               encoded(step(1)), encoded(step(3)), encoded(step(True)),
               encoded(dict(step(2), commands=[True] * 16)),
               encoded(step(2)).replace('"tick":2', '"tick":2,"tick":2'),
               encoded(step(2)).replace('0.0', 'NaN', 1),
               encoded(step(2)).replace('0.0', '1e999', 1),
               ' ' * REQUEST_LIMIT, encoded(dict(snapshot(), snapshot=1))]
        for frame in bad:
            with self.subTest(frame=frame[:90]):
                child, trace = self.model()
                receive_worker(child, step(), EPOCH)
                child.stdin.write(frame + '\n')
                child.stdin.flush()
                child.stdin.close()
                self.assertNotEqual(child.wait(timeout=3), 0)
                self.assertEqual(child.stdout.read(), '')
                rows = trace.read_text().splitlines()
                self.assertEqual(len(rows), 1)
                self.assertEqual(json.loads(rows[0])['tick'], 1)
        # Fresh epoch explicitly rejects a request from the prior run at tick 0.
        child, trace = self.model(OTHER)
        child.stdin.write(encoded(step()) + '\n')
        child.stdin.close()
        self.assertNotEqual(child.wait(timeout=3), 0)
        self.assertEqual(trace.read_text(), '')
        self.assertEqual(child.stdout.read(), '')


if __name__ == '__main__':
    unittest.main()
