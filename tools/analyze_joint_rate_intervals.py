"""Attribute start-to-start creep in one retained 0.5x rate trace.

The trace exposes group work and the interval before the next group starts.
For every adjacent pair this tool verifies the exact identity

    creep = previous_work_over + release_excess

It does not claim that release_excess can be split into health checks, record
writes, sleep overshoot, or scheduler delay without more instrumentation.

Usage: python3 -B tools/analyze_joint_rate_intervals.py TRACE --output NEW.json
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


PERIOD_NS = 8_000_000
TICKS_PER_GROUP = 4
_EPOCH = re.compile(r"[0-9a-f]{32}")
_PAIR_FIELDS = (
    "epoch",
    "segment_id",
    "request_id",
    "requested_rate",
    "transition",
    "start_tick",
    "end_tick",
    "ideal_start_ns",
    "ideal_end_ns",
    "earliest_start_ns",
    "actual_start_ns",
)
_INTEGER_FIELDS = (
    "tick",
    "segment_id",
    "start_tick",
    "end_tick",
    "ideal_start_ns",
    "ideal_end_ns",
    "earliest_start_ns",
    "actual_start_ns",
    "lateness_ns",
)


def _integer(row, key, number):
    if key not in row or isinstance(row[key], bool) or not isinstance(row[key], int):
        raise ValueError(f"line {number}: {key} must be an integer")
    return row[key]


def _validate_common(row, number):
    if not isinstance(row, dict):
        raise ValueError(f"line {number}: record must be an object")
    for key in _INTEGER_FIELDS:
        _integer(row, key, number)
    epoch = row.get("epoch")
    if not isinstance(epoch, str) or _EPOCH.fullmatch(epoch) is None:
        raise ValueError(f"line {number}: epoch must be 32 lowercase hex characters")
    request_id = row.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError(f"line {number}: request_id must be a non-empty string")
    rate = row.get("requested_rate")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate != 0.5:
        raise ValueError(f"line {number}: requested_rate must be exactly 0.5")
    if row.get("transition") is not False:
        raise ValueError(f"line {number}: transition must be false")
    if row["segment_id"] < 0 or row["start_tick"] < 0:
        raise ValueError(f"line {number}: segment_id and start_tick must be nonnegative")
    if row["end_tick"] != row["start_tick"] + TICKS_PER_GROUP:
        raise ValueError(f"line {number}: group must span exactly four ticks")
    if row["ideal_end_ns"] - row["ideal_start_ns"] != PERIOD_NS:
        raise ValueError(f"line {number}: ideal group period must be exactly 8 ms")
    if row["actual_start_ns"] < row["earliest_start_ns"]:
        raise ValueError(f"line {number}: group started before its release boundary")


def _finish_group(start, start_line, end, end_line):
    _validate_common(end, end_line)
    if start["tick"] != start["start_tick"]:
        raise ValueError(f"line {start_line}: start tick does not match start_tick")
    if end["tick"] != end["end_tick"]:
        raise ValueError(f"line {end_line}: end tick does not match end_tick")
    if "actual_end_ns" not in end:
        raise ValueError(f"line {end_line}: missing actual_end_ns")
    actual_end = _integer(end, "actual_end_ns", end_line)
    for key in _PAIR_FIELDS:
        if end[key] != start[key]:
            raise ValueError(f"line {end_line}: end record changes {key}")
    if actual_end < start["actual_start_ns"]:
        raise ValueError(f"line {end_line}: group ends before it starts")
    expected_start_lateness = max(0, start["actual_start_ns"] - start["ideal_start_ns"])
    if start["lateness_ns"] != expected_start_lateness:
        raise ValueError(f"line {start_line}: start lateness is inconsistent")
    expected_end_lateness = max(0, actual_end - start["ideal_end_ns"])
    if end["lateness_ns"] != expected_end_lateness:
        raise ValueError(f"line {end_line}: end lateness is inconsistent")
    return {
        "start_tick": start["start_tick"],
        "actual_start_ns": start["actual_start_ns"],
        "actual_end_ns": actual_end,
        "work_ns": actual_end - start["actual_start_ns"],
        "ideal_start_ns": start["ideal_start_ns"],
        "ideal_end_ns": start["ideal_end_ns"],
        "earliest_start_ns": start["earliest_start_ns"],
    }


def load_groups(path):
    """Load complete group pairs in record order and verify one schedule."""
    groups = []
    pending = None
    identity = None
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"line {number}: malformed JSON: {error}") from error
            if not isinstance(row, dict):
                raise ValueError(f"line {number}: record must be an object")
            kind = row.get("kind")
            if kind not in ("rate_group_start", "rate_group_end"):
                continue
            _validate_common(row, number)
            row_identity = (
                row["epoch"], row["segment_id"], row["request_id"],
                row["requested_rate"], row["transition"],
            )
            if identity is None:
                identity = row_identity
            elif row_identity != identity:
                raise ValueError(f"line {number}: rate identity changed")
            if kind == "rate_group_start":
                if pending is not None:
                    raise ValueError(f"line {number}: group start arrived before prior end")
                pending = (row, number)
                continue
            if pending is None:
                raise ValueError(f"line {number}: group end has no preceding start")
            start, start_line = pending
            groups.append(_finish_group(start, start_line, row, number))
            pending = None
    if pending is not None:
        raise ValueError(f"line {pending[1]}: group start has no complete end")
    if not groups:
        raise ValueError("no complete rate groups in trace")

    for index, group in enumerate(groups):
        if index == 0:
            if group["earliest_start_ns"] != group["ideal_start_ns"]:
                raise ValueError("first group release boundary does not equal its ideal start")
            continue
        previous = groups[index - 1]
        if group["start_tick"] != previous["start_tick"] + TICKS_PER_GROUP:
            raise ValueError(f"group at tick {group['start_tick']} is not tick-contiguous")
        if group["ideal_start_ns"] != previous["ideal_end_ns"]:
            raise ValueError(f"group at tick {group['start_tick']} changes the ideal schedule")
        expected_earliest = max(
            group["ideal_start_ns"], previous["actual_start_ns"] + PERIOD_NS
        )
        if group["earliest_start_ns"] != expected_earliest:
            raise ValueError(f"group at tick {group['start_tick']} changes release scheduling")
        if group["actual_start_ns"] < previous["actual_end_ns"]:
            raise ValueError(f"group at tick {group['start_tick']} overlaps its predecessor")
        if group["actual_start_ns"] < previous["actual_start_ns"] + PERIOD_NS:
            raise ValueError(f"group at tick {group['start_tick']} catches up")

    return {
        "epoch": identity[0],
        "segment_id": identity[1],
        "request_id": identity[2],
        "requested_rate": identity[3],
        "transition": identity[4],
    }, groups


def _buckets(values):
    result = {}
    for name, low, high in (
        ("0-10us", 0, 10_000),
        ("10-100us", 10_000, 100_000),
        ("100-500us", 100_000, 500_000),
        ("0.5-1ms", 500_000, 1_000_000),
        ("1-2ms", 1_000_000, 2_000_000),
        (">2ms", 2_000_000, None),
    ):
        selected = [value for value in values if value > low and (high is None or value <= high)]
        result[name] = {"count": len(selected), "sum_ns": sum(selected)}
    result["zero"] = {"count": sum(value == 0 for value in values), "sum_ns": 0}
    return result


def analyze(path):
    identity, groups = load_groups(path)
    intervals = []
    for index in range(1, len(groups)):
        previous = groups[index - 1]
        current = groups[index]
        creep = current["actual_start_ns"] - previous["actual_start_ns"] - PERIOD_NS
        work_over = max(0, previous["work_ns"] - PERIOD_NS)
        release_excess = creep - work_over
        between = current["actual_start_ns"] - previous["actual_end_ns"]
        if creep < 0 or release_excess < 0 or between < 0:
            raise ValueError(f"interval ending at tick {current['start_tick']} is negative")
        if creep != work_over + release_excess:
            raise ValueError(f"interval ending at tick {current['start_tick']} does not close")
        intervals.append({
            "previous_start_tick": previous["start_tick"],
            "current_start_tick": current["start_tick"],
            "creep_ns": creep,
            "previous_work_ns": previous["work_ns"],
            "between_ns": between,
            "previous_work_over_ns": work_over,
            "release_excess_ns": release_excess,
        })

    creep_total = sum(item["creep_ns"] for item in intervals)
    work_over_total = sum(item["previous_work_over_ns"] for item in intervals)
    release_excess_total = sum(item["release_excess_ns"] for item in intervals)
    if creep_total != work_over_total + release_excess_total:
        raise ValueError("aggregate interval attribution does not close")
    def rank(field, total):
        running = 0
        result = []
        for item in sorted(intervals, key=lambda value: value[field], reverse=True)[:20]:
            running += item[field]
            result.append({**item, "cumulative_share": running / total if total else None})
        return result

    trace_path = Path(path)
    return {
        "schema": "wksim.rate-interval-attribution.v1",
        "status": "analyzed",
        "scope": "observable interval arithmetic only; no causal split of release_excess",
        "identity": identity,
        "period_ns": PERIOD_NS,
        "ticks_per_group": TICKS_PER_GROUP,
        "groups": len(groups),
        "intervals": len(intervals),
        "creep_total_ns": creep_total,
        "work_over_total_ns": work_over_total,
        "release_excess_total_ns": release_excess_total,
        "last_group_work_over_unattributed_ns": max(0, groups[-1]["work_ns"] - PERIOD_NS),
        "positive_creep_buckets": _buckets([item["creep_ns"] for item in intervals]),
        "positive_release_excess_buckets": _buckets(
            [item["release_excess_ns"] for item in intervals]
        ),
        "top_creep_intervals": rank("creep_ns", creep_total),
        "top_release_excess_intervals": rank("release_excess_ns", release_excess_total),
        "observable": [
            "group work", "between-group interval", "start-to-start creep",
            "previous work-over", "release excess",
        ],
        "not_separable_without_instrumentation": [
            "release excess split among health checks, record writes, sleep overshoot, and scheduler delay"
        ],
        "trace_sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(),
        "analyzer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = analyze(args.trace)
    except (ValueError, OSError, KeyError, TypeError) as error:
        result = {"status": "failed", "error": str(error)}
    try:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=1)
            stream.write("\n")
    except FileExistsError:
        print(json.dumps({"status": "failed", "error": "output already exists"}))
        return 1
    print(json.dumps({
        key: result.get(key) for key in (
            "status", "groups", "intervals", "creep_total_ns",
            "work_over_total_ns", "release_excess_total_ns", "error",
        )
    }))
    return 0 if result["status"] == "analyzed" else 1


if __name__ == "__main__":
    sys.exit(main())
