"""Correlate validated 100-500us release-excess intervals with probe phases."""

import argparse
import hashlib
import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_joint_flight import lines, require
from analyze_joint_rate_intervals import PERIOD_NS, analyze as analyze_intervals, load_groups
from analyze_joint_rate_probe import PHASES, analyze as analyze_probe


LOWER_RELEASE_EXCESS_NS = 100_000
UPPER_RELEASE_EXCESS_NS = 500_000
SUMMARY_FIELDS = ("release_excess_ns",) + PHASES


def _nearest_rank(ordered, percent):
    rank = (percent * len(ordered) + 99) // 100
    return ordered[max(0, rank - 1)]

def _summary(values):
    ordered = sorted(values)
    if not ordered:
        return {
            "count": 0,
            "nonzero_count": 0,
            "total_ns": 0,
            "mean_ns": 0.0,
            "p95_ns": None,
            "p99_ns": None,
            "max_ns": None,
        }
    total = sum(ordered)
    return {
        "count": len(ordered),
        "nonzero_count": sum(value != 0 for value in ordered),
        "total_ns": total,
        "mean_ns": total / len(ordered),
        "p95_ns": _nearest_rank(ordered, 95),
        "p99_ns": _nearest_rank(ordered, 99),
        "max_ns": ordered[-1],
    }


def _probe_rows(path):
    result = {}
    for row in lines(path):
        if row.get("kind") != "rate_timing_probe":
            continue
        start_tick = row["start_tick"]
        require(start_tick not in result,
                f"Duplicate timing-probe start_tick {start_tick}")
        result[start_tick] = row
    return result


def _group_start_rows(path):
    result = {}
    for row in lines(path):
        if row.get("kind") != "rate_group_start":
            continue
        start_tick = row["start_tick"]
        require(start_tick not in result,
                f"Duplicate rate-group start_tick {start_tick}")
        result[start_tick] = row
    return result


def _check_join(group_start, probe):
    require(probe["outcome"] == "started",
            f"Missing started timing probe for start_tick {group_start['start_tick']}")
    for field in (
        "epoch",
        "start_tick",
        "end_tick",
        "ideal_start_ns",
        "earliest_start_ns",
    ):
        require(probe[field] == group_start[field],
                f"Timing probe {field} differs at start_tick {group_start['start_tick']}")
    require(probe["terminal_ns"] == group_start["actual_start_ns"],
            f"Timing probe actual start differs at start_tick {group_start['start_tick']}")


def _interval(previous, current):
    creep = current["actual_start_ns"] - previous["actual_start_ns"] - PERIOD_NS
    work_over = max(0, previous["work_ns"] - PERIOD_NS)
    release_excess = creep - work_over
    between = current["actual_start_ns"] - previous["actual_end_ns"]
    require(creep >= 0 and release_excess >= 0 and between >= 0,
            f"Interval ending at tick {current['start_tick']} is negative")
    require(creep == work_over + release_excess,
            f"Interval ending at tick {current['start_tick']} does not close")
    return {
        "previous_start_tick": previous["start_tick"],
        "current_start_tick": current["start_tick"],
        "creep_ns": creep,
        "previous_work_ns": previous["work_ns"],
        "between_ns": between,
        "previous_work_over_ns": work_over,
        "release_excess_ns": release_excess,
    }


def analyze(path):
    path = Path(path)
    interval_result = analyze_intervals(path)
    probe_result = analyze_probe(path)
    identity, groups = load_groups(path)
    require(interval_result["intervals"] == len(groups) - 1,
            "Interval validator and complete-group load disagree")
    require(probe_result["epoch"] == identity["epoch"],
            "Timing probes and rate groups use different epochs")
    probes = _probe_rows(path)
    group_starts = _group_start_rows(path)

    selected = []
    for previous, current in zip(groups, groups[1:]):
        interval = _interval(previous, current)
        probe = probes.get(current["start_tick"])
        require(probe is not None,
                f"Missing timing probe for start_tick {current['start_tick']}")
        group_start = group_starts.get(current["start_tick"])
        require(group_start is not None,
                f"Missing rate-group start for start_tick {current['start_tick']}")
        _check_join(group_start, probe)
        if not (LOWER_RELEASE_EXCESS_NS < interval["release_excess_ns"]
                <= UPPER_RELEASE_EXCESS_NS):
            continue
        selected.append({
            **interval,
            **{field: probe[field] for field in PHASES},
            "sleep_max_overshoot_ns": probe["sleep_max_overshoot_ns"],
        })

    summary_values = {
        field: [row[field] for row in selected] for field in SUMMARY_FIELDS
    }
    return {
        "schema": "wksim.rate-tail-phases.v1",
        "status": "diagnostic",
        "classification": "diagnostic_only",
        "diagnostic_only": True,
        "production_performance": False,
        "percentile_method": "nearest_rank",
        "epoch": identity["epoch"],
        "bucket": {
            "lower_ns": LOWER_RELEASE_EXCESS_NS,
            "upper_ns": UPPER_RELEASE_EXCESS_NS,
            "lower_inclusive": False,
            "upper_inclusive": True,
        },
        "interval_count": len(groups) - 1,
        "selected_count": len(selected),
        "selected": selected,
        "summary": {field: _summary(values) for field, values in summary_values.items()},
        "input": str(path),
        "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "tool": str(Path(__file__)),
        "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "limitations": [
            "correlation is not causal",
            "Probe overhead is included",
            "final_spin_other is residual",
            "No OS scheduler attribution",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rate_jsonl", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite diagnostic evidence: {args.output}")
    result = analyze(args.rate_jsonl)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({
        key: result[key] for key in ("status", "epoch", "interval_count", "selected_count")
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
