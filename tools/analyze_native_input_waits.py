"""Split retained AP/PX4 native-input wait segments by stack against one capture.

Reuses the proven trace parser, write/sched pairing, supervisor scheduler
attribution and report/trace identity guards from tools/analyze_joint_scheduler.py;
it never re-implements trace parsing. It summarizes only diagnostic_native_input_timing
segments lying fully inside the capture window and never overwrites evidence.
"""
import argparse
from bisect import bisect_right
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.analyze_joint_scheduler import parse, pair, explain, require

STACKS = ('arducopter', 'px4')
SCHEDULER_KEYS = ('off_cpu_ns', 'runnable_ns', 'blocked_before_wake_ns', 'unknown_off_cpu_ns')


def check_segment(segment):
    stack = segment.get('stack')
    require(stack in STACKS, 'Unknown or missing native wait stack')
    for key in ('wall_start_ns', 'wall_end_ns', 'wall_ns', 'thread_cpu_ns'):
        require(type(segment.get(key)) is int, 'Native wait segment missing integer ' + key)
    require(segment['wall_end_ns'] > segment['wall_start_ns'], 'Native wait wall time regressed')
    require(segment['wall_ns'] == segment['wall_end_ns'] - segment['wall_start_ns'],
            'Native wait wall_ns does not match its own bracket')
    # The producer reads wall then CPU at each endpoint. These are shifted
    # measurement windows, so short sampled waits can legitimately have CPU
    # slightly greater than wall; do not clip or reject that observation.
    require(0 <= segment['thread_cpu_ns'], 'Native wait thread CPU is negative')
    if stack == 'arducopter':
        require(type(segment.get('ap_frame')) is int, 'AP wait segment missing integer ap_frame')
    else:
        # Startup may complete a PX4 wait before any actuator timestamp is bound.
        require(segment.get('px4_time_us') is None or type(segment.get('px4_time_us')) is int,
                'PX4 wait segment has a non-integer px4_time_us')


def check_record(row, epoch):
    require(row.get('kind') == 'diagnostic_native_input_timing', 'Not a native input timing record')
    require(row.get('epoch') == epoch, 'Native input timing record epoch is not the bound epoch')
    require(type(row.get('tick')) is int, 'Native input timing record missing integer tick')
    require(type(row.get('native_wait_wall_ns')) is int, 'Record missing integer native_wait_wall_ns')
    waits = row.get('waits')
    require(isinstance(waits, list) and len(waits) > 0, 'Native input timing record has no wait segments')
    for segment in waits:
        check_segment(segment)
    require(sum(segment['wall_ns'] for segment in waits) == row['native_wait_wall_ns'],
            'Native wait segments do not sum to native_wait_wall_ns')
    require(all(a['wall_end_ns'] <= b['wall_start_ns'] for a, b in zip(waits, waits[1:])),
            'Overlapping native wait segments in one record')
    stacks = [segment['stack'] for segment in waits]
    require(len(set(stacks)) == len(stacks), 'Duplicate native wait stack in one record')
    require(stacks == sorted(stacks, key=STACKS.index), 'Out-of-order native wait stacks in one record')


def scheduler_numbers(span, intervals):
    found = explain(span, intervals)
    return {key: found[key] for key in SCHEDULER_KEYS}


