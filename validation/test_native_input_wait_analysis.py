"""Offline checks for tools/analyze_native_input_waits.py; synthetic captures, not flight proof.

Exercises the per-stack AP/PX4 wait summarization and the reused report/trace
guards with in-memory records and a synthetic capture tree. No SITL/UE/ROS or a
real tracefs run is started.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.analyze_native_input_waits import analyze, check_record, summarize

EPOCH = 'e' * 32


def ap_seg(start, end, cpu, frame):
    return dict(stack='arducopter', wall_start_ns=start, wall_end_ns=end,
                wall_ns=end - start, thread_cpu_ns=cpu, ap_frame=frame)


def px4_seg(start, end, cpu, stamp):
    return dict(stack='px4', wall_start_ns=start, wall_end_ns=end,
                wall_ns=end - start, thread_cpu_ns=cpu, px4_time_us=stamp)


def record(tick, waits, epoch=EPOCH, total=None):
    return dict(kind='diagnostic_native_input_timing', epoch=epoch, tick=tick,
                native_wait_wall_ns=sum(w['wall_ns'] for w in waits) if total is None else total,
                waits=waits)


def switch_line(prev_pid, prev_state, next_pid, ns):
    sec, frac = divmod(ns, 10**9)
    return (f'c{prev_pid}-{prev_pid} [000] d..1 {sec}.{str(frac).zfill(9)}: sched_switch: '
            f'prev_comm=c{prev_pid} prev_pid={prev_pid} prev_prio=120 prev_state={prev_state} '
            f'==> next_comm=c{next_pid} next_pid={next_pid}')


def build_capture(tmp, rows, trace_lines, **meta_overrides):
    root = Path(tmp) / 'probe'
    epoch_dir = root / 'runs' / 'run-x' / 'epochs' / EPOCH
    epoch_dir.mkdir(parents=True)
    (root / 'capture').mkdir(parents=True)
    with (epoch_dir / 'wire.jsonl').open('w') as stream:
        for row in rows:
            stream.write(json.dumps(row) + '\n')
    trace = root / 'capture' / 'trace.txt'
    trace.write_text(''.join(line + '\n' for line in trace_lines))
    meta = dict(complete=True, loss_free=True, global_controls_unchanged=True, instance_removed=True,
                pid_mapping=dict(kernel_pids=dict(supervisor=100, ap_worker=200, px4_worker=300)),
                trace_bytes=trace.stat().st_size,
                trace_sha256=hashlib.sha256(trace.read_bytes()).hexdigest(),
                started_monotonic_ns=0, stopped_monotonic_ns=10**9)
    meta.update(meta_overrides)
    report = dict(run_id='scheduler-x', epoch=EPOCH, directory=str(root / 'runs' / 'run-x'), capture=meta)
    (root / 'report.json').write_text(json.dumps(report))
    return root


class CheckRecordTests(unittest.TestCase):
    def test_rejects_time_inconsistency(self):
        regressed = dict(stack='arducopter', wall_start_ns=5000, wall_end_ns=1000,
                         wall_ns=-4000, thread_cpu_ns=0, ap_frame=4)
        mismatched = dict(stack='arducopter', wall_start_ns=0, wall_end_ns=5000,
                          wall_ns=9999, thread_cpu_ns=10, ap_frame=4)
        negative_cpu = dict(stack='arducopter', wall_start_ns=0, wall_end_ns=1000,
                             wall_ns=1000, thread_cpu_ns=-1, ap_frame=4)
        for bad in (regressed, mismatched, negative_cpu):
            with self.assertRaises(ValueError):
                check_record(record(500, [bad]), EPOCH)

    def test_cpu_window_shift_preserves_observed_periodic_sample(self):
        # Real tick3750: wall409703ns, CPU410956ns. Endpoint reads are not simultaneous.
        check_record(record(3750,[ap_seg(0,409703,410956,3750)]),EPOCH)

    def test_no_records_or_only_outside_capture_is_not_zero_success(self):
        with self.assertRaisesRegex(ValueError,'No segmented'):
            summarize([],[],0,100,EPOCH)
        with self.assertRaisesRegex(ValueError,'inside capture'):
            summarize([record(500,[ap_seg(1000,2000,100,500)])],[],0,100,EPOCH)

    def test_rejects_duplicate_and_out_of_order_stack(self):
        duplicate = record(500, [ap_seg(0, 1000, 1, 500), ap_seg(2000, 3000, 1, 500)])
        reordered = record(500, [px4_seg(0, 1000, 1, 500000), ap_seg(2000, 3000, 1, 500)])
        for bad in (duplicate, reordered):
            with self.assertRaises(ValueError):
                check_record(bad, EPOCH)

    def test_rejects_empty_waits(self):
        with self.assertRaises(ValueError):
            check_record(record(500, []), EPOCH)

    def test_rejects_sum_mismatch(self):
        with self.assertRaises(ValueError):
            check_record(record(500, [ap_seg(0, 1000, 1, 500)], total=9999), EPOCH)

    def test_rejects_unknown_stack(self):
        bad = dict(stack='mavlink', wall_start_ns=0, wall_end_ns=1000, wall_ns=1000,
                   thread_cpu_ns=10, ap_frame=4)
        with self.assertRaises(ValueError):
            check_record(record(500, [bad]), EPOCH)

    def test_rejects_epoch_mismatch(self):
        with self.assertRaises(ValueError):
            check_record(record(500, [ap_seg(0, 1000, 1, 500)], epoch='f' * 32), EPOCH)

    def test_accepts_startup_px4_none_stamp(self):
        # A startup PX4 wait may complete before any actuator timestamp is bound.
        row = record(500, [ap_seg(0, 1000, 1, 500), px4_seg(2000, 3000, 1, None)])
        check_record(row, EPOCH)  # must not raise or fabricate a frame
        self.assertIsNone(row['waits'][1]['px4_time_us'])


class SummarizeTests(unittest.TestCase):
    def test_scheduler_blocked_and_runnable_attribution(self):
        intervals = [dict(start_ns=1000, end_ns=5000, state='S', wake_ns=3000)]
        rows = [record(500, [ap_seg(1000, 5000, 500, 500)])]
        result = summarize(rows, intervals, 0, 10**9, EPOCH)
        ap = result['by_stack'][0]
        self.assertEqual(ap['stack'], 'arducopter')
        self.assertEqual(ap['recorded_samples'], 1)
        self.assertEqual(ap['scheduler_totals'],
                         dict(off_cpu_ns=4000, runnable_ns=2000,
                              blocked_before_wake_ns=2000, unknown_off_cpu_ns=0))
        self.assertEqual(result['by_stack'][1]['recorded_samples'], 0)
        self.assertEqual((result['inside_capture'], result['excluded_capture_boundary']), (1, 0))

    def test_excludes_segments_crossing_capture_boundary(self):
        rows = [record(500, [ap_seg(1000, 5000, 500, 500), px4_seg(6000, 9000, 300, 500000)]),
                record(504, [ap_seg(3000, 4000, 100, 504)])]
        result = summarize(rows, [], 2000, 8000, EPOCH)
        self.assertEqual(result['total_segments'], 3)
        self.assertEqual(result['inside_capture'], 1)
        self.assertEqual(result['excluded_capture_boundary'], 2)
        self.assertEqual(result['by_stack'][0]['recorded_samples'], 1)
        self.assertEqual(result['by_stack'][1]['recorded_samples'], 0)

    def test_boundary_tick_separates_stacks_with_concrete_ticks(self):
        rows = [record(500, [ap_seg(1000, 3000, 200, 500), px4_seg(4000, 9000, 600, 500000)])]
        result = summarize(rows, [], 0, 10**9, EPOCH)
        ap, px4 = result['by_stack']
        self.assertEqual((ap['maximum_recorded_ns'], ap['recorded_wall_ns'], ap['recorded_thread_cpu_ns']),
                         (2000, 2000, 200))
        self.assertEqual((px4['maximum_recorded_ns'], px4['recorded_wall_ns'], px4['recorded_thread_cpu_ns']),
                         (5000, 5000, 600))
        self.assertEqual(ap['longest_recorded_waits'][0]['tick'], 500)
        self.assertEqual(px4['longest_recorded_waits'][0]['tick'], 500)
        self.assertEqual(px4['longest_recorded_waits'][0]['px4_time_us'], 500000)


class CaptureTests(unittest.TestCase):
    def trace(self):
        return [switch_line(100, 'S', 999, 1000), switch_line(999, 'S', 100, 4000)]

    def test_analyze_attributes_supervisor_off_cpu(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_capture(tmp, [record(500, [ap_seg(1000, 4000, 500, 500)])], self.trace())
            result = analyze(root)
            self.assertEqual(result['schema'], 'wksim.native-input-wait-analysis.v1')
            self.assertFalse(result['acceptance_eligible'])
            ap = result['by_stack'][0]
            self.assertEqual(ap['recorded_samples'], 1)
            self.assertEqual(ap['scheduler_totals']['unknown_off_cpu_ns'], 3000)
            self.assertEqual(ap['scheduler_totals']['off_cpu_ns'], 3000)
            self.assertEqual(result['trace_sha256'], hashlib.sha256(
                (root / 'capture' / 'trace.txt').read_bytes()).hexdigest())

    def test_incomplete_capture_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_capture(tmp, [record(500, [ap_seg(1000, 4000, 500, 500)])], self.trace(),
                                 complete=False)
            with self.assertRaises(ValueError):
                analyze(root)

    def test_trace_identity_change_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_capture(tmp, [record(500, [ap_seg(1000, 4000, 500, 500)])], self.trace())
            with (root / 'capture' / 'trace.txt').open('a') as stream:
                stream.write('# tampered\n')
            with self.assertRaises(ValueError):
                analyze(root)

    def test_cli_writes_output_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_capture(tmp, [record(500, [ap_seg(1000, 4000, 500, 500)])], self.trace())
            out = Path(tmp) / 'analysis.json'
            cmd = [sys.executable, '-B', str(ROOT / 'tools' / 'analyze_native_input_waits.py'),
                   str(root), '--output', str(out)]
            first = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            result = json.loads(out.read_text())
            self.assertEqual(result['records_seen'], 1)
            second = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn('FileExistsError', second.stderr)


if __name__ == '__main__':
    unittest.main()
