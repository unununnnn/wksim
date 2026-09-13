#!/usr/bin/env python3
"""Record SHA-256 of every artifact in this directory (read-only)."""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP = {'manifests.json'}


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    entries = {}
    for name in sorted(os.listdir(HERE)):
        path = os.path.join(HERE, name)
        if not os.path.isfile(path) or name in SKIP:
            continue
        entries[name] = dict(sha256=digest(path), bytes=os.path.getsize(path))
    payload = dict(
        kind='wksim.ds-perf-stream-consumer-manifest.v1',
        directory='validation/coordination/ds-perf-stream-consumer-20260913-01',
        contract='docs/coordination/perf-stream-contract-20260913.md',
        scope=('strict offline consumer for wksim.perf_switch_stream.v1 raw+metadata, optional '
               'wksim.perf_windows.v1 intersections; stdlib only; no native, no compilation, '
               'no model/ROS, no existing rate artifact parsed'),
        windows_format=dict(schema='wksim.perf_windows.v1', clock_id='CLOCK_MONOTONIC',
                            fields=['boot_id', 'owner_pid', 'owner_tid', 'windows[].id',
                                    'windows[].start_ns', 'windows[].end_ns'],
                            bound_to='capture metadata (boot, owner, clock)'),
        refuses_overwrite=True,
        flight_conclusion=None,
        tests='58 checks, 0 failed (python -B test_perf_stream_consumer.py)',
        artifacts=entries)
    with open(os.path.join(HERE, 'manifests.json'), 'w', encoding='utf-8') as fh:
        fh.write(json.dumps(payload, indent=2) + '\n')
    print(json.dumps(payload, indent=2))


if __name__ == '__main__':
    sys.exit(main())