def summarize(rows, intervals, capture_start, capture_end, epoch):
    require(capture_start < capture_end, 'Invalid capture window')
    require(rows, 'No segmented native input records')
    intervals = sorted(intervals, key=lambda value: value['start_ns'])
    ends = [value['end_ns'] for value in intervals]
    require(all(a['end_ns'] <= b['start_ns'] for a, b in zip(intervals, intervals[1:])),
            'Overlapping supervisor scheduler intervals')
    per_stack = {stack: [] for stack in STACKS}
    total = excluded = 0
    for row in rows:
        check_record(row, epoch)  # validate every record, even one partly outside the window
        for segment in row['waits']:
            total += 1
            if segment['wall_start_ns'] < capture_start or segment['wall_end_ns'] > capture_end:
                excluded += 1
                continue
            first = bisect_right(ends, segment['wall_start_ns'])
            selected = []
            for value in intervals[first:]:
                if value['start_ns'] >= segment['wall_end_ns']:
                    break
                selected.append(value)
            span = dict(ns=segment['wall_start_ns'], end_ns=segment['wall_end_ns'],
                        duration_ns=segment['wall_ns'])
            entry = dict(tick=row['tick'], wall_ns=segment['wall_ns'],
                         thread_cpu_ns=segment['thread_cpu_ns'], scheduler=scheduler_numbers(span, selected))
            if segment['stack'] == 'arducopter':
                entry['ap_frame'] = segment['ap_frame']
            else:
                entry['px4_time_us'] = segment.get('px4_time_us')  # may be None during startup
            per_stack[segment['stack']].append(entry)
    summaries = []
    require(total > excluded, 'No native input segments inside capture')
    for stack in STACKS:
        entries = per_stack[stack]
        durations = sorted(entry['wall_ns'] for entry in entries)
        summaries.append(dict(stack=stack, recorded_samples=len(entries),
            maximum_recorded_ns=max(durations) if durations else None,
            recorded_wall_ns=sum(durations),
            recorded_thread_cpu_ns=sum(entry['thread_cpu_ns'] for entry in entries),
            cpu_exceeds_wall_samples=sum(entry['thread_cpu_ns'] > entry['wall_ns'] for entry in entries),
            scheduler_totals={key: sum(entry['scheduler'][key] for entry in entries) for key in SCHEDULER_KEYS},
            longest_recorded_waits=sorted(entries, key=lambda entry: entry['wall_ns'], reverse=True)[:10]))
    return dict(records_seen=len(rows), total_segments=total, inside_capture=total - excluded,
                excluded_capture_boundary=excluded, by_stack=summaries)


def load_capture(root):
    report = json.loads((root / 'report.json').read_text())
    meta = report['capture']
    require(meta['complete'] and meta['loss_free'] and meta['global_controls_unchanged']
            and meta['instance_removed'], 'Incomplete or lossy capture')
    require(meta.get('pid_mapping') and meta.get('trace_bytes', 0) > 0,
            'Missing kernel mapping or empty capture')
    raw = root / 'capture/trace.txt'
    require(hashlib.sha256(raw.read_bytes()).hexdigest() == meta['trace_sha256'], 'Trace identity changed')
    pids = meta['pid_mapping']['kernel_pids']
    with raw.open() as stream:
        events = [parse(line) for line in stream if line.strip() and not line.startswith('#')]
    _writes, off, boundaries = pair(events, set(pids.values()))
    return report, meta, pids, off, boundaries


def analyze(root):
    report, meta, pids, off, boundaries = load_capture(root)
    epoch_dir = Path(report['directory']) / 'epochs' / report['epoch']
    with (epoch_dir / 'wire.jsonl').open() as stream:
        rows = [row for line in stream if (row := json.loads(line))['kind'] == 'diagnostic_native_input_timing']
    summary = summarize(rows, off[pids['supervisor']],
                        meta['started_monotonic_ns'], meta['stopped_monotonic_ns'], report['epoch'])
    return dict(schema='wksim.native-input-wait-analysis.v1', acceptance_eligible=False,
        run_id=report['run_id'],
        analyzer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        epoch=report['epoch'], pid_mapping=meta['pid_mapping'], trace_sha256=meta['trace_sha256'],
        capture_window_ns=dict(start_ns=meta['started_monotonic_ns'], end_ns=meta['stopped_monotonic_ns']),
        scheduler_boundary_counts=boundaries, **summary,
        limitation='Biased retained samples: the sum of native waits >2ms or a tick divisible by 250, '
            'never a full census. No population median or rate is claimed. Only segments fully inside the '
            'capture window are summarized; boundary-crossing segments are excluded, not interpolated. '
            'Supervisor off-CPU/runnable/blocked time during a wait includes I/O wait and descheduling and '
            'does not identify the native FC internal function, host or Windows cause. '
            'CPU and wall reads bracket slightly different windows; CPU is retained even when it exceeds wall. A PX4 wait with '
            'px4_time_us null completed during startup before any actuator timestamp was bound; a returned '
            'wait is not by itself proof a PX4 input arrived.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.root)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({row['stack']: dict(recorded_samples=row['recorded_samples'],
        maximum_recorded_ns=row['maximum_recorded_ns'],
        recorded_wall_ns=row['recorded_wall_ns'])
        for row in result['by_stack']}, indent=2))
