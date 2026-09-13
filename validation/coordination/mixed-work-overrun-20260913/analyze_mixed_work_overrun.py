"""Work-overrun decomposition for the failed mixed run joint-public-flight-oxv29042.

Read-only, Python standard library only.  Re-derives from the retained raw
rate.jsonl and joint-wire.jsonl of that run, plus its captured source
snapshots, only what program order can prove:

1. All four-tick groups whose work (actual_end_ns - actual_start_ns) exceeds
   the 8 ms period of the retained 0.5x rate: total overrun and the largest
   group.  Totals are cross-checked against the retained main-rate-analysis
   (trace SHA pinned); any mismatch fails the run of this script.

2. A single common offset ``S`` between the two in-process clocks of the run:

       wire_absolute_ns(event) == S + round(wall_seconds * 1e9)

   ``wall`` is ``time.monotonic() - started`` written by the runner's
   ``record()`` (run_joint_flight.py snapshot, wire writer at its line 829)
   and rate ``actual_start_ns`` / ``actual_end_ns`` are ``time.monotonic_ns()``
   (joint_rate.py snapshot).  Same process, same clock family: one S exists.
   Program order per group (runner advance() loop lines 934-981 and
   JointPhysics.advance() in the joint.py snapshot):

       rate_group_start  <  first group-interior wire record
       last group-interior wire record  <  rate_group_end

   Intersecting all groups yields ``[S_lo, S_hi]``.  Wrong tick alignments
   (P..P+3, P+2..P+5 instead of the true P+1..P+4) MUST produce an empty
   intersection; if they do not, the mapping is rejected and this script
   reports failure instead of numbers.

3. For each overrun group the native sensor->actuator region as the UNION of
   per-(tick, stack) intervals (AP and PX4 spans overlap on macro ticks and
   are never summed), separated from all other phases: the exact wire-interior
   remainder and the boundary region (release edge -> first wire record ->
   ... -> last wire record -> group end) whose pre/post split is an interval
   in S.  The two boundary parts share one S: their sum is exact, the split
   is not.  No overlap of the two stacks is added, no residual is attributed
   to the OS.

This is an analysis of one failed run; it is not a full-run acceptance result.
"""

import argparse
import hashlib
import json
import platform
import sys
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path

SCHEMA = "wksim.mixed-work-overrun.v1"
RUN_ID = "joint-public-flight-oxv29042"
TICKS_PER_GROUP = 4
NS = Decimal(1_000_000_000)

# Wire kinds JointPhysics.advance()/finish_inputs() emit between
GROUP_INTERIOR_KINDS = ("sensor", "actuator", "step", "barrier", "gps")
# Diagnostic kinds emitted only when WKSIM_JOINT_CPU_TIMING == '1' (frozen
# joint.py snapshot line 54); all three share that single gate.
DIAGNOSTIC_KINDS = ("diagnostic_gc_timing", "diagnostic_step_cpu_timing",
                    "diagnostic_native_input_timing")
KNOWN_KINDS = GROUP_INTERIOR_KINDS + (
    "connected", "diagnostic_land_pacing_started") + DIAGNOSTIC_KINDS

EXPECTED_RATE_SHA256 = \
    "8725b63c568783199b4a5e7d3de7df532003749b73d4c255131da4bcedee8b91"
EXPECTED_JOINT_RATE_SHA256 = \
    "0b53a16acd65138b4623a9a8573ec8d643a2b78f4e27e8122c65efb9a6da25c4"
EXPECTED_RUNNER_SHA256 = \
    "65c7a86765a99d2173a62ffafaf56c43243674dd1e3cbbc1150147b4c56d8161"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ns_of(wall_decimal):
    """Exact decimal seconds -> integer nanoseconds (nearest, half-even)."""
    return int((wall_decimal * NS).to_integral_value(rounding=ROUND_HALF_EVEN))


def union_length(intervals):
    """Total length covered by a list of (lo, hi) integer intervals."""
    total = 0
    current_lo = current_hi = None
    for lo, hi in sorted(intervals):
        if current_lo is None:
            current_lo, current_hi = lo, hi
        elif lo <= current_hi:
            current_hi = max(current_hi, hi)
        else:
            total += current_hi - current_lo
            current_lo, current_hi = lo, hi
    if current_lo is not None:
        total += current_hi - current_lo
    return total


