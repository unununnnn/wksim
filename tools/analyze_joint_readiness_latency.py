"""Decompose retained 1x ground-readiness rate failures; offline only.

Reads only the SHA256-pinned retained evidence declared by an evidence root's
failure-facts.json (the validation/lunar-20-epoch-1 set for #62 declares two
evidence records: epoch-raw and case/run/epochs/2a8d5df1…).  Every declared run is
decomposed: each timed group's work, start lateness and start-to-start creep
inside the ground-readiness / stabilization window, joined with the sealed
scene phase.  It verifies the exact interval identity

    creep = previous_work_over + release_excess

cross-checks every latch row against faults.json and result.json, and requires
the computed latch to equal the pinned expectation byte-exactly (measured_rate
included; no tolerance).  It does not claim which health check, write, sleep
or scheduler delay produced the release excess; that causal split needs the
deferred tracefs slice.

Usage:
    python3 -B tools/analyze_joint_readiness_latency.py EVIDENCE_DIR \
        [--period-ns 4000000] [--output NEW.json]
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_joint_rate_intervals import TICKS_PER_GROUP, _EPOCH

TICK_NS = 1_000_000
DEFAULT_PERIOD_NS = 4_000_000          # 1x: four 1 ms ticks per group
LATE_LIMIT_NS = 100_000_000            # frozen 100 ms supervision cap
STABILIZATION_NS = 2_000_000_000       # frozen stabilization_s = 2
SCHEMA = "wksim.readiness-latency.v2"
RETAINED_PHASES = frozenset(("running", "faulted"))
FACTS = "failure-facts.json"
CONSUMED = ("rate.jsonl", "clock.jsonl", "scene-lifecycle.jsonl",
            "faults.json", "result.json")
EXPECT_FIELDS = ("tick", "lateness_ns", "completed_groups", "measured_rate")
_PAIR_FIELDS = (
    "epoch", "segment_id", "request_id", "requested_rate", "transition",
    "start_tick", "end_tick", "ideal_start_ns", "ideal_end_ns",
    "earliest_start_ns", "actual_start_ns",
)
_SUMMARY_FIELDS = (
    "epoch", "requested_rate", "request_id", "segment_id", "latched",
    "anchor", "measured_rate", "measurement", "completed_groups",
    "worst_lateness_ns", "steady_after_ns",
)
_RESULT_SUMMARY_FIELDS = tuple(field for field in _SUMMARY_FIELDS if field != "epoch")
_INTEGER_FIELDS = (
    "tick", "segment_id", "start_tick", "end_tick", "ideal_start_ns",
    "ideal_end_ns", "earliest_start_ns", "actual_start_ns", "lateness_ns",
)
_HEX64 = re.compile(r"[0-9a-f]{64}")
_RUN_DECLARATION_FIELDS = frozenset((
    "evidence_id", "expected_run_id", "epoch", "directory", "expect", "sha256"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _integer(row, key, number):
    if key not in row or isinstance(row[key], bool) or not isinstance(row[key], int):
        raise ValueError(f"line {number}: {key} must be an integer")
    return row[key]


def _epoch_of(row, number):
    epoch = row.get("epoch")
    if not isinstance(epoch, str) or _EPOCH.fullmatch(epoch) is None:
        raise ValueError(f"line {number}: epoch must be 32 lowercase hex characters")
    return epoch


def _safe_run_dir(evidence, run):
    """Resolve one declared run directory; reject escape, links, absence."""
    directory = run.get("directory")
    if not isinstance(directory, str) or not directory:
        raise ValueError("run directory must be non-empty text")
    candidate = Path(directory)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"run directory escapes the evidence root: {directory!r}")
    path = evidence / candidate
    if path.is_symlink():
        raise ValueError(f"run directory is a symlink: {directory!r}")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(evidence) or resolved != path:
        raise ValueError(f"run directory resolves outside or through links: {directory!r}")
    if not path.is_dir():
        raise ValueError(f"run directory missing: {directory!r}")
    return path


def verify_runs(evidence):
    """Fail closed unless every declared run input matches its sealed SHA256."""
    evidence = Path(evidence)
    facts_path = evidence / FACTS
    if facts_path.is_symlink() or not facts_path.is_file():
        raise ValueError("missing failure-facts.json pin set")
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    if facts.get("issue") != 62 or facts.get("fault") != "RateUnmet":
        raise ValueError("pin set is not the #62 RateUnmet failure record")
    if "sha256" in facts:
        raise ValueError("legacy top-level pin set must be removed; runs[].sha256 is the sole authority")
    if facts.get("epochs_run") != 1:
        raise ValueError("epochs_run must stay 1: the retained case is not an epoch-2 run")
    runs = facts.get("runs")
    if not isinstance(runs, list) or len(runs) != 2:
        raise ValueError("failure-facts.json must declare exactly two runs")
    root = evidence.resolve()
    declared = []
    seen_evidence_ids = set()
    seen_epochs = set()
    seen_directories = set()
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError("run declaration must be an object")
        if set(run) != _RUN_DECLARATION_FIELDS:
            raise ValueError("run declaration must contain evidence_id, expected_run_id, epoch, directory, expect and sha256")
        evidence_id = run.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id or evidence_id in seen_evidence_ids:
            raise ValueError("evidence_id must be unique non-empty text")
        seen_evidence_ids.add(evidence_id)
        expected_run_id = run.get("expected_run_id")
        if not isinstance(expected_run_id, str) or not expected_run_id:
            raise ValueError("expected_run_id must be non-empty text")
        declared_epoch = run.get("epoch")
        if not isinstance(declared_epoch, str) or _EPOCH.fullmatch(declared_epoch) is None:
            raise ValueError("declared epoch must be 32 lowercase hex characters")
        if declared_epoch in seen_epochs:
            raise ValueError("epochs must be distinct")
        seen_epochs.add(declared_epoch)
        path = _safe_run_dir(root, run)
        if run["directory"] in seen_directories:
            raise ValueError("run directories must be distinct")
        seen_directories.add(run["directory"])
        expect = run.get("expect")
        if not isinstance(expect, dict) or set(expect) != set(EXPECT_FIELDS):
            raise ValueError(f"evidence {evidence_id}: expectation fields differ")
        for key in ("tick", "lateness_ns", "completed_groups"):
            value = expect[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"evidence {evidence_id}: expect.{key} must be a nonnegative integer")
        if isinstance(expect["measured_rate"], bool) \
                or not isinstance(expect["measured_rate"], (int, float)) \
                or not 0 < expect["measured_rate"] < float("inf"):
            raise ValueError(f"evidence {evidence_id}: expect.measured_rate must be positive and finite")
        pins = run.get("sha256")
        if not isinstance(pins, dict) or set(pins) != set(CONSUMED):
            raise ValueError(f"evidence {evidence_id}: pin set must cover exactly {sorted(CONSUMED)}")
        declared.append({"evidence_id": evidence_id, "expected_run_id": expected_run_id,
                         "declared_epoch": declared_epoch, "path": path,
                         "directory": run["directory"], "expect": expect, "pins": pins})
    for run in declared:
        verified = {}
        for name in CONSUMED:
            expected = run["pins"][name]
            if not isinstance(expected, str) or not _HEX64.fullmatch(expected):
                raise ValueError(f"evidence {run['evidence_id']}: malformed pin for {name}")
            target = run["path"] / name
            if target.is_symlink() or not target.is_file():
                raise ValueError(f"evidence {run['evidence_id']}: pinned input missing or linked: {name}")
            actual = digest(target)
            if actual != expected:
                raise ValueError(f"evidence {run['evidence_id']}: pinned input drifted: {name}")
            verified[name] = actual
        run["input_sha256"] = verified
        del run["pins"]
    return facts, declared

def _validate_group_row(row, number, expected_rate, period_ns):
    if not isinstance(row, dict):
        raise ValueError(f"line {number}: record must be an object")
    for key in _INTEGER_FIELDS:
        _integer(row, key, number)
    _epoch_of(row, number)
    request_id = row.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError(f"line {number}: request_id must be a non-empty string")
    rate = row.get("requested_rate")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate != expected_rate:
        raise ValueError(f"line {number}: requested_rate must be exactly {expected_rate}")
    if row.get("transition") is not False:
        raise ValueError(f"line {number}: transition must be false")
    if row["segment_id"] < 0 or row["start_tick"] < 0:
        raise ValueError(f"line {number}: segment_id and start_tick must be nonnegative")
    if row["end_tick"] != row["start_tick"] + TICKS_PER_GROUP:
        raise ValueError(f"line {number}: group must span exactly four ticks")
    if row["ideal_end_ns"] - row["ideal_start_ns"] != period_ns:
        raise ValueError(f"line {number}: ideal group period must be exactly {period_ns} ns")
    if row["actual_start_ns"] < row["earliest_start_ns"]:
        raise ValueError(f"line {number}: group started before its release boundary")


def _finish_group(start, start_line, end, end_line):
    if start["tick"] != start["start_tick"]:
        raise ValueError(f"line {start_line}: start tick does not match start_tick")
    if end["tick"] != end["end_tick"]:
        raise ValueError(f"line {end_line}: end tick does not match end_tick")
    actual_end = _integer(end, "actual_end_ns", end_line)
    for key in _PAIR_FIELDS:
        if end[key] != start[key]:
            raise ValueError(f"line {end_line}: end record changes {key}")
    if actual_end < start["actual_start_ns"]:
        raise ValueError(f"line {end_line}: group ends before it starts")
    if start["lateness_ns"] != max(0, start["actual_start_ns"] - start["ideal_start_ns"]):
        raise ValueError(f"line {start_line}: start lateness is inconsistent")
    if end["lateness_ns"] != max(0, actual_end - start["ideal_end_ns"]):
        raise ValueError(f"line {end_line}: end lateness is inconsistent")
    return {
        "epoch": start["epoch"],
        "segment_id": start["segment_id"],
        "request_id": start["request_id"],
        "requested_rate": start["requested_rate"],
        "transition": start["transition"],
        "start_tick": start["start_tick"],
        "actual_start_ns": start["actual_start_ns"],
        "actual_end_ns": actual_end,
        "work_ns": actual_end - start["actual_start_ns"],
        "ideal_start_ns": start["ideal_start_ns"],
        "ideal_end_ns": start["ideal_end_ns"],
        "earliest_start_ns": start["earliest_start_ns"],
        "start_lateness_ns": start["lateness_ns"],
        "end_lateness_ns": end["lateness_ns"],
    }


def load_trace(path, expected_rate, period_ns):
    """Parse one retained rate trace and verify one exact 1x schedule."""
    groups = []
    bootstrap = []
    anchor = unmet = segment_end = None
    request = None
    requests = bootstraps = transport_inits = 0
    identity = None
    pending = pending_untimed = None
    for number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(f"line {number}: malformed JSON: {error}") from error
        if not isinstance(row, dict):
            raise ValueError(f"line {number}: record must be an object")
        kind = row.get("kind")
        epoch = _epoch_of(row, number)
        if identity is None:
            identity = epoch
        elif epoch != identity:
            raise ValueError(f"line {number}: epoch changed")
        if kind in ("rate_group_start", "rate_group_end"):
            _validate_group_row(row, number, expected_rate, period_ns)
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
        elif kind in ("untimed_group_start", "untimed_group_end"):
            if row.get("classification") != "bootstrap":
                raise ValueError(f"line {number}: unexpected untimed classification")
            if kind == "untimed_group_start":
                if pending_untimed is not None:
                    raise ValueError(f"line {number}: untimed start arrived before prior end")
                pending_untimed = (row, number)
                continue
            if pending_untimed is None:
                raise ValueError(f"line {number}: untimed end has no preceding start")
            start, _ = pending_untimed
            actual_end = _integer(row, "actual_end_ns", number)
            actual_start = _integer(start, "actual_start_ns", number)
            if actual_end < actual_start:
                raise ValueError(f"line {number}: untimed group ends before it starts")
            bootstrap.append({"start_tick": start["start_tick"], "work_ns": actual_end - actual_start})
            pending_untimed = None
        elif kind == "rate_request":
            requests += 1
            if row.get("requested_rate") != expected_rate:
                raise ValueError(f"line {number}: requested rate differs from the frozen 1x request")
            if request is not None:
                raise ValueError(f"line {number}: second rate request")
            request = row
        elif kind == "rate_bootstrap":
            bootstraps += 1
        elif kind == "transport_initialized":
            transport_inits += 1
        elif kind == "rate_anchor":
            if anchor is not None:
                raise ValueError(f"line {number}: second rate anchor")
            anchor = row
        elif kind == "rate_unmet":
            if unmet is not None:
                raise ValueError(f"line {number}: second rate_unmet latch")
            unmet = row
        elif kind == "rate_segment_end":
            if segment_end is not None:
                raise ValueError(f"line {number}: second segment end")
            segment_end = row
        else:
            raise ValueError(f"line {number}: unknown record kind {kind!r}")
    if pending is not None:
        raise ValueError(f"line {pending[1]}: group start has no complete end")
    if pending_untimed is not None:
        raise ValueError(f"line {pending_untimed[1]}: untimed group start has no complete end")
    if not groups:
        raise ValueError("no complete rate groups in trace")
    if requests != 1 or bootstraps != 1 or transport_inits != 1:
        raise ValueError("trace must carry exactly one request, bootstrap and transport record")
    if anchor is None:
        raise ValueError("trace has no rate anchor")
    if anchor.get("latched") is not False:
        raise ValueError("anchor must not be latched")

    first = groups[0]
    anchor_body = anchor.get("anchor")
    if (not isinstance(anchor_body, dict) or anchor_body.get("transition") is not False
            or anchor_body["tick"] != first["start_tick"]
            or anchor_body["wall_ns"] != first["ideal_start_ns"]):
        raise ValueError("anchor does not match the first timed group")
    for key in ("epoch", "requested_rate", "request_id", "segment_id"):
        if anchor.get(key) != first[key]:
            raise ValueError(f"anchor {key} differs from the first timed group")
    if request is None or request.get("epoch") != identity or request.get("request_id") != first["request_id"]:
        raise ValueError("rate request identity differs from the timed groups")
    if request.get("requested_rate") != first["requested_rate"]:
        raise ValueError("rate request value differs from the timed groups")
    for index, group in enumerate(groups):
        for key in ("epoch", "requested_rate", "request_id", "segment_id", "transition"):
            if group[key] != first[key]:
                raise ValueError(f"group at tick {group['start_tick']} changes {key}")
        if group["ideal_start_ns"] != anchor_body["wall_ns"] + index * period_ns:
            raise ValueError(f"group at tick {group['start_tick']} changes the ideal schedule")
        if index == 0:
            if group["earliest_start_ns"] != group["ideal_start_ns"]:
                raise ValueError("first group release boundary does not equal its ideal start")
            continue
        previous = groups[index - 1]
        if group["start_tick"] != previous["start_tick"] + TICKS_PER_GROUP:
            raise ValueError(f"group at tick {group['start_tick']} is not tick-contiguous")
        expected_earliest = max(group["ideal_start_ns"], previous["actual_start_ns"] + period_ns)
        if group["earliest_start_ns"] != expected_earliest:
            raise ValueError(f"group at tick {group['start_tick']} changes release scheduling")
        if group["actual_start_ns"] < previous["actual_end_ns"]:
            raise ValueError(f"group at tick {group['start_tick']} overlaps its predecessor")
        if group["actual_start_ns"] < previous["actual_start_ns"] + period_ns:
            raise ValueError(f"group at tick {group['start_tick']} catches up")
    return identity, anchor_body, anchor, groups, bootstrap, unmet, segment_end


def load_clock(path, epoch, latch_tick):
    """Per-tick raw authority phases through exactly the latch tick."""
    phases = {}
    ticks = []
    for number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        row = json.loads(raw)
        if _epoch_of(row, number) != epoch:
            raise ValueError(f"line {number}: clock epoch differs from trace")
        tick = _integer(row, "tick", number)
        phase = row.get("phase")
        if not isinstance(phase, str) or phase not in RETAINED_PHASES:
            raise ValueError(f"line {number}: raw clock phase must be running or faulted")
        if tick in phases:
            raise ValueError(f"line {number}: duplicate clock tick")
        phases[tick] = phase
        ticks.append(tick)
    if not ticks:
        raise ValueError("clock has no raw tick records")
    if ticks[-1] != latch_tick or max(ticks) != latch_tick:
        raise ValueError("raw clock last/max tick must equal the latch tick")
    if ticks != list(range(ticks[0], latch_tick + 1)):
        raise ValueError("clock ticks are not contiguous")
    if phases[latch_tick] != "running":
        raise ValueError("raw clock phase at the latch tick must be running")
    if any(phase == "faulted" for phase in phases.values()):
        raise ValueError("raw clock faulted phase appeared before scene fault publication")
    return phases


def load_scene(path, epoch, expected_run_id):
    """Read the scene stream and retain enough order to audit the latch."""
    events = []
    for number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(f"line {number}: malformed scene JSON: {error}") from error
        if not isinstance(row, dict):
            raise ValueError(f"line {number}: scene record must be an object")
        if _epoch_of(row, number) != epoch:
            raise ValueError(f"line {number}: scene epoch differs from trace")
        tick = _integer(row, "tick", number)
        if tick < 0:
            raise ValueError(f"line {number}: scene tick must be nonnegative")
        kind = row.get("kind")
        phase = row.get("phase")
        if not isinstance(kind, str) or not kind:
            raise ValueError(f"line {number}: scene kind must be non-empty text")
        if not isinstance(phase, str) or phase not in RETAINED_PHASES:
            raise ValueError(f"line {number}: scene phase must be running or faulted")
        message = row.get("message")
        if kind == "permission":
            if not isinstance(message, dict) or not isinstance(message.get("run_id"), str):
                raise ValueError(f"line {number}: permission message must carry run_id")
        if isinstance(message, dict) and "run_id" in message:
            if message["run_id"] != expected_run_id:
                raise ValueError(f"line {number}: scene message.run_id differs from expected_run_id")
        events.append({"tick": tick, "kind": kind, "phase": phase,
                       "has_message_run_id": isinstance(message, dict) and "run_id" in message,
                       "line": number})
    ticks = [event["tick"] for event in events]
    if ticks != sorted(ticks):
        raise ValueError("scene event ticks must be non-decreasing")
    if not any(event["has_message_run_id"] for event in events):
        raise ValueError("scene has no message.run_id identity")
    return events


def _require_shared(left, left_label, right, right_label, fields):
    for key in fields:
        if key not in left or key not in right:
            raise ValueError(f"{left_label}/{right_label} missing shared field {key}")
        if left[key] != right[key]:
            raise ValueError(f"{left_label}.{key} differs from {right_label}.{key}")


def verify_latch(run_dir, epoch, expected_run_id, anchor, anchor_row, unmet,
                 segment_end, groups, expect):
    """The latch must match every sealed cross-record and the pinned expectation."""
    if unmet is None:
        raise ValueError("trace has no rate_unmet latch; not a readiness failure trace")
    if unmet.get("latched") is not True or unmet.get("reason") != "resource_insufficient":
        raise ValueError("latch identity differs")
    lateness = _integer(unmet, "lateness_ns", 0)
    if lateness <= LATE_LIMIT_NS:
        raise ValueError("latch lateness within the frozen cap would be a pseudo-fault")
    if anchor_row.get("latched") is not False or anchor_row.get("reason") != "synchronized_boundary":
        raise ValueError("rate anchor identity differs")
    if anchor_row.get("tick") != anchor.get("tick") or anchor_row.get("anchor") != anchor:
        raise ValueError("rate anchor body differs from the canonical anchor")
    if anchor_row.get("measured_rate") is not None or anchor_row.get("completed_groups") != 0 \
            or anchor_row.get("worst_lateness_ns") != 0:
        raise ValueError("rate anchor must be an unlatched zero summary")
    if anchor_row.get("steady_after_ns") != anchor["wall_ns"] + STABILIZATION_NS:
        raise ValueError("rate anchor steady window boundary differs from the frozen 2 s contract")
    if segment_end is None or segment_end.get("reason") != "fault" \
            or segment_end.get("latched") is not True or segment_end.get("tick") != unmet["tick"]:
        raise ValueError("segment end record differs from the latch")
    _require_shared(anchor_row, "rate_anchor", unmet, "rate_unmet",
                    ("epoch", "requested_rate", "request_id", "segment_id",
                     "anchor", "measurement", "steady_after_ns"))
    _require_shared(unmet, "rate_unmet", segment_end, "rate_segment_end", _SUMMARY_FIELDS)
    if unmet.get("completed_groups") != len(groups):
        raise ValueError("latch completed_groups differs from the trace")
    observed = [lateness] + [g["start_lateness_ns"] for g in groups] + [g["end_lateness_ns"] for g in groups]
    if unmet.get("worst_lateness_ns") != max(observed):
        raise ValueError("latch worst_lateness_ns is not the observed maximum")
    # joint_rate.py:150-153: measured = completed * period / (last_end - anchor wall).
    anchor_wall = unmet["anchor"]["wall_ns"]
    measured = unmet.get("measured_rate")
    reproduced = len(groups) * (groups[0]["ideal_end_ns"] - groups[0]["ideal_start_ns"]) / (
        groups[-1]["actual_end_ns"] - anchor_wall)
    if measured != reproduced:
        raise ValueError("latch measured_rate does not reproduce from retained groups")
    latch = {"tick": unmet["tick"], "lateness_ns": lateness,
             "completed_groups": len(groups), "measured_rate": measured}
    # Exact equality with the pinned expectation; no tolerance anywhere.
    for key in EXPECT_FIELDS:
        if latch[key] != expect[key]:
            raise ValueError(f"latch {key} differs from the pinned expectation")
    faults = json.loads((run_dir / "faults.json").read_text(encoding="utf-8"))
    if not isinstance(faults, list) or len(faults) != 1:
        raise ValueError("faults.json must hold exactly one fault")
    fault = faults[0]
    authority = fault.get("authority") or {}
    if (fault.get("type") != "RateUnmet" or authority.get("tick") != unmet["tick"]
            or authority.get("epoch") != epoch
            or authority.get("fault") != "rate_unmet/resource_insufficient"
            or authority.get("phase") != "faulted"):
        raise ValueError("faults.json authority differs from the trace latch")
    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    if (result.get("status") != "failed" or result.get("epoch") != epoch
            or result.get("run_id") != expected_run_id):
        raise ValueError("result.json status/epoch/run_id differs from the evidence declaration")
    if "interrupt" not in str(result.get("error")).lower():
        raise ValueError("result.json error is not the latch-driven interruption")
    result_authority = result.get("authority") or {}
    if (result_authority.get("tick") != unmet["tick"]
            or result_authority.get("phase") != "faulted"
            or result_authority.get("epoch") != epoch
            or result_authority.get("fault") != "Owned joint epoch interrupted"):
        raise ValueError("result.json authority differs from the latch")
    last_segment = (result.get("rate") or {}).get("last_segment") or {}
    for key in ("requested_rate", "request_id", "segment_id", "latched", "anchor",
                 "measured_rate", "measurement", "completed_groups",
                 "worst_lateness_ns", "steady_after_ns"):
        if last_segment.get(key) != segment_end.get(key):
            raise ValueError("result.json last_segment differs from the segment end record")
    _require_shared(segment_end, "rate_segment_end", last_segment, "result.last_segment",
                    _RESULT_SUMMARY_FIELDS)
    expected_summary = {
        "completed_groups": len(groups),
        "worst_lateness_ns": max(observed),
        "measured_rate": reproduced,
    }
    for key, value in expected_summary.items():
        if unmet.get(key) != value or segment_end.get(key) != value or last_segment.get(key) != value:
            raise ValueError(f"{key} does not match the retained groups")
    return latch


def _nearest_rank(ordered, percent):
    rank = (percent * len(ordered) + 99) // 100
    return ordered[max(0, rank - 1)]


def _summary(values):
    if not values:
        return {"count": 0, "total_ns": 0, "p95_ns": None, "p99_ns": None, "max_ns": None}
    ordered = sorted(values)
    return {"count": len(values), "total_ns": sum(values),
            "p95_ns": _nearest_rank(ordered, 95), "p99_ns": _nearest_rank(ordered, 99),
            "max_ns": ordered[-1]}


def analyze_run(run, period_ns):
    epoch, anchor, anchor_row, groups, bootstrap, unmet, segment_end = load_trace(
        run["path"] / "rate.jsonl", TICKS_PER_GROUP * TICK_NS / period_ns, period_ns)
    if epoch != run["declared_epoch"]:
        raise ValueError(f"evidence {run['evidence_id']}: declared epoch differs from trace")
    latch = verify_latch(run["path"], epoch, run["expected_run_id"], anchor, anchor_row,
                         unmet, segment_end, groups, run["expect"])
    phases = load_clock(run["path"] / "clock.jsonl", epoch, latch["tick"])
    scene = load_scene(run["path"] / "scene-lifecycle.jsonl", epoch, run["expected_run_id"])

    faulted = [e for e in scene if e["phase"] == "faulted"]
    if not faulted or any(e["tick"] != latch["tick"] for e in faulted):
        raise ValueError("scene faulted events differ from the latch tick")
    if any(e["tick"] < latch["tick"] for e in faulted):
        raise ValueError("scene faulted events appeared before the latch tick")
    clock_events = [e for e in scene if e["kind"] == "faulted_clock"]
    if (len(clock_events) != 1 or clock_events[0]["phase"] != "faulted"
            or clock_events[0]["tick"] != latch["tick"]):
        raise ValueError("scene faulted_clock event must be unique at the latch tick")
    latched_events = [e for e in scene if e["kind"] == "fault_latched"]
    if (len(latched_events) != 1 or latched_events[0]["phase"] != "faulted"
            or latched_events[0]["tick"] != latch["tick"]):
        raise ValueError("scene fault_latched event differs from the latch")
    clock_index = scene.index(clock_events[0])
    latch_index = scene.index(latched_events[0])
    same_tick_faulted_permissions = [
        index for index, event in enumerate(scene)
        if event["kind"] == "permission" and event["phase"] == "faulted"
        and event["tick"] == latch["tick"]
    ]
    if any(index >= clock_index for index in same_tick_faulted_permissions):
        raise ValueError("same-tick faulted permission must precede faulted_clock")
    if latch_index != clock_index + 1:
        raise ValueError("scene faulted_clock and fault_latched must be adjacent")
    if latch_index != len(scene) - 1:
        raise ValueError("scene events must end at the unique fault_latched event")
    raw_clock_phase = phases[latch["tick"]]
    scene_faulted_clock_phase = clock_events[0]["phase"]

    steady_after_ns = anchor["wall_ns"] + STABILIZATION_NS
    if unmet.get("steady_after_ns") != steady_after_ns:
        raise ValueError("latch steady window boundary differs from the frozen 2 s contract")

    intervals = []
    for index in range(1, len(groups)):
        previous, current = groups[index - 1], groups[index]
        creep = current["actual_start_ns"] - previous["actual_start_ns"] - period_ns
        work_over = max(0, previous["work_ns"] - period_ns)
        release_excess = creep - work_over
        if creep < 0 or release_excess < 0:
            raise ValueError(f"interval ending at tick {current['start_tick']} is negative")
        intervals.append({"current_start_tick": current["start_tick"], "creep_ns": creep,
                          "previous_work_over_ns": work_over, "release_excess_ns": release_excess})
    creep_total = sum(i["creep_ns"] for i in intervals)
    work_over_total = sum(i["previous_work_over_ns"] for i in intervals)
    release_excess_total = sum(i["release_excess_ns"] for i in intervals)
    if creep_total != work_over_total + release_excess_total:
        raise ValueError("aggregate interval attribution does not close")

    def phase_of(group):
        raw_phase = phases.get(group["start_tick"])
        if raw_phase is None:
            raise ValueError(f"clock does not cover tick {group['start_tick']}")
        if raw_phase != "running":
            raise ValueError(f"timed group at tick {group['start_tick']} must land on raw clock running phase")
        window = "stabilization" if group["ideal_start_ns"] < steady_after_ns else "steady"
        return f"{raw_phase}/{window}"

    per_phase = {}
    for group in groups:
        bucket = per_phase.setdefault(phase_of(group), {"groups": 0, "work_ns": [],
            "start_lateness_ns": [], "end_lateness_ns": []})
        bucket["groups"] += 1
        bucket["work_ns"].append(group["work_ns"])
        bucket["start_lateness_ns"].append(group["start_lateness_ns"])
        bucket["end_lateness_ns"].append(group["end_lateness_ns"])
    by_tick = {g["start_tick"]: g for g in groups}
    interval_phases = {}
    for item in intervals:
        bucket = interval_phases.setdefault(phase_of(by_tick[item["current_start_tick"]]),
                                            {"creep_ns": [], "release_excess_ns": []})
        bucket["creep_ns"].append(item["creep_ns"])
        bucket["release_excess_ns"].append(item["release_excess_ns"])

    top = sorted(groups, key=lambda g: g["start_lateness_ns"], reverse=True)[:10]
    return {
        "evidence_id": run["evidence_id"],
        "run_id": run["expected_run_id"],
        "directory": run["directory"],
        "epoch": epoch,
        "anchor": anchor,
        "bootstrap_groups": {"count": len(bootstrap),
                             "work_ns": _summary([b["work_ns"] for b in bootstrap])},
        "timed_groups": len(groups),
        "latch": latch,
        "raw_clock_phase_at_latch": raw_clock_phase,
        "scene_faulted_clock_phase": scene_faulted_clock_phase,
        "max_group_start_lateness_ns": max(g["start_lateness_ns"] for g in groups),
        "max_group_end_lateness_ns": max(g["end_lateness_ns"] for g in groups),
        "steady_after_ns": steady_after_ns,
        "steady_window_reached": any(g["ideal_start_ns"] >= steady_after_ns for g in groups),
        "creep_total_ns": creep_total,
        "work_over_total_ns": work_over_total,
        "release_excess_total_ns": release_excess_total,
        "per_phase": {name: {"groups": b["groups"],
                             "work_ns": _summary(b["work_ns"]),
                             "start_lateness_ns": _summary(b["start_lateness_ns"]),
                             "end_lateness_ns": _summary(b["end_lateness_ns"]),
                             "creep_ns": _summary(interval_phases.get(name, {})
                                                  .get("creep_ns", [])),
                             "release_excess_ns": _summary(interval_phases.get(name, {})
                                                           .get("release_excess_ns", []))}
                      for name, b in sorted(per_phase.items())},
        "top_start_lateness_groups": [
            {"start_tick": g["start_tick"], "phase": phase_of(g),
             "start_lateness_ns": g["start_lateness_ns"], "work_ns": g["work_ns"]}
            for g in top],
        "input_sha256": run["input_sha256"],
    }


def analyze(evidence, period_ns=DEFAULT_PERIOD_NS):
    if isinstance(period_ns, bool) or not isinstance(period_ns, int) or period_ns <= 0 \
            or period_ns % TICK_NS:
        raise ValueError("period must be a positive whole millisecond count")
    facts, runs = verify_runs(evidence)
    analyzed = [analyze_run(run, period_ns) for run in runs]
    identities = {(run["evidence_id"], run["epoch"]) for run in analyzed}
    if len(identities) != len(analyzed):
        raise ValueError("evidence_id/epoch pairs must be distinct")
    return {
        "schema": SCHEMA,
        "status": "analyzed",
        "scope": ("observable interval arithmetic over sealed #62 inputs only; "
                  "no causal split of release excess and no performance claim"),
        "issue": 62,
        "period_ns": period_ns,
        "requested_rate": TICKS_PER_GROUP * TICK_NS / period_ns,
        "late_limit_ns": LATE_LIMIT_NS,
        "stabilization_ns": STABILIZATION_NS,
        "runs": analyzed,
        "analyzer_sha256": digest(Path(__file__)),
    }


def _write_output(path, raw):
    """Atomic create-only write; idempotent for byte-identical output."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("output path must not be a symlink")
    if path.exists():
        if path.read_bytes() == raw.encode("utf-8"):
            return
        raise ValueError("output exists with different bytes; refusing to overwrite")
    handle, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(raw.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # A hard link is the portable same-directory create-only publish
            # primitive: unlike os.replace it cannot overwrite a concurrent
            # destination.  The temporary name is removed after publication.
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink():
                raise ValueError("output path must not be a symlink")
            if path.read_bytes() == raw.encode("utf-8"):
                return
            raise ValueError("output exists with different bytes; refusing to overwrite")
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--period-ns", type=int, default=DEFAULT_PERIOD_NS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = analyze(args.evidence, period_ns=args.period_ns)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {"schema": SCHEMA, "status": "rejected", "error": repr(error),
                  "analyzer_sha256": digest(Path(__file__))}
    raw = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        if result["status"] != "analyzed":
            raise SystemExit(f"refusing to write a rejected report: {result['error']}")
        _write_output(args.output, raw)
    sys.stdout.buffer.write(raw.encode("utf-8"))
    return 0 if result["status"] == "analyzed" else 1


if __name__ == "__main__":
    sys.exit(main())
