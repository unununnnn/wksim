"""Isolated release-wait comparison; Python re-entry time is the primary metric."""
from pathlib import Path
import ctypes
import gc
import hashlib
import json
import os
import platform
import statistics
import sys
import time

affinity_before = sorted(os.sched_getaffinity(0))
selected_cpu = affinity_before[0]
os.sched_setaffinity(0, {selected_cpu})  # this benchmark thread only
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import native_release_wait as waiter
import native_release_wait_extension as extension

library = HERE / 'libwksim_release_wait.so'
digest = hashlib.sha256(library.read_bytes()).hexdigest()
waits = {
    'cdll': waiter.bind(library, digest, loader=ctypes.CDLL),
    'pydll': waiter.bind(library, digest, loader=ctypes.PyDLL),
}
extension_path = HERE / (extension.MODULE_NAME + extension.EXT_SUFFIX)
extension_digest = hashlib.sha256(extension_path.read_bytes()).hexdigest()
waits['direct'] = extension.load(extension_path, extension_digest)
clock = time.monotonic_ns
assert time.get_clock_info('monotonic').implementation == 'clock_gettime(CLOCK_MONOTONIC)'

class PythonClock:
    def __init__(self):
        self.now = time.monotonic_ns

python_clock = PythonClock()
names = ('python_poll', 'cdll', 'pydll', 'direct')
rows = []
started = clock()
for index in range(1030):
    # Rotate execution order; do not run all samples of one mode in a separate phase.
    for mode in names[index % len(names):] + names[:index % len(names)]:
        deadline = clock() + 1_000_000
        if mode == 'python_poll':
            observed = python_clock.now()
            while observed < deadline:
                observed = python_clock.now()
        else:
            observed = waits[mode](deadline)
        resumed = clock()
        assert deadline <= observed <= resumed
        if index >= 30:
            rows.append(dict(mode=mode, index=index - 30, deadline_ns=deadline,
                observed_ns=observed, python_return_ns=resumed,
                observed_lateness_ns=observed - deadline,
                return_lateness_ns=resumed - deadline,
                return_gap_ns=resumed - observed))

def distribution(values):
    ordered = sorted(values)
    return dict(count=len(values), median_ns=statistics.median(ordered),
        p95_ns=ordered[(len(ordered) * 95 // 100) - 1],
        p99_ns=ordered[(len(ordered) * 99 // 100) - 1], maximum_ns=max(ordered),
        total_ns=sum(ordered), over_10us=sum(value > 10_000 for value in ordered))

summary = dict(scope='Single-process microbenchmark of final wait only; not a flight or production rate proof',
    primary_metric='Python re-entry time minus deadline; C crossing time alone excludes adapter/GIL return costs',
    host=dict(python=platform.python_version(), kernel=platform.release(),
              affinity=sorted(os.sched_getaffinity(0)), gc_enabled=gc.isenabled()),
    runtime_ns=clock() - started, library_sha256=digest, extension_sha256=extension_digest,
    adapter_sha256=hashlib.sha256((HERE / 'native_release_wait.py').read_bytes()).hexdigest(),
    benchmark_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    production_pacer_changed=False, resource_profile=dict(name='own-thread-first-allowed-vcpu', before=affinity_before, selected_cpu=selected_cpu), modes={})
for mode in names:
    selected = [row for row in rows if row['mode'] == mode]
    summary['modes'][mode] = {field: distribution([row[field] for row in selected])
        for field in ('observed_lateness_ns', 'return_lateness_ns', 'return_gap_ns')}
with (HERE / 'benchmark-rows.jsonl').open('x', encoding='utf-8') as stream:
    for row in rows:
        stream.write(json.dumps(row) + '\n')
summary['rows_sha256'] = hashlib.sha256((HERE / 'benchmark-rows.jsonl').read_bytes()).hexdigest()
with (HERE / 'benchmark-summary.json').open('x', encoding='utf-8') as stream:
    json.dump(summary, stream, indent=2)
    stream.write('\n')
print(json.dumps(summary))