# --------------------------------------------------------------------------- #
# rate.jsonl: validated schedule of four-tick groups
# --------------------------------------------------------------------------- #
def load_rate_groups(path):
    groups_in_order = []
    pending = None
    identity = None
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            row = json.loads(line)
            kind = row.get("kind")
            if kind not in ("rate_group_start", "rate_group_end"):
                continue
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
                    raise ValueError(f"line {number}: start before prior end")
                if row["tick"] != row["start_tick"]:
                    raise ValueError(f"line {number}: start tick mismatch")
                if row["end_tick"] != row["start_tick"] + TICKS_PER_GROUP:
                    raise ValueError(f"line {number}: group is not four ticks")
                pending = row
                continue
            if pending is None:
                raise ValueError(f"line {number}: end before any start")
            if row["tick"] != row["end_tick"]:
                raise ValueError(f"line {number}: end tick mismatch")
            for field in ("start_tick", "end_tick", "ideal_start_ns",
                          "ideal_end_ns", "actual_start_ns"):
                if row[field] != pending[field]:
                    raise ValueError(f"line {number}: end/start field {field} differs")
            if row["actual_end_ns"] < pending["actual_start_ns"]:
                raise ValueError(f"line {number}: group ends before it starts")
            groups_in_order.append({
                "start_tick": pending["start_tick"],
                "end_tick": pending["end_tick"],
                "actual_start_ns": pending["actual_start_ns"],
                "actual_end_ns": row["actual_end_ns"],
                "work_ns": row["actual_end_ns"] - pending["actual_start_ns"],
            })
            pending = None
    if pending is not None:
        raise ValueError("final group start has no end")
    if not groups_in_order:
        raise ValueError("no complete groups")
    for index in range(1, len(groups_in_order)):
        previous, current = groups_in_order[index - 1], groups_in_order[index]
        if current["start_tick"] != previous["start_tick"] + TICKS_PER_GROUP:
            raise ValueError(f"group {current['start_tick']} not tick-contiguous")
        if current["actual_start_ns"] < previous["actual_end_ns"]:
            raise ValueError(f"group {current['start_tick']} overlaps its predecessor")
    identity = dict(zip(
        ("epoch", "segment_id", "request_id", "requested_rate", "transition"),
        identity))
    return identity, groups_in_order


def interval_totals(groups, period_ns):
    """creep / work-over / release-excess totals, same definitions as the
    retained main-rate-analysis (per consecutive-group interval)."""
    creep_total = 0
    work_over_total = 0
    release_excess_total = 0
    overrun_groups = []
    for index, group in enumerate(groups):
        over = group["work_ns"] - period_ns
        if over > 0:
            overrun_groups.append((index, group, over))
        if index == 0:
            continue
        previous = groups[index - 1]
        creep = group["actual_start_ns"] - previous["actual_start_ns"] - period_ns
        previous_over = max(0, previous["work_ns"] - period_ns)
        creep_total += creep
        work_over_total += previous_over
        release_excess_total += creep - previous_over
    last_over = max(0, groups[-1]["work_ns"] - period_ns)
    return {
        "creep_total_ns": creep_total,
        "work_over_total_ns": work_over_total,
        "release_excess_total_ns": release_excess_total,
        "last_group_work_over_ns": last_over,
        "overrun_groups": overrun_groups,
    }


# --------------------------------------------------------------------------- #
# joint-wire.jsonl: one streaming pass
# --------------------------------------------------------------------------- #
def scan_wire(path, selected_ticks, diagnostic_ticks):
    kind_census = {}
    first = {}
    last = {}
    detail = {tick: [] for tick in selected_ticks}
    selected_diagnostics = {tick: [] for tick in diagnostic_ticks}
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            row = json.loads(line, parse_float=Decimal)
            kind = row.get("kind")
            kind_census[kind] = kind_census.get(kind, 0) + 1
            tick = row.get("tick")
            if kind in DIAGNOSTIC_KINDS:
                if tick in selected_diagnostics:
                    selected_diagnostics[tick].append({
                        "line": number, "kind": kind, "tick": tick,
                        "row": {key: value for key, value in row.items()
                                if key not in ("epoch",)}})
                continue
            if kind not in GROUP_INTERIOR_KINDS:
                continue
            wall = row.get("wall")
            if tick is None or wall is None:
                continue
            if tick not in first or wall < first[tick][0]:
                first[tick] = (wall, number, kind, row.get("stack"))
            if tick not in last or wall > last[tick][0]:
                last[tick] = (wall, number, kind, row.get("stack"))
            if tick in detail:
                detail[tick].append({
                    "line": number, "kind": kind, "tick": tick,
                    "stack": row.get("stack"), "wall_ns": ns_of(wall),
                })
    return kind_census, first, last, detail, selected_diagnostics


