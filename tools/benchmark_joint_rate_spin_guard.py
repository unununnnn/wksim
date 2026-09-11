"""Diagnostic-only host benchmark for fixed 8ms release spin guards.

No production scheduler, flight, SITL, UE, or MATLAB behavior is exercised.

Usage: python3 -B tools/benchmark_joint_rate_spin_guard.py --samples N --output PATH
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time

PERIOD_NS = 8_000_000
GUARD_CANDIDATES_NS = (1_000_000, 500_000, 200_000)


def _positive_int(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError('must be a positive integer')
    if value <= 0:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return value


def _guard_ns(value):
    if type(value) is not int or value <= 0:
        raise ValueError('guard_ns must be a positive integer')
    return value


def _samples(value):
    if type(value) is not int or value <= 0:
        raise ValueError('samples must be a positive integer')
    return value


def _percentile(ordered, fraction):
    return ordered[int(fraction * (len(ordered) - 1))]


def summarize(values):
    if not values:
        raise ValueError('cannot summarize empty measurements')
    ordered = sorted(values)
    return dict(
        count=len(ordered),
        total_ns=sum(ordered),
        mean_ns=sum(ordered) / len(ordered),
        median_ns=statistics.median(ordered),
        p95_ns=_percentile(ordered, .95),
        p99_ns=_percentile(ordered, .99),
        max_ns=ordered[-1],
        count_gt_10us=sum(value > 10_000 for value in ordered),
        count_gt_100us=sum(value > 100_000 for value in ordered),
        count_gt_500us=sum(value > 500_000 for value in ordered),
    )


def measure_guard(guard_ns, samples, now=time.monotonic_ns, sleep=time.sleep):
    guard_ns = _guard_ns(guard_ns)
    samples = _samples(samples)
    overshoot_ns = []
    spin_elapsed_ns = []
    for _ in range(samples):
        target = now() + PERIOD_NS
        before_sleep = now()
        sleep(max(0, target - before_sleep - guard_ns) / 1e9)
        spin_start = now()
        current = spin_start
        while current < target:
            current = now()
        overshoot_ns.append(current - target)
        spin_elapsed_ns.append(current - spin_start)
    return dict(
        guard_ns=guard_ns,
        overshoot_ns=overshoot_ns,
        spin_elapsed_ns=spin_elapsed_ns,
        summary=dict(overshoot_ns=summarize(overshoot_ns),
                     spin_elapsed_ns=summarize(spin_elapsed_ns)),
    )


def host_metadata():
    return dict(
        python=sys.version,
        platform=platform.platform(),
        wsl_distro_name=os.environ.get('WSL_DISTRO_NAME'),
    )


def scheduler_metadata():
    try:
        policy_value = os.sched_getscheduler(0)
        policy_names = {
            value: name for name, value in (
                (name, getattr(os, name))
                for name in ('SCHED_OTHER', 'SCHED_FIFO', 'SCHED_RR', 'SCHED_BATCH', 'SCHED_IDLE')
                if hasattr(os, name)
            )
        }
        policy = policy_names.get(policy_value, str(policy_value))
    except (AttributeError, OSError):
        policy_value = None
        policy = None
    try:
        priority = os.sched_getparam(0).sched_priority
    except (AttributeError, OSError):
        priority = None
    try:
        nice = os.getpriority(os.PRIO_PROCESS, 0)
    except (AttributeError, OSError):
        nice = None
    return dict(policy=policy, policy_value=policy_value, priority=priority, nice=nice)


def benchmark_source_sha256():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def run_benchmark(samples, *, now=time.monotonic_ns, sleep=time.sleep,
                  utc_now=lambda: datetime.now(timezone.utc).isoformat(),
                  environment=None, scheduler=None):
    samples = _samples(samples)
    started_utc = utc_now()
    candidates = [measure_guard(guard_ns, samples, now, sleep)
                  for guard_ns in GUARD_CANDIDATES_NS]
    finished_utc = utc_now()
    return dict(
        schema='wksim.joint_rate_spin_guard.v1',
        scope='Diagnostic-only host timing of exact 8ms group cadence; no production performance claim',
        diagnostic_only=True,
        production_performance=False,
        flight_claim=False,
        period_ns=PERIOD_NS,
        candidates_ns=list(GUARD_CANDIDATES_NS),
        sample_count=samples,
        started_utc=started_utc,
        finished_utc=finished_utc,
        environment=host_metadata() if environment is None else environment,
        scheduler=scheduler_metadata() if scheduler is None else scheduler,
        benchmark_source_sha256=benchmark_source_sha256(),
        candidates=candidates,
    )


def write_result(output, result):
    output = Path(output)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=1)
        stream.write('\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=_positive_int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError('output already exists: ' + str(args.output))
    result = run_benchmark(args.samples)
    write_result(args.output, result)
    print(json.dumps(dict(output=str(args.output), sample_count=args.samples)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
