"""Parent-probe callback subsets v2 for run uy9ov56b (read-only, stdlib only).

v2 corrections over inspect_parent_subsets.py (v1 preserved):
- BOTH selection filters are computed and reported under separate names:
  ``release_excess_ge_10us`` (v1's filter) and ``remaining_begin_ge_10us``
  (the task's actual threshold: remaining_begin >= 10us).
- The sleep==0/loop_health==0 subset is small (29 groups); its observed max
  remaining is reported as a SUBSET-LOCAL observation only.  It cannot rule
  out polling/descheduling inside callback-containing groups, and a callback
  being present does not mean the callback caused the late tail.
- No lateness allocation from aggregates; no OS/CPU cause claims.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

EXPECTED_PROBE_SHA256 = \
    "a8bac9ac84ba9960296bb6b43d6d39c6bbc17fa9fdc47adf7e05ce76d7066653"
DEFAULT_RAW = Path(
    "/root/wksim-release-acceptance-fe3/validation/joint-public-flight-uy9ov56b")
FLOOR_NS = 10_000
FILTERS = {
    "release_excess_ge_10us": lambda row: row["release_excess_ns"] >= FLOOR_NS,
    "remaining_begin_ge_10us": lambda row: row["_remaining_begin_ns"] >= FLOOR_NS,
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    probe_source = args.raw / ("source__Simulator__wksim_runtime__"
                               "joint_rate_probe.py.txt")
    probe_sha = hashlib.sha256(probe_source.read_bytes()).hexdigest()
    if probe_sha != EXPECTED_PROBE_SHA256:
        raise SystemExit(f"archived probe source differs: {probe_sha}")
    rate_path = args.raw / "rate.jsonl"

    started = []
    non_started = []
    with rate_path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("kind") != "rate_timing_probe":
                continue
            row["_remaining_begin_ns"] = max(
                0, row["terminal_ns"] - max(row["earliest_start_ns"],
                                            row["initial_health_end_ns"]))
            (started if row["outcome"] == "started"
             else non_started).append(row)

    def subset_key(row):
        return ("sleep=%s,loop_health=%s"
                % ("nonzero" if row["sleep_calls"] else "zero",
                   "nonzero" if row["loop_health_calls"] else "zero"))

    filters_out = {}
    for filter_name, selected in FILTERS.items():
        subsets = {}
        for row in started:
            bucket = subsets.setdefault(
                subset_key(row),
                dict(rows=0, selected_rows=0, remaining_sum_ns=0,
                     remaining_max_ns=0, release_excess_sum_ns=0))
            bucket["rows"] += 1
            if selected(row):
                bucket["selected_rows"] += 1
                bucket["remaining_sum_ns"] += row["_remaining_begin_ns"]
                bucket["remaining_max_ns"] = max(
                    bucket["remaining_max_ns"], row["_remaining_begin_ns"])
                bucket["release_excess_sum_ns"] += row["release_excess_ns"]
        filters_out[filter_name] = {
            "selected_total": sum(b["selected_rows"] for b in subsets.values()),
            "subsets": subsets}

    both_zero = [row for row in started
                 if row["sleep_calls"] == 0 and row["loop_health_calls"] == 0]
    both_zero_note = {
        "rows": len(both_zero),
        "observed_max_remaining_begin_ns":
            max((row["_remaining_begin_ns"] for row in both_zero), default=None),
        "scope": "subset-local observation only; says nothing about "
                 "callback-containing groups, where polling/descheduling "
                 "inside the tail is not ruled out",
    }

    def slim(row):
        return {key: row[key] for key in (
            "start_tick", "outcome", "release_excess_ns",
            "_remaining_begin_ns", "entry_ns", "terminal_ns",
            "earliest_start_ns", "initial_health_end_ns",
            "entry_to_initial_health_ns", "loop_health_ns", "loop_health_calls",
            "sleep_calls", "sleep_elapsed_ns", "sleep_max_overshoot_ns",
            "final_spin_other_ns")}

    largest = sorted(started, key=lambda row: row["_remaining_begin_ns"],
                     reverse=True)[:10]

    result = {
        "schema": "wksim.parent-callback-subsets.v2",
        "supersedes": "wksim.parent-callback-subsets.v1 "
                      "(parent-subsets-uy9ov56b.json, preserved)",
        "run_id": "joint-public-flight-uy9ov56b",
        "inputs": {
            "rate_jsonl": hashlib.sha256(rate_path.read_bytes()).hexdigest(),
            "probe_source": probe_sha,
        },
        "started_rows": len(started),
        "non_started_rows": len(non_started),
        "floor_ns": FLOOR_NS,
        "filters": filters_out,
        "both_zero_subset": both_zero_note,
        "largest_remaining": [slim(row) for row in largest],
        "last_non_started": slim(non_started[-1]) if non_started else None,
        "limits": [
            "Callback presence never implies the callback caused the late "
            "tail; aggregates do not allocate lateness.",
            "Late-callback timestamps would LOCALIZE the tail regardless of "
            "cause; they do not establish callback responsibility.",
            "Shifted measurement windows give intervals, never OS/CPU causes.",
        ],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    if args.output.exists():
        raise SystemExit(f"output exists, refusing: {args.output}")
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({
        "started_rows": result["started_rows"],
        "filters": {name: {"selected_total": out["selected_total"],
                           "subsets": out["subsets"]}
                    for name, out in filters_out.items()},
        "both_zero_subset": both_zero_note,
        "largest_remaining_ticks": [
            (row["start_tick"], row["_remaining_begin_ns"]) for row in largest],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
