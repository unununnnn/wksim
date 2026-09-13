"""Bounded offline evidence reads for Simulator/wksim_runtime/replay.py.

Reproduces the load_evidence race: stat() sees a small record, then the read
consumes a file that grew or was replaced, so the byte limit must be enforced on
the bytes actually read rather than on a stale stat value. Reader doubles and a
tiny MAX_BYTES keep the race controllable without allocating oversized files.

Pure Python, offline: no runtime, native, SITL, model, ROS or network resource.
"""
import hashlib
import inspect
import os
from pathlib import Path
import stat as stat_module
import tempfile
import tracemalloc
import unittest
from unittest.mock import patch

from Simulator.wksim_runtime import replay
from Simulator.wksim_runtime.replay import load_evidence


LIMIT = 32
GUARDS = (
    patch('socket.socket', side_effect=AssertionError('offline reader opened network')),
    patch('subprocess.Popen', side_effect=AssertionError('offline reader created a process')),
    patch('os.system', side_effect=AssertionError('offline reader ran a shell')),
)


def stale_file_stat(size):
    """A stat result reporting `size` bytes that still looks like a regular file."""
    return os.stat_result((stat_module.S_IFREG | 0o644, 0, 0, 1, 0, 0, size, 0, 0, 0))


class Reader:
    """File-object double recording every requested size and byte actually served."""

    def __init__(self, chunks, honor_request=True):
        self.chunks = list(chunks)
        self.honor_request = honor_request
        self.requests = []
        self.served = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size=-1):
        self.requests.append(size)
        if not self.chunks:
            return b''
        chunk = self.chunks.pop(0)
        if self.honor_request and size >= 0:
            chunk = chunk[:size]
        self.served += len(chunk)
        return chunk


class DripReader:
    """Reader double returning one freshly allocated byte per read.

    Request recording is optional because the recording list itself allocates,
    which would dominate the peak-allocation probe below.
    """

    def __init__(self, payload, record_requests=True):
        self.payload = payload
        self.served = 0
        self.requests = [] if record_requests else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size=-1):
        if self.requests is not None:
            self.requests.append(size)
        if self.served >= len(self.payload):
            return b''
        chunk = self.payload[self.served:self.served + 1]
        self.served += 1
        return chunk


class OpenerSequence:
    """Stand-in for replay._open_record_file returning a different reader per call."""

    def __init__(self, readers):
        self.readers = list(readers)
        self.used = []

    def __call__(self, path):
        reader = self.readers.pop(0)
        self.used.append(reader)
        return reader


class BoundedReadTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, name, raw):
        path = self.root / name
        path.write_bytes(raw)
        return path

    def stale_size_for(self, name, size):
        """Report a stale, small st_size for one record inside the run."""
        real_stat = Path.stat

        def fake_stat(self_path, *args, **kwargs):
            if self_path.parent == self.root and self_path.name == name:
                return stale_file_stat(size)
            return real_stat(self_path, *args, **kwargs)

        return patch.object(Path, 'stat', fake_stat)

    def opener(self, reader):
        return patch.object(replay, '_open_record_file', lambda path: reader, create=True)

    def snapshot(self):
        return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir()}

    def test_default_limit_is_the_documented_64_mib_promise(self):
        self.assertEqual(replay.MAX_BYTES, 64 * 1024 * 1024)

    def test_record_exactly_at_limit_is_accepted_complete_and_hashed(self):
        prefix, suffix = b'{"run_id":"r","p":"', b'"}'
        raw = prefix + b'x' * (LIMIT - len(prefix) - len(suffix)) + suffix
        self.assertEqual(len(raw), LIMIT)
        self.write('result.json', raw)
        with patch.object(replay, 'MAX_BYTES', LIMIT):
            evidence = load_evidence(self.root)
        self.assertEqual(evidence['run_id'], 'r')
        self.assertEqual(evidence['files']['result.json'],
                         {'bytes': LIMIT, 'sha256': hashlib.sha256(raw).hexdigest()})

    def test_empty_record_at_zero_limit_is_accepted(self):
        self.write('truth.jsonl', b'')
        with patch.object(replay, 'MAX_BYTES', 0):
            evidence = load_evidence(self.root)
        self.assertEqual(evidence['files']['truth.jsonl'],
                         {'bytes': 0, 'sha256': hashlib.sha256(b'').hexdigest()})
        self.assertEqual(evidence['counts']['truth'], 0)

    def test_one_byte_over_limit_is_rejected_even_when_stat_agrees(self):
        self.write('result.json', b'x' * (LIMIT + 1))
        with patch.object(replay, 'MAX_BYTES', LIMIT):
            with self.assertRaisesRegex(ValueError, 'reader limit'):
                load_evidence(self.root)

    def test_real_file_read_is_capped_without_a_reader_double(self):
        raw = b'{"run_id":"r"}' + b' ' * (LIMIT * 6)
        self.assertGreater(len(raw), LIMIT)
        self.write('result.json', raw)
        with patch.object(replay, 'MAX_BYTES', LIMIT), self.stale_size_for('result.json', 4):
            with self.assertRaisesRegex(ValueError, 'grew or was replaced'):
                load_evidence(self.root)

    def test_stale_stat_cannot_bypass_the_read_cap(self):
        raw = b'{"run_id":"r","epoch":1}' + b' ' * LIMIT
        self.assertGreater(len(raw), LIMIT)
        self.write('result.json', raw)
        reader = Reader([raw])
        with patch.object(replay, 'MAX_BYTES', LIMIT), self.stale_size_for('result.json', 4), \
                self.opener(reader):
            with self.assertRaisesRegex(ValueError, 'reader limit'):
                load_evidence(self.root)
        self.assertTrue(reader.requests, 'bounded reader was never used')
        self.assertLessEqual(max(reader.requests), LIMIT + 1)
        self.assertLessEqual(reader.served, LIMIT + 1)

    def test_file_replaced_between_stat_and_read_is_rejected(self):
        original = b'{"run_id":"old","epoch":1}'
        self.write('result.json', original)
        replaced = b'{"run_id":"new","epoch":1,"pad":"' + b'y' * (LIMIT * 2) + b'"}'
        reader = Reader([replaced])
        with patch.object(replay, 'MAX_BYTES', LIMIT), self.opener(reader):
            with self.assertRaisesRegex(ValueError, 'reader limit'):
                load_evidence(self.root)
        self.assertLessEqual(max(reader.requests), LIMIT + 1)

    def test_growing_reader_is_rejected_without_silent_truncation(self):
        self.write('result.json', b'{"run_id":"r","epoch":1}')
        reader = Reader([b'{"run_id":"r","epoch":1}', b' ' * LIMIT, b'trailing growth'])
        with patch.object(replay, 'MAX_BYTES', LIMIT), self.stale_size_for('result.json', 4), \
                self.opener(reader):
            with self.assertRaisesRegex(ValueError, 'reader limit'):
                load_evidence(self.root)
        self.assertLessEqual(reader.served, LIMIT + 1)

    def test_reader_ignoring_the_request_size_is_still_capped(self):
        self.write('result.json', b'{"run_id":"r","epoch":1}')
        reader = Reader([b'x' * (LIMIT * 4)], honor_request=False)
        with patch.object(replay, 'MAX_BYTES', LIMIT), self.stale_size_for('result.json', 4), \
                self.opener(reader):
            with self.assertRaisesRegex(ValueError, 'reader limit'):
                load_evidence(self.root)
        self.assertEqual(reader.requests, [LIMIT + 1])
        self.assertGreater(reader.served, LIMIT)

    def test_byte_by_byte_short_reads_are_accepted_at_a_small_limit(self):
        limit = 8
        payload = b'{"a":1}'
        self.assertLessEqual(len(payload), limit)
        self.write('result.json', payload)
        reader = DripReader(payload)
        opener = OpenerSequence([reader, DripReader(payload)])
        with patch.object(replay, 'MAX_BYTES', limit), \
                patch.object(replay, '_open_record_file', opener, create=True):
            evidence = load_evidence(self.root)
        self.assertEqual(evidence['files']['result.json'],
                         {'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()})
        self.assertEqual(reader.served, len(payload))
        self.assertEqual(reader.requests, [limit + 1 - i for i in range(len(payload) + 1)])
        self.assertLessEqual(max(reader.requests), limit + 1)

    def test_oversized_chunk_mid_stream_is_rejected_without_further_reads(self):
        limit = 8
        self.write('result.json', b'{"a":1}')
        reader = Reader([b'ab', b'x' * 9], honor_request=False)
        with patch.object(replay, 'MAX_BYTES', limit), \
                patch.object(replay, '_open_record_file', lambda path: reader, create=True):
            with self.assertRaisesRegex(ValueError, 'reader limit'):
                load_evidence(self.root)
        self.assertEqual(reader.requests, [limit + 1, limit + 1 - 2])
        self.assertGreater(reader.served, limit)

    def test_bounded_reader_accumulates_in_one_buffer(self):
        source = inspect.getsource(replay._read_bounded)
        self.assertIn('bytearray()', source)
        self.assertNotIn('chunks.append', source)
        self.assertNotIn('.join(', source)

    def test_drip_reader_peak_allocation_stays_near_the_limit(self):
        limit = 64 * 1024
        payload = b'{"p":"' + b'x' * (limit - 8) + b'"}'
        self.assertEqual(len(payload), limit)
        self.write('result.json', payload)
        reader = DripReader(payload, record_requests=False)
        with patch.object(replay, '_open_record_file', lambda path: reader):
            tracemalloc.start()
            try:
                data = replay._read_bounded(self.root / 'result.json', limit)
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
        self.assertEqual(len(data), limit)
        self.assertEqual(hashlib.sha256(data).hexdigest(), hashlib.sha256(payload).hexdigest())
        self.assertEqual(reader.served, limit)
        self.assertLess(peak, 4 * limit)

    def test_short_reads_are_joined_and_hash_binds_consumed_bytes(self):
        raw = b'{"run_id":"r","epoch":1}'
        self.assertLessEqual(len(raw), LIMIT)
        self.write('result.json', raw)
        reader = Reader([raw[:5], raw[5:11], raw[11:]])
        opener = OpenerSequence([reader, Reader([raw])])
        with patch.object(replay, 'MAX_BYTES', LIMIT), \
                patch.object(replay, '_open_record_file', opener, create=True):
            evidence = load_evidence(self.root)
        self.assertEqual(evidence['files']['result.json'],
                         {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
        self.assertEqual(reader.requests,
                         [LIMIT + 1, LIMIT + 1 - 5, LIMIT + 1 - 11, LIMIT + 1 - len(raw)])
        self.assertEqual(reader.served, len(raw))

    def test_change_during_verification_reread_is_rejected_and_bounded(self):
        self.write('result.json', b'{"run_id":"r","epoch":1}')
        opener = OpenerSequence([Reader([b'{"run_id":"r","epoch":1}']),
                                 Reader([b'{"run_id":"r","epoch":2}'])])
        with patch.object(replay, 'MAX_BYTES', LIMIT), \
                patch.object(replay, '_open_record_file', opener, create=True):
            with self.assertRaisesRegex(ValueError, 'Evidence changed while reading'):
                load_evidence(self.root)
        self.assertEqual(len(opener.used), 2)
        for reader in opener.used:
            self.assertLessEqual(max(reader.requests), LIMIT + 1)

    def test_verification_reread_grown_past_limit_is_a_change_not_evidence(self):
        self.write('result.json', b'{"run_id":"r","epoch":1}')
        opener = OpenerSequence([Reader([b'{"run_id":"r","epoch":1}']),
                                 Reader([b'z' * (LIMIT + 1)])])
        with patch.object(replay, 'MAX_BYTES', LIMIT), \
                patch.object(replay, '_open_record_file', opener, create=True):
            with self.assertRaisesRegex(ValueError, 'Evidence changed while reading'):
                load_evidence(self.root)
        self.assertLessEqual(max(opener.used[1].requests), LIMIT + 1)

    def test_records_are_never_read_with_unbounded_read_bytes(self):
        self.write('result.json', b'{"run_id":"r","epoch":1}')
        self.write('truth.jsonl', b'{"time":1.0}\n')
        with patch.object(replay, 'MAX_BYTES', 4096), \
                patch.object(Path, 'read_bytes', side_effect=AssertionError('unbounded read_bytes used')):
            evidence = load_evidence(self.root)
        self.assertEqual(evidence['run_id'], 'r')
        self.assertEqual(evidence['counts']['truth'], 1)

    def test_rejected_load_performs_no_network_process_or_write(self):
        self.write('result.json', b'x' * (LIMIT + 1))
        before = self.snapshot()
        with patch.object(replay, 'MAX_BYTES', LIMIT), GUARDS[0], GUARDS[1], GUARDS[2]:
            with self.assertRaisesRegex(ValueError, 'reader limit'):
                load_evidence(self.root)
        self.assertEqual(before, self.snapshot())
        source = Path(replay.__file__).read_text(encoding='utf-8')
        for banned in ('import socket', 'import subprocess', 'import rospy', 'import rclpy', 'os.system'):
            self.assertNotIn(banned, source)
        self.write('result.json', b'{"run_id":"ok","epoch":1}')
        with patch.object(replay, 'MAX_BYTES', LIMIT):
            self.assertEqual(load_evidence(self.root)['run_id'], 'ok')

    def test_diagnostics_order_clocks_and_raw_text_survive_the_bounded_reader(self):
        self.write('result.json', b'{"stack":"px4"}')
        prometheus = (b'{"topic":"/uav1/prometheus/state","message":{"header":'
                      b'{"stamp":{"sec":10,"nanosec":250000000}}}}\n')
        truth = b'{"time":2.5,"sequence":1}\n{"time":3.5,"sequence":2}\n'
        self.write('prometheus.jsonl', prometheus)
        self.write('dds.jsonl', b'{"topic":\n')
        self.write('truth.jsonl', truth)
        self.write('telemetry.jsonl', b'{"mavpackettype":"HEARTBEAT"}\n')
        with patch.object(replay, 'MAX_BYTES', 4096), GUARDS[0], GUARDS[1]:
            evidence = load_evidence(self.root)
        self.assertEqual([r['stream'] for r in evidence['records']],
                         ['prometheus', 'truth', 'truth', 'telemetry'])
        self.assertEqual([r['line'] for r in evidence['records']], [1, 1, 2, 1])
        self.assertEqual([r['clock'] for r in evidence['records']],
                         ['fc_boot', 'physics', 'physics', 'unknown'])
        self.assertEqual([r['source_time_s'] for r in evidence['records']], [10.25, 2.5, 3.5, None])
        self.assertEqual([r['raw_json'] for r in evidence['records']],
                         [prometheus.decode(), truth.decode().splitlines(keepends=True)[0],
                          truth.decode().splitlines(keepends=True)[1], '{"mavpackettype":"HEARTBEAT"}\n'])
        self.assertEqual(evidence['files']['truth.jsonl'],
                         {'bytes': len(truth), 'sha256': hashlib.sha256(truth).hexdigest()})
        codes = {d['code'] for d in evidence['diagnostics']}
        self.assertTrue({'malformed_record', 'unknown_run_identity'} <= codes)
        self.assertEqual(evidence['reader_status'], 'partial')
        self.assertEqual(evidence['mode'], 'offline-records-not-resimulation')
        self.assertEqual(evidence['order'], 'stream then original line; no invented global event order')

    def test_symlink_outside_run_is_still_refused_via_path_double(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: outside.exists() and __import__('shutil').rmtree(outside, ignore_errors=True))
        self.write('result.json', b'{"run_id":"r","epoch":1}')
        real_resolve = Path.resolve

        def fake_resolve(self_path, *args, **kwargs):
            if self_path.parent == self.root and self_path.name == 'result.json':
                return outside / 'result.json'
            return real_resolve(self_path, *args, **kwargs)

        with patch.object(Path, 'resolve', fake_resolve):
            with self.assertRaisesRegex(ValueError, 'symlink outside run'):
                load_evidence(self.root)

    def test_symlink_outside_run_is_still_refused_for_a_real_link(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(outside, ignore_errors=True))
        (outside / 'result.json').write_bytes(b'{"run_id":"r","epoch":1}')
        try:
            os.symlink(outside / 'result.json', self.root / 'result.json')
        except (OSError, NotImplementedError) as error:
            self.skipTest(f'host cannot create symlinks: {error}')
        with self.assertRaisesRegex(ValueError, 'symlink outside run'):
            load_evidence(self.root)


if __name__ == '__main__':
    unittest.main()
