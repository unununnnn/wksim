"""Host sleep-overshoot benchmark and deterministic JointRate release replay.

Two parts, both offline (no SITL/ROS):
1. time.sleep overshoot distribution for 0.2/0.5/1/2 ms, >=10000 samples each.
2. A labeled SIMULATION of the begin_group release loop (not production code):
   the current 1 ms guard versus a hypothetical 2 ms guard, replaying the
   recorded per-group work durations of a real run, with every measured sleep
   overshoot replayed in a deterministic interleaving. This model
   cannot prove production benefit; it only compares the two guards' creep
   under identical synthetic conditions.

Usage: python3 -B tools/benchmark_joint_rate_release.py --rate-jsonl <run rate.jsonl> --output <new.json>
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time

DURATIONS_MS = (0.2, 0.5, 1.0, 2.0)
SAMPLES = 10000
PERIOD_NS = 8_000_000


def measure_sleep():
    summary = {}
    samples = {}
    for ms in DURATIONS_MS:
        over = []
        target = ms / 1000
        for _ in range(SAMPLES):
            start = time.monotonic_ns()
            time.sleep(target)
            over.append(time.monotonic_ns() - start - round(target * 1e9))
        over.sort()
        n = len(over)
        key = str(ms)
        samples[key] = over
        summary[key] = dict(samples=n, median_ns=over[n // 2],
                            p95_ns=over[int(n * .95)], p99_ns=over[int(n * .99)],
                            p999_ns=over[int(n * .999)], max_ns=over[-1], min_ns=over[0],
                            over_1ms=sum(value > 1_000_000 for value in over))
    return summary, samples


def recorded_work_ns(rate_jsonl):
    """Per-group actual work durations from a real run's rate trace."""
    work = []
    for line in Path(rate_jsonl).open():
        row = json.loads(line)
        if row["kind"] == "rate_group_end":
            work.append(row["actual_end_ns"] - row["actual_start_ns"])
    return work


def simulate_creep(work_ns, overshoot_pool, guard_ns):
    """Labeled simulation of the release loop; not the production path.

    For every adjacent pair of group starts, replay the previous group's measured
    work and the production loop's repeated max-2ms sleeps. The final guard is
    represented as a perfect spin to the release edge. Returns incremental
    start-to-start excess over the fixed 8ms period, plus sleep-call counts.
    """
    overshoot_pool = list(overshoot_pool)
    if not overshoot_pool:
        raise ValueError("overshoot pool is empty")
    cursor = 0
    creep = 0
    previous_start = 0
    sleep_calls = 0
    sleep_crossings = 0
    for work in work_ns[:-1]:
        now = previous_start + work
        earliest = previous_start + PERIOD_NS
        while now < earliest:
            remaining = earliest - now
            if remaining <= guard_ns:
                now = earliest
                break
            slept = min(remaining - guard_ns, 2_000_000)
            over = overshoot_pool[cursor % len(overshoot_pool)]
            cursor += 1
            sleep_calls += 1
            now += slept + over
            if now > earliest:
                sleep_crossings += 1
        excess = max(0, now - previous_start - PERIOD_NS)
        creep += excess
        previous_start = now
    return dict(creep_ns=creep, sleep_calls=sleep_calls,
                sleep_crossings=sleep_crossings)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rate-jsonl", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    overshoot, raw_overshoot = measure_sleep()
    work = recorded_work_ns(args.rate_jsonl)
    # Preserve and replay every measured value. Each duration bucket is sorted by
    # measure_sleep; interleaving equal ranks avoids privileging one requested duration.
    keys = [str(ms) for ms in DURATIONS_MS]
    pool = [raw_overshoot[key][index] for index in range(SAMPLES) for key in keys]
    creep_1ms = simulate_creep(work, pool, 1_000_000)
    creep_2ms = simulate_creep(work, pool, 2_000_000)
    result = {
        "schema": "wksim.rate-release-spin.v2",
        "scope": "Host sleep accuracy plus a labeled guard simulation; no production "
                 "change is licensed by this file",
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "wsl_distro_name": os.environ.get("WSL_DISTRO_NAME"),
        },
        "measurement": {"durations_ms": list(DURATIONS_MS), "samples_per_duration": SAMPLES},
        "sleep_overshoot": overshoot,
        "raw_sleep_overshoot_ns": raw_overshoot,
        "groups": len(work),
        "simulation": {
            "method": ("recorded group work plus repeated max-2ms sleeps; all sorted "
                       "overshoot samples interleaved by rank and duration; final guard "
                       "is a perfect spin; excludes between-group health/recording work"),
            "guard_1ms": creep_1ms,
            "guard_2ms": creep_2ms,
        },
        "rate_jsonl_sha256": __import__("hashlib").sha256(args.rate_jsonl.read_bytes()).hexdigest(),
        "benchmark_sha256": __import__("hashlib").sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=1)
        stream.write("\n")
    print(json.dumps({"groups": len(work), "guard_1ms": creep_1ms,
                      "guard_2ms": creep_2ms,
                      "sleep_median_ns": {k: v["median_ns"] for k, v in overshoot.items()}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
