"""Aggregate sealed joint-rate timing-probe rows as diagnostic-only evidence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_joint_flight import lines, require
from audit_joint_rate import TIMING_PROBE_IDENTITY, timing_probe_identity


PHASES = (
    "entry_to_initial_health_ns",
    "loop_health_ns",
    "sleep_elapsed_ns",
    "final_spin_other_ns",
)
COUNTERS = ("loop_health_calls", "sleep_requested_ns", "sleep_calls", "sleep_max_overshoot_ns")


def _nonnegative_integer(row, field):
    value = row.get(field)
    require(type(value) is int and value >= 0, f"Invalid timing-probe {field}")
    return value


def analyze(path):
    path = Path(path)
    samples = [row for row in lines(path) if row.get("kind") == "rate_timing_probe"]
    require(samples, "No rate_timing_probe samples")
    epochs = {row.get("epoch") for row in samples}
    require(len(epochs) == 1 and next(iter(epochs)), "Timing probe crossed or lacks an epoch")
    outcomes = Counter()
    totals = Counter()
    maxima = Counter()
    for row in samples:
        timing_probe_identity(row)
        require(row.get("outcome") in ("started", "rate_unmet", "rejected"),
                "Invalid timing-probe outcome")
        require(type(row.get("start_tick")) is int and row.get("end_tick") == row["start_tick"] + 4,
                "Timing probe changed the four-tick group")
        phases = {field: _nonnegative_integer(row, field) for field in PHASES}
        counters = {field: _nonnegative_integer(row, field) for field in COUNTERS}
        observed = _nonnegative_integer(row, "observed_elapsed_ns")
        phase_total = _nonnegative_integer(row, "phase_total_ns")
        release_excess = _nonnegative_integer(row, "release_excess_ns")
        for field in ("entry_ns", "initial_health_end_ns", "terminal_ns",
                      "ideal_start_ns", "earliest_start_ns"):
            require(type(row.get(field)) is int, f"Invalid timing-probe {field}")
        require(phase_total == observed == sum(phases.values()),
                "Timing-probe phase accounting is not closed")
        require(release_excess == max(0, row["terminal_ns"] - row["earliest_start_ns"]),
                "Timing-probe release excess was relabelled")
        entry_lateness = max(0, row["entry_ns"] - row["earliest_start_ns"])
        post_entry_excess = max(0, row["terminal_ns"] - max(row["entry_ns"], row["earliest_start_ns"]))
        require(release_excess == entry_lateness + post_entry_excess,
                "Timing-probe release excess does not split at probe entry")
        require(counters["sleep_max_overshoot_ns"] <= phases["sleep_elapsed_ns"],
                "Timing-probe sleep overshoot exceeds elapsed sleep")
        outcomes[row["outcome"]] += 1
        for field, value in {**phases, **counters, "observed_elapsed_ns": observed,
                             "release_excess_ns": release_excess,
                             "entry_lateness_ns": entry_lateness,
                             "post_entry_excess_ns": post_entry_excess}.items():
            totals[field] += value
            maxima[field] = max(maxima[field], value)
    observed_total = totals["observed_elapsed_ns"]
    phase_summary = {
        field: {
            "total_ns": totals[field],
            "max_ns": maxima[field],
            "mean_ns": totals[field] / len(samples),
            "observed_share": totals[field] / observed_total if observed_total else 0.0,
        }
        for field in PHASES
    }
    return {
        "status": "diagnostic",
        "classification": "diagnostic_only",
        "production_performance": False,
        "rate_timing_probe": dict(TIMING_PROBE_IDENTITY),
        "epoch": next(iter(epochs)),
        "sample_count": len(samples),
        "outcomes": dict(sorted(outcomes.items())),
        "phases": phase_summary,
        "release_excess_ns": {
            "total": totals["release_excess_ns"],
            "max": maxima["release_excess_ns"],
            "mean": totals["release_excess_ns"] / len(samples),
            "entry_lateness": {
                "total": totals["entry_lateness_ns"],
                "max": maxima["entry_lateness_ns"],
                "mean": totals["entry_lateness_ns"] / len(samples),
            },
            "post_entry_excess": {
                "total": totals["post_entry_excess_ns"],
                "max": maxima["post_entry_excess_ns"],
                "mean": totals["post_entry_excess_ns"] / len(samples),
            },
        },
        "counters": {field: {"total": totals[field], "max": maxima[field]} for field in COUNTERS},
        "input": str(path),
        "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "limitations": [
            "Probe overhead is included; this diagnostic cannot establish a production rate pass.",
            "Phase attribution closes observed supervisor time but does not identify an OS or host root cause.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rate_jsonl", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    require(not args.output.exists(), "Refusing to overwrite diagnostic evidence")
    result = analyze(args.rate_jsonl)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "epoch", "sample_count", "outcomes")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
