"""Read recorded SITL evidence offline; never import ROS or connect to a flight controller.

Records retain original JSON text and file/line order. Clock domains are not
merged: an old run has no recorded mapping from FC boot to physics time.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys


STREAMS = ('prometheus', 'dds', 'truth', 'telemetry')
MAX_BYTES = 64 * 1024 * 1024


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def source_time(stream, row):
    """Return a named recorded clock, never derive time from row number."""
    if stream == 'truth' and finite(row.get('time')):
        return 'physics', row['time']
    msg = row.get('message', row)
    if not isinstance(msg, dict):
        return 'unknown', None
    if finite(msg.get('time_boot_ms')):
        return 'fc_boot', msg['time_boot_ms'] / 1000
    if (stream == 'dds' or row.get('observation_only') is True) and finite(msg.get('timestamp')):
        return 'fc_boot', msg['timestamp'] / 1e6
    stamp = msg.get('header', {}).get('stamp') if isinstance(msg.get('header'), dict) else None
    if isinstance(stamp, dict) and finite(stamp.get('sec')) and finite(stamp.get('nanosec')):
        value = stamp['sec'] + stamp['nanosec'] / 1e9
        topic = str(row.get('topic', ''))
        # Public state uses FC boot; public commands/events use the ROS clock.
        clock = 'fc_boot' if stream == 'dds' or topic.endswith(('/state', '/control_state')) else 'ros'
        return clock, value
    return 'unknown', None


def event_kind(row):
    if 'published' in row:
        return 'command'
    if row.get('mavpackettype') == 'COMMAND_ACK' or 'command_ack' in str(row.get('topic', '')):
        return 'native_ack'
    msg = row.get('message')
    if str(row.get('topic', '')).endswith('/text_info') and isinstance(msg, dict):
        try:
            event = json.loads(msg.get('message', '{}'))
            if isinstance(event, dict):
                return str(event.get('event', 'text_info'))
        except (TypeError, ValueError):
            pass
        return 'text_info'
    return str(row.get('mavpackettype', 'state'))


def load_evidence(directory):
    root = Path(directory).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Evidence input must be a run directory')
    records, diagnostics, files = [], [], {}

    def read(name):
        path = root / name
        if not path.is_file():
            diagnostics.append({'code': 'missing_file', 'file': name})
            return None
        if path.resolve().parent != root:
            raise ValueError(f'Refusing evidence symlink outside run: {name}')
        # ponytail: bounded in-memory reader; add streaming indexing for larger runs.
        if path.stat().st_size > MAX_BYTES:
            raise ValueError(f'{name} exceeds offline reader limit {MAX_BYTES} bytes')
        data = path.read_bytes()
        if len(data) > MAX_BYTES:
            raise ValueError(f'{name} grew beyond the offline reader limit')
        files[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        return data

    result_bytes = read('result.json')
    result = {}
    if result_bytes is not None:
        try:
            result = json.loads(result_bytes)
            if not isinstance(result, dict):
                raise ValueError('result must be an object')
        except (ValueError, UnicodeError) as error:
            result = {}
            diagnostics.append({'code': 'invalid_result', 'detail': str(error)})
    run_id, epoch = result.get('run_id'), result.get('epoch')
    if run_id is None or epoch is None:
        diagnostics.append({'code': 'unknown_run_identity', 'detail': 'Missing run_id/epoch remain unknown; directory name is not a recorded epoch.'})

    for stream in STREAMS:
        name = stream + '.jsonl'
        data = read(name)
        if data is None:
            continue
        if data and not data.endswith(b'\n'):
            diagnostics.append({'code': 'unterminated_last_line', 'file': name})
        previous_time, previous_sequence = {}, {}
        for line_number, line in enumerate(data.splitlines(keepends=True), 1):
            where = {'stream': stream, 'line': line_number}
            try:
                raw = line.decode('utf-8')
                constants = []
                row = json.loads(raw, parse_constant=lambda token: constants.append(token) or {'nonfinite': token})
                if not isinstance(row, dict):
                    raise ValueError('record must be an object')
            except (ValueError, UnicodeError) as error:
                diagnostics.append(dict(where, code='malformed_record', detail=str(error), raw_sha256=hashlib.sha256(line).hexdigest()))
                continue
            if constants:
                diagnostics.append(dict(where, code='nonfinite_values', values=sorted(set(constants))))
            clock, stamp = source_time(stream, row)
            topic = str(row.get('topic', row.get('mavpackettype', stream)))
            key = (topic, clock)
            if stamp is not None:
                if key in previous_time and stamp < previous_time[key]:
                    diagnostics.append(dict(where, code='source_time_regression', clock=clock))
                previous_time[key] = stamp
            sequence = row.get('sequence')
            if isinstance(sequence, int) and not isinstance(sequence, bool):
                if topic in previous_sequence and sequence != previous_sequence[topic] + 1:
                    diagnostics.append(dict(where, code='sequence_discontinuity', previous=previous_sequence[topic], actual=sequence))
                previous_sequence[topic] = sequence
            msg = row.get('message', {})
            invalid = isinstance(msg, dict) and (msg.get('connected') is False or msg.get('odom_valid') is False)
            records.append(dict(where, clock=clock, source_time_s=stamp,
                                receive_wall_s=row.get('wall') if finite(row.get('wall')) else None,
                                receive_clock='wall_elapsed:' + stream, kind=event_kind(row),
                                recorded_invalid=invalid, run_id=run_id, epoch=epoch,
                                raw_sha256=hashlib.sha256(line).hexdigest(), raw_json=raw, payload=row))
    # Re-read hashes detects an active/growing run; never advertise a live snapshot as stable.
    for name, identity in files.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != identity['sha256']:
            raise ValueError(f'Evidence changed while reading: {name}; stop the run first')
    counts = {s: sum(r['stream'] == s for r in records) for s in STREAMS}
    return {'format_version': 1, 'mode': 'offline-records-not-resimulation',
            'reader_status': 'partial' if any(d['code'] in ('missing_file', 'invalid_result', 'malformed_record',
                                                          'unterminated_last_line', 'sequence_discontinuity')
                                            for d in diagnostics) else 'parsed',
            'run_id': run_id, 'epoch': epoch, 'stack': result.get('stack'),
            'recorded_run_status': result.get('status'), 'input_directory': str(root),
            'clock_mapping': 'unknown across physics, FC boot, ROS and per-stream elapsed clocks',
            'order': 'stream then original line; no invented global event order',
            'files': files, 'counts': counts, 'records': records, 'diagnostics': diagnostics}


def select_records(evidence, *, stream=None, clock=None, start=None, end=None, events_only=False):
    if (start is not None or end is not None) and clock is None:
        raise ValueError('Time filtering requires an explicit --clock; domains cannot be mixed')
    if start is not None and end is not None and start > end:
        raise ValueError('--from-time must not exceed --to-time')
    for row in evidence['records']:
        if stream is not None and row['stream'] != stream:
            continue
        if clock is not None and row['clock'] != clock:
            continue
        if start is not None and (row['source_time_s'] is None or row['source_time_s'] < start):
            continue
        if end is not None and (row['source_time_s'] is None or row['source_time_s'] > end):
            continue
        if events_only and row['kind'] in ('state', 'HEARTBEAT', 'LOCAL_POSITION_NED', 'ATTITUDE', 'GLOBAL_POSITION_INT'):
            continue
        yield row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--stream', choices=STREAMS)
    parser.add_argument('--clock', choices=('physics', 'fc_boot', 'ros', 'unknown'))
    parser.add_argument('--from-time', type=float)
    parser.add_argument('--to-time', type=float)
    parser.add_argument('--events-only', action='store_true')
    parser.add_argument('--record', help='Inspect one exact recorded sample, e.g. prometheus:100')
    parser.add_argument('--output', type=Path, help='New JSON replay file outside the input run; never overwritten')
    args = parser.parse_args(argv)
    try:
        if any(v is not None and not finite(v) for v in (args.from_time, args.to_time)):
            raise ValueError('Time filters must be finite')
        evidence = load_evidence(args.directory)
        if args.record:
            stream, line = args.record.split(':', 1)
            sample = next((r for r in evidence['records'] if r['stream'] == stream and r['line'] == int(line)), None)
            if sample is None:
                raise ValueError('No valid sample at that stream/line; inspect diagnostics for malformed records')
            print(json.dumps(sample, ensure_ascii=False, allow_nan=False, indent=2))
            return 0
        selected = list(select_records(evidence, stream=args.stream, clock=args.clock,
                                       start=args.from_time, end=args.to_time, events_only=args.events_only))
        summary = {k: v for k, v in evidence.items() if k not in ('records', 'diagnostics')}
        summary['selected_records'] = len(selected)
        summary['diagnostic_counts'] = {code: sum(d['code'] == code for d in evidence['diagnostics'])
                                        for code in sorted({d['code'] for d in evidence['diagnostics']})}
        if args.output:
            if args.output.resolve().is_relative_to(args.directory.resolve()):
                raise ValueError('Replay output must be outside the source evidence directory')
            with args.output.open('x', encoding='utf-8') as out:
                json.dump(dict(summary, records=selected, diagnostics=evidence['diagnostics']), out,
                          ensure_ascii=False, allow_nan=False)
                out.write('\n')
            summary['output'] = str(args.output.resolve())
        print(json.dumps(summary, ensure_ascii=False, allow_nan=False, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({'status': 'error', 'reason': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