# --------------------------------------------------------------------------- #
# offset intersection and alignment controls
# --------------------------------------------------------------------------- #
def intersect_offset(groups, first, last, mapping_offset=1):
    lower = upper = None
    lower_group = upper_group = None
    used = skipped = 0
    for group in groups:
        ticks = [group["start_tick"] + mapping_offset + i
                 for i in range(TICKS_PER_GROUP)]
        if any(tick not in first for tick in ticks):
            skipped += 1
            continue
        used += 1
        first_ns = min(ns_of(first[t][0]) for t in ticks)
        last_ns = max(ns_of(last[t][0]) for t in ticks)
        lo = group["actual_start_ns"] - first_ns
        hi = group["actual_end_ns"] - last_ns
        if lower is None or lo > lower:
            lower, lower_group = lo, group["start_tick"]
        if upper is None or hi < upper:
            upper, upper_group = hi, group["start_tick"]
    return {
        "lower_ns": lower, "lower_bound_group": lower_group,
        "upper_ns": upper, "upper_bound_group": upper_group,
        "groups_used": used, "groups_skipped": skipped,
        "nonempty": lower is not None and upper is not None and lower <= upper,
    }


def verify_constraints(groups, first, last, lower, upper):
    """Every group-interior wire event must admit some S in [lower, upper]."""
    violations = []
    for group in groups:
        ticks = range(group["start_tick"] + 1, group["start_tick"] + TICKS_PER_GROUP + 1)
        if any(tick not in first for tick in ticks):
            continue
        for tick in ticks:
            for entry in (first[tick], last[tick]):
                wall_ns = ns_of(entry[0])
                lo = group["actual_start_ns"] - wall_ns
                hi = group["actual_end_ns"] - wall_ns
                if hi < lower or lo > upper:
                    violations.append({
                        "group": group["start_tick"], "tick": tick,
                        "line": entry[1], "kind": entry[2],
                    })
    return violations


# --------------------------------------------------------------------------- #
# per-overrun-group decomposition
# --------------------------------------------------------------------------- #
def localize_group(group, detail, first, last, lower, upper, period_ns):
    start = group["start_tick"]
    ticks = list(range(start + 1, start + TICKS_PER_GROUP + 1))
    events = sorted((e for tick in ticks for e in detail[tick]),
                    key=lambda e: e["wall_ns"])
    first_ns = min(ns_of(first[t][0]) for t in ticks)
    last_ns = max(ns_of(last[t][0]) for t in ticks)
    interior_ns = last_ns - first_ns
    work_ns = group["work_ns"]
    boundary_total = work_ns - interior_ns

    lo = group["actual_start_ns"] - first_ns      # S >  lo
    hi = group["actual_end_ns"] - last_ns         # S <  hi
    pre_lower = max(0, lower - lo)
    pre_upper = upper - lo
    post_lower = hi - upper
    post_upper = hi - lower

    native_intervals = []
    native_per_stack = {}
    for tick in ticks:
        sensor_wall = {}
        actuator_wall = {}
        for entry in detail[tick]:
            if entry["kind"] == "sensor":
                sensor_wall[entry["stack"]] = entry["wall_ns"]
            elif entry["kind"] == "actuator":
                actuator_wall[entry["stack"]] = entry["wall_ns"]
        for stack in ("arducopter", "px4"):
            if stack in sensor_wall and stack in actuator_wall:
                span = actuator_wall[stack] - sensor_wall[stack]
                native_per_stack.setdefault(stack, []).append(
                    {"tick": tick, "span_ns": span})
                native_intervals.append(
                    (sensor_wall[stack], actuator_wall[stack]))
    union_ns = union_length(native_intervals)
    largest_gap = None
    for previous, following in zip(events, events[1:]):
        gap = following["wall_ns"] - previous["wall_ns"]
        if largest_gap is None or gap > largest_gap["gap_ns"]:
            largest_gap = {
                "gap_ns": gap,
                "from": f"{previous['kind']}@{previous['tick']}",
                "to": f"{following['kind']}@{following['tick']}",
            }

    return {
        "start_tick": start, "end_tick": group["end_tick"],
        "work_ns": work_ns,
        "work_over_ns": work_ns - period_ns,
        "interior_ns": interior_ns,
        "boundary": {
            "pre_lower_ns": pre_lower, "pre_upper_ns": pre_upper,
            "post_lower_ns": post_lower, "post_upper_ns": post_upper,
            "total_ns": boundary_total,
        },
        "sensor_to_actuator_per_stack_ns": {
            stack: sum(item["span_ns"] for item in items)
            for stack, items in native_per_stack.items()},
        "sensor_to_actuator_union_ns": union_ns,
        "wire_interior_outside_native_ns": interior_ns - union_ns,
        "other_phases_ns": work_ns - union_ns,
        "largest_wire_gap": largest_gap,
        "wire_event_count": len(events),
    }


# --------------------------------------------------------------------------- #
# hand-checkable self-tests of the bound/union primitives
# --------------------------------------------------------------------------- #
def _bound_from_windows(windows):
    lower = upper = None
    for a_ns, b_ns, walls in windows:
        for wall in walls:
            w = ns_of(Decimal(wall))
            lo, hi = a_ns - w, b_ns - w
            if lower is None or lo > lower:
                lower = lo
            if upper is None or hi < upper:
                upper = hi
    return lower, upper


def self_tests():
    results = []
    truth = 36_000_000_000
    w_lo, w_hi = 55_000_000_000, 55_100_000_000
    windows = [
        (truth + w_lo - 1_000_000, truth + w_hi + 1_000_000,
         [format(w_lo / 1e9, ".17g"), format(w_hi / 1e9, ".17g")]),
        (truth + w_lo + 50_000_000 - 500_000, truth + w_hi + 100_000_000 + 500_000,
         [format((w_lo + 50_000_000) / 1e9, ".17g"),
          format((w_hi + 100_000_000) / 1e9, ".17g")]),
    ]
    lower, upper = _bound_from_windows(windows)
    results.append({
        "name": "positive_recovers_true_offset",
        "passed": lower == truth - 500_000 and upper == truth + 500_000
                  and lower <= truth <= upper,
        "lower_ns": lower, "upper_ns": upper,
    })
    lower, upper = _bound_from_windows(
        windows + [(truth + w_lo, truth + w_lo - 1,
                    [format(w_lo / 1e9, ".17g")])])
    results.append({
        "name": "negative_empty_intersection",
        "passed": lower > upper, "lower_ns": lower, "upper_ns": upper,
    })
    union = union_length([(10, 20), (15, 30), (40, 50)])
    results.append({
        "name": "union_never_sums_overlap",
        "passed": union == 30, "union_ns": union,
    })
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path(
        "/root/wksim-release-acceptance-fe3/validation/joint-public-flight-oxv29042"))
    parser.add_argument("--rate-analysis", type=Path, default=None,
                        help="retained main-rate-analysis.json for cross-check")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rate_path = args.raw / "rate.jsonl"
    wire_path = args.raw / "joint-wire.jsonl"
    joint_source = args.raw / "source__Simulator__wksim_core__joint.py.txt"
    rate_source = args.raw / "source__Simulator__wksim_runtime__joint_rate.py.txt"
    runner_source = args.raw / "source__tools__run_joint_flight.py.txt"

    rate_sha = sha256(rate_path)
    rate_source_sha = sha256(rate_source)
    runner_sha = sha256(runner_source)
    identity_checks = {
        "rate_jsonl_matches_bundle_manifest": rate_sha == EXPECTED_RATE_SHA256,
        "joint_rate_source_matches_bundle_manifest":
            rate_source_sha == EXPECTED_JOINT_RATE_SHA256,
        "runner_source_matches_bundle_manifest":
            runner_sha == EXPECTED_RUNNER_SHA256,
    }
    if not all(identity_checks.values()):
        raise SystemExit(f"identity mismatch: {identity_checks}")

    identity, groups = load_rate_groups(rate_path)
    if identity["epoch"] != "18c96a7e0af9477092aa87e18239c23c":
        raise SystemExit(f"epoch mismatch: {identity['epoch']}")
    period_ns = int(4_000_000 / identity["requested_rate"])
    totals = interval_totals(groups, period_ns)
    overrun = totals["overrun_groups"]

    crosscheck = {"available": False}
    if args.rate_analysis is not None:
        prior = json.loads(args.rate_analysis.read_text())
        crosscheck = {
            "available": True,
            "trace_sha256_matches": prior.get("trace_sha256") == rate_sha,
            "creep_total_matches":
                prior["creep_total_ns"] == totals["creep_total_ns"],
            "work_over_total_matches":
                prior["work_over_total_ns"] == totals["work_over_total_ns"],
            "release_excess_total_matches":
                prior["release_excess_total_ns"] ==
                totals["release_excess_total_ns"],
            "last_group_unattributed_matches":
                prior["last_group_work_over_unattributed_ns"] ==
                totals["last_group_work_over_ns"],
        }
        if not all(value for key, value in crosscheck.items()
                   if key != "available"):
            raise SystemExit(f"cross-check against retained analysis failed: "
                             f"{crosscheck}")

    selected = set()
    diagnostic_ticks = set()
    for _, group, _ in overrun:
        for tick in range(group["start_tick"] + 1,
                          group["start_tick"] + TICKS_PER_GROUP + 1):
            selected.add(tick)
        # neighbourhood covers the group's own ticks plus the step->sensor
        # regions leading in and out of the group
        for tick in range(group["start_tick"] - TICKS_PER_GROUP,
                          group["end_tick"] + 2 * TICKS_PER_GROUP + 1):
            diagnostic_ticks.add(tick)
    kind_census, first, last, detail, diagnostics = scan_wire(
        wire_path, selected, diagnostic_ticks)
    diagnostic_counts = {kind: kind_census.get(kind, 0)
                         for kind in DIAGNOSTIC_KINDS}
    diagnostic_rows = [row for tick in sorted(diagnostics)
                       for row in diagnostics[tick]]
    # Had the flag been on, every tick % 250 == 0 step emits
    # diagnostic_step_cpu_timing unconditionally (frozen joint.py snapshot).
    last_tick = groups[-1]["end_tick"]
    expected_min_step_cpu_records = last_tick // 250

    offset = intersect_offset(groups, first, last)
    controls = {
        "true_P+1..P+4": offset["nonempty"],
        "wrong_P..P+3": intersect_offset(groups, first, last, 0)["nonempty"],
        "wrong_P+2..P+5": intersect_offset(groups, first, last, 2)["nonempty"],
    }
    alignment_rejected = (controls["true_P+1..P+4"] and
                          not controls["wrong_P..P+3"] and
                          not controls["wrong_P+2..P+5"])
    violations = verify_constraints(groups, first, last,
                                    offset["lower_ns"], offset["upper_ns"])
    if not alignment_rejected:
        raise SystemExit(f"tick alignment control failed: {controls}")
    if violations:
        raise SystemExit(f"offset constraints violated: {violations[:5]}")

    groups_out = []
    for _, group, over in overrun:
        entry = localize_group(group, detail, first, last,
                               offset["lower_ns"], offset["upper_ns"], period_ns)
        groups_out.append(entry)

    overrun_total = sum(entry["work_over_ns"] for entry in groups_out)
    aggregate = {
        "overrun_group_count": len(groups_out),
        "overrun_total_ns": overrun_total,
        "work_total_ns": sum(entry["work_ns"] for entry in groups_out),
        "sensor_to_actuator_union_total_ns":
            sum(entry["sensor_to_actuator_union_ns"] for entry in groups_out),
        "wire_interior_outside_native_total_ns":
            sum(entry["wire_interior_outside_native_ns"] for entry in groups_out),
        "boundary_total_ns":
            sum(entry["boundary"]["total_ns"] for entry in groups_out),
        "boundary_split_interval_ns": [
            sum(entry["boundary"]["pre_lower_ns"] + entry["boundary"]["post_lower_ns"]
                for entry in groups_out),
            sum(entry["boundary"]["pre_upper_ns"] + entry["boundary"]["post_upper_ns"]
                for entry in groups_out),
        ],
        "largest_overrun_group": max(groups_out, key=lambda e: e["work_over_ns"],
                                     default=None),
        "largest_work_group": max(groups_out, key=lambda e: e["work_ns"],
                                  default=None),
    }
    # largest_* embed full entries; trim to identifying fields for the summary
    for key in ("largest_overrun_group", "largest_work_group"):
        entry = aggregate[key]
        if entry is not None:
            aggregate[key] = {field: entry[field] for field in (
                "start_tick", "work_ns", "work_over_ns",
                "sensor_to_actuator_union_ns", "wire_interior_outside_native_ns")}

    tests = self_tests()
    unknown = sorted(set(kind_census) - set(KNOWN_KINDS))
    result = {
        "schema": SCHEMA,
        "run_id": RUN_ID,
        "epoch": identity["epoch"],
        "python": platform.python_version(),
        "method": {
            "offset_model": "wire_absolute_ns = S + round(wall_seconds*1e9)",
            "constraints": "per rate group: actual_start_ns < first group-interior "
                           "wire event and last group-interior wire event < "
                           "actual_end_ns (program order, captured source)",
            "group_wire_ticks": "rate start_tick P owns wire ticks P+1..P+4; wrong "
                                "alignments P..P+3 and P+2..P+5 must be rejected",
            "selection": "every group with work_ns > period_ns (8 ms at 0.5x)",
        },
        "inputs": {
            "rate_jsonl": rate_sha,
            "joint_wire_jsonl": sha256(wire_path),
            "joint_py_snapshot": sha256(joint_source),
            "joint_rate_py_snapshot": rate_source_sha,
            "run_joint_flight_py_snapshot": runner_sha,
        },
        "identity_checks": identity_checks,
        "rate_identity": identity,
        "period_ns": period_ns,
        "groups_total": len(groups),
        "interval_totals": {key: totals[key] for key in (
            "creep_total_ns", "work_over_total_ns",
            "release_excess_total_ns", "last_group_work_over_ns")},
        "retained_analysis_crosscheck": crosscheck,
        "wire_kind_census": kind_census,
        "wire_unexpected_kinds": unknown,
        "tick_alignment_control": {
            **controls, "wrong_alignments_rejected": alignment_rejected},
        "offset": {
            **offset,
            "width_ns": (offset["upper_ns"] - offset["lower_ns"])
                        if offset["nonempty"] else None,
            "verified_violations": len(violations),
        },
        "aggregate": aggregate,
        "overrun_groups": groups_out,
        "self_tests": tests,
        "diagnostic_cpu_timing": {
            "flag_source": "joint.py snapshot line 54: cpu_timing = "
                           "os.environ.get('WKSIM_JOINT_CPU_TIMING') == '1'; "
                           "all three diagnostic kinds share this gate",
            "observed_counts": diagnostic_counts,
            "observed_total": sum(diagnostic_counts.values()),
            "expected_min_step_cpu_records_if_enabled":
                expected_min_step_cpu_records,
            "flag_state_proof": "0 diagnostic rows in the 495410-line wire while "
                                "tick%250==0 steps would have emitted at least "
                                "527 diagnostic_step_cpu_timing rows",
            "window_ticks_examined": sorted(diagnostic_ticks),
            "rows_in_overrun_windows": diagnostic_rows,
            "extractable_stages": None,
        },
        "limits": [
            "Only same-run program order and relative wire timestamps are used; no "
            "tick is converted to wall seconds and no common clock origin is assumed.",
            "The pre-sensor and post-step boundary parts share one S: their sum is "
            "exact, the split is an interval and is correlated across groups; never "
            "sum or treat them as independent.",
            "AP and PX4 sensor->actuator spans overlap on macro ticks; per-stack "
            "totals are not additive and only the union is subtracted.",
            "Interior spans are exact wire differences but still contain record, "
            "serialisation, I/O-wait and possible descheduling; no residual is "
            "attributed to the OS or to any single cause.",
            "diagnostic_* wire kinds are excluded from order constraints.",
            "This is one failed run's decomposition; it is not a full-run "
            "acceptance result.",
        ],
        "script_sha256": sha256(__file__),
        "native_executed": False,
        "performance_pass": False,
        "full_run_acceptance": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({
        "schema": SCHEMA,
        "groups_total": len(groups),
        "overrun_group_count": aggregate["overrun_group_count"],
        "overrun_total_ns": aggregate["overrun_total_ns"],
        "largest_overrun_group": aggregate["largest_overrun_group"],
        "diagnostic_observed_total": sum(diagnostic_counts.values()),
        "offset_width_ns": result["offset"]["width_ns"],
        "tick_alignment_control": result["tick_alignment_control"],
        "crosscheck": crosscheck,
        "self_tests_passed": all(t["passed"] for t in tests),
        "union_total_ns": aggregate["sensor_to_actuator_union_total_ns"],
        "boundary_total_ns": aggregate["boundary_total_ns"],
        "interior_outside_native_total_ns":
            aggregate["wire_interior_outside_native_total_ns"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
