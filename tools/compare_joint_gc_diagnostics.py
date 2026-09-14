"""Read-only comparator for two joint-flight GC diagnostic fields.

It answers only what the retained records can answer: were the two fields run
under the same identity/profile/timing-environment/async/baseline manifests, what
did Python cyclic GC and the supervisor wait/stages cost in each field, did each
field's recorded rate latch close against its own interval totals, and did the
declared manager GC candidate report satisfy its own contract.

The candidate contract is consumed from the runner's real product, never
invented here: ``result['manager_gc_candidate']`` written by
``tools/manager_gc_candidate.py`` (``ManagerGCFreeze.report()``), and, when
present, the matching side file ``manager-gc-candidate.json``. If both exist
they must be byte-for-byte equal as JSON; a mismatch is rejected. Nothing in
this tool creates that report, converts it, or asks the main session to
fabricate one.

It never fabricates zeros, never claims a performance pass, and never turns the
two-field correlation into a cause. Different boot or source, a missing complete
timed window, missing diagnostic marks, overflow/lost, or a timebase/identity
mismatch is rejected. Bool clocks, reversed or negative intervals, non-finite
CPU/cost values, and non-object result/source/metadata structures fail closed.
A named field cannot pair with an anonymous run, and empty source maps cannot
be a controlled pairing. Named fields ``oayggl_s`` / ``x39qjvkw`` / ``5lfbcy43`` /
``rfw9nmbb`` keep their published conditions and are never treated as a
controlled pair. Descriptive numbers, controlled pairing, and causal claims are
classified separately; causal is always false.

Usage:
    python3 -B tools/compare_joint_gc_diagnostics.py \
        --baseline DIR --candidate DIR --output NEW.json [--self-check]
"""

import argparse
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_joint_rate_intervals import PERIOD_NS, analyze as analyze_intervals


MANAGER_GC_MODULE = "tools/manager_gc_candidate.py"
MANAGER_GC_CLASSIFICATION = "candidate_not_performance_pass"
MANAGER_GC_SIDE_FILE = "manager-gc-candidate.json"
MANAGER_GC_SOURCE_KEY = "tools/manager_gc_candidate.py"
MANAGER_GC_ERROR_KEYS = ("manager_gc_candidate_error", "manager_gc_candidate_write_error")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_REQUIRED_EVENTS = ("armed", "prepared", "restored")
_SKIPPED_EVENTS = ("arm_skipped_disabled", "prepare_skipped_disabled",
                   "restore_skipped_disabled", "restore_noop_not_owner")
GC_KIND = "diagnostic_gc_timing"
STEP_KIND = "diagnostic_step_cpu_timing"
NATIVE_KIND = "diagnostic_native_input_timing"
_BOOT_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_INTEGRITY_KEYS = ("overflow", "lost", "lost_samples", "kernel_lost_count",
                   "reports_dropped", "dropped")
_INTEGRITY_KINDS = frozenset({
    "overflow", "lost", "record_lost", "perf_lost", "rate_overflow",
})
_BOOT_SIDECARS = (
    "terminal-cleanup.json", "inflight.json",
    "precheck-Ubuntu-22.04.json", "precheck-RflySim-20.04.json",
)
_SOURCE_COMPARE_KEYS = (
    "tools/run_joint_flight.py",
    "Simulator/wksim_runtime/joint_rate.py",
    "Simulator/wksim_core/joint.py",
    "Simulator/wksim_runtime/joint_rate_probe.py",
    MANAGER_GC_SOURCE_KEY,
)
KNOWN_FIELD_CONDITIONS = {
    "oayggl_s": {
        "family": "unprobed_manager99",
        "probe": False,
        "group_work_timing": False,
        "manager_target": 99,
    },
    "x39qjvkw": {
        "family": "probed_manager99",
        "probe": True,
        "group_work_timing": False,
        "manager_target": 99,
    },
    "5lfbcy43": {
        "family": "probed_manager50",
        "probe": True,
        "group_work_timing": False,
        "manager_target": 50,
    },
    "rfw9nmbb": {
        "family": "mixed_group_work_timing",
        "probe": False,
        "group_work_timing": True,
        "manager_target": None,
    },
}


def _positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _nonnegative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _clock_ns(value):
    return _nonnegative_int(value)


def _finite_number(value):
    if isinstance(value, bool) or isinstance(value, str):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _finite_nonnegative_number(value):
    return _finite_number(value) and value >= 0


def _require_object(value, name):
    if not isinstance(value, dict):
        raise TypeError(f"{name}_not_object:{type(value).__name__}")
    return value


def _optional_object(value, name):
    if value is None:
        return {}
    return _require_object(value, name)


def _verifiable_source_map(mapping):
    if not isinstance(mapping, dict) or not mapping:
        return None
    verified = {}
    for key, value in mapping.items():
        if isinstance(key, str) and key and isinstance(value, str) and value:
            verified[key] = value
    return verified if verified else None


def _boot_id_ok(value):
    return isinstance(value, str) and _BOOT_ID.fullmatch(value) is not None


def known_field_token(run_id):
    """Return the published short id embedded in a joint-public-flight run_id."""
    if not isinstance(run_id, str) or not run_id:
        return None
    for token in KNOWN_FIELD_CONDITIONS:
        if run_id == token or run_id.endswith("-" + token) or run_id.endswith("_" + token):
            return token
    return None


def _first_boot_id(*values):
    for value in values:
        if _boot_id_ok(value):
            return value
        if isinstance(value, dict):
            host = value.get("host")
            environment = value.get("environment")
            found = _first_boot_id(
                value.get("boot_id"), value.get("host_boot_id"),
                host.get("boot_id") if isinstance(host, dict) else None,
                environment.get("boot_id") if isinstance(environment, dict) else None)
            if found:
                return found
    return None


def _read_json_object(path):
    try:
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def discover_boot_id(directory, result_document, pre_run):
    """Read boot from the result, pre-run identity, or retained sidecars."""
    found = _first_boot_id(result_document, pre_run)
    if found:
        return found
    directory = Path(directory)
    for name in _BOOT_SIDECARS:
        path = directory / name
        if path.is_file():
            found = _first_boot_id(_read_json_object(path))
            if found:
                return found
    return None


def _integrity_value_problem(key, value):
    if value is None:
        return None
    if value is True or _positive_int(value):
        return f"{key}={value}"
    if _nonnegative_int(value):
        return None
    return f"{key}_invalid_type:{type(value).__name__}"


def _integrity_hits(row):
    problems = []
    if not isinstance(row, dict):
        return ["row_not_object"]
    kind = row.get("kind")
    if isinstance(kind, str) and (
            kind in _INTEGRITY_KINDS or kind.endswith("_lost") or kind.endswith("_overflow")):
        problems.append(f"kind:{kind}")
    for key in _INTEGRITY_KEYS:
        if key not in row:
            continue
        hit = _integrity_value_problem(key, row.get(key))
        if hit:
            problems.append(hit)
    return problems


def scan_integrity(path, document):
    """Reject overflow/lost/dropped marks; never treat them as a clean window."""
    problems = []
    if path is not None:
        for number, row in _lines(path):
            if not isinstance(row, dict):
                continue
            hits = _integrity_hits(row)
            if hits:
                problems.append(f"{Path(path).name}:{number}:" + ",".join(hits))
    if isinstance(document, dict):
        for key in _INTEGRITY_KEYS:
            if key not in document:
                continue
            hit = _integrity_value_problem(key, document.get(key))
            if hit:
                problems.append(f"result:{hit}")
        markers = document.get("markers")
        if markers is not None and not isinstance(markers, dict):
            problems.append("markers_not_object")
        elif isinstance(markers, dict):
            for key, value in markers.items():
                integrity_key = (
                    key in _INTEGRITY_KEYS
                    or (isinstance(key, str) and ("lost" in key or "overflow" in key)))
                if integrity_key:
                    hit = _integrity_value_problem(key, value)
                    if hit:
                        problems.append(f"markers:{hit}")
                elif value is True or _positive_int(value):
                    problems.append(f"markers:{key}={value}")
    return {"status": "rejected" if problems else "clean", "problems": problems}


def diagnostic_marks(document, rate_scan, wire_gc_samples):
    document = document if isinstance(document, dict) else {}
    probe_identity = document.get("rate_timing_probe")
    group_work = document.get("group_work_timing")
    owned = document.get("owned_scheduling")
    markers = document.get("markers")
    return {
        "gc_timing": bool(wire_gc_samples),
        "rate_timing_probe": bool((rate_scan or {}).get("probe_rows")) or isinstance(probe_identity, dict),
        "group_work_timing": group_work not in (None, {}, False),
        "owned_scheduling": owned not in (None, {}, False),
        "markers_empty": markers == {} or markers is None,
        "present": bool(wire_gc_samples) or bool((rate_scan or {}).get("probe_rows"))
                   or isinstance(probe_identity, dict)
                   or group_work not in (None, {}, False)
                   or owned not in (None, {}, False),
    }


def window_completeness(rate_scan, latch_status):
    bounds = (rate_scan or {}).get("timed_bounds") or {}
    reasons = []
    if bounds.get("status") != "observed":
        reasons.append("timed_bounds_unavailable:" + str(bounds.get("reason")))
    if bounds.get("clock") != "monotonic_ns":
        reasons.append("timed_bounds_clock_not_monotonic_ns")
    if not _clock_ns(bounds.get("timed_start_ns")) or not _clock_ns(bounds.get("timed_end_ns")):
        reasons.append("timed_bounds_not_nonnegative_int")
    elif bounds.get("timed_end_ns") < bounds.get("timed_start_ns"):
        reasons.append("timed_window_reversed")
    if latch_status != "reconciled":
        reasons.append("latch_not_reconciled:" + str(latch_status))
    return {
        "status": "complete" if not reasons else "incomplete",
        "reasons": reasons,
        "timed_bounds": bounds.get("status"),
        "latch_status": latch_status,
    }


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _lines(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield number, json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"line {number}: malformed JSON: {error}") from error


def resolve_inputs(directory, overrides):
    """Locate result/rate/joint-wire and the optional side report, accepting .gz."""
    directory = Path(directory)
    found = {}
    for key, choices in (
        ("result", ("result.json",)),
        ("rate", ("rate.jsonl", "rate.jsonl.gz")),
        ("wire", ("joint-wire.jsonl", "joint-wire.jsonl.gz")),
        ("pre_run_identity", ("pre-run-identity.json",)),
        ("manager_gc_report", (MANAGER_GC_SIDE_FILE,)),
    ):
        override = overrides.get(key)
        if override:
            path = Path(override)
            found[key] = path if path.is_file() else None
            continue
        found[key] = next((directory / name for name in choices if (directory / name).is_file()), None)
    return found


def read_result(path):
    """Return (summary, full document) for one retained result.json."""
    data = _require_object(json.loads(Path(path).read_text(encoding="utf-8")), "result")
    if data.get("mixed_admission") is not None:
        admission = _require_object(data.get("mixed_admission"), "mixed_admission")
    elif data.get("pv_admission") is not None:
        admission = _require_object(data.get("pv_admission"), "pv_admission")
    else:
        admission = {}
    identities = _optional_object(admission.get("identities"), "identities")
    baseline = _optional_object(identities.get("baseline"), "baseline")
    manifests = _optional_object(data.get("manifest_sha256"), "manifest_sha256")
    source = _optional_object(data.get("source_sha256"), "source_sha256")
    markers = _optional_object(data.get("markers"), "markers")
    baseline_manifests = _optional_object(baseline.get("manifests"), "baseline_manifests")
    summary = {
        "run_id": data.get("run_id"),
        "scene_epoch": data.get("scene_epoch"),
        "task_profile": data.get("task_profile"),
        "status": data.get("status"),
        "error": data.get("error"),
        "wall_seconds": data.get("wall_seconds"),
        "flight_completed": data.get("flight_completed"),
        "source_unchanged": data.get("source_unchanged"),
        "async_model_evidence_requested": data.get("async_model_evidence_requested"),
        "rate_timing_probe_identity": data.get("rate_timing_probe"),
        "group_work_timing_present": data.get("group_work_timing") not in (None, {}, False),
        "owned_scheduling_present": data.get("owned_scheduling") not in (None, {}, False),
        "markers": markers,
        "manager_gc_candidate_present": isinstance(data.get("manager_gc_candidate"), dict),
        "manager_gc_candidate_errors": {key: data.get(key) for key in MANAGER_GC_ERROR_KEYS
                                        if data.get(key)},
        "manifest_sha256": {
            "ap": manifests.get("ap"),
            "control": manifests.get("control"),
            "message": manifests.get("message"),
            "px4": manifests.get("px4"),
        },
        "admission_px4_manifest": baseline_manifests.get("px4"),
        "source_sha256": {key: value for key, value in source.items()
                          if isinstance(key, str) and key and isinstance(value, str) and value},
        "source_sha256_count": len(source),
        "source_unchanged": data.get("source_unchanged"),
        "host_boot_id": data.get("host_boot_id") or data.get("boot_id"),
    }
    return summary, data


def manager_gc_contract(result_document, side_report_path, role):
    """Validate the real ManagerGCFreeze report; never synthesise one."""
    from_result = result_document.get("manager_gc_candidate")
    from_result = from_result if isinstance(from_result, dict) else None
    from_side = None
    if side_report_path is not None:
        try:
            loaded = json.loads(Path(side_report_path).read_text(encoding="utf-8"))
            from_side = loaded if isinstance(loaded, dict) else None
        except (OSError, ValueError) as error:
            return {"status": "rejected", "required": role == "candidate", "sources": ["side_file"],
                    "problems": [f"side_report_unreadable:{type(error).__name__}"]}
    sources = []
    if from_result is not None:
        sources.append("result")
    if from_side is not None:
        sources.append("side_file")
    errors = {key: result_document.get(key) for key in MANAGER_GC_ERROR_KEYS
              if result_document.get(key)}
    base = {"required": role == "candidate", "sources": sources,
            "side_file": None if side_report_path is None else str(side_report_path)}
    if not sources:
        return {**base, "status": "unavailable", "reason": "no_manager_gc_candidate_report"}
    if errors:
        return {**base, "status": "rejected", "problems": sorted(errors)}
    if len(sources) == 2 and from_result != from_side:
        return {**base, "status": "rejected",
                "problems": ["report_mismatch_between_result_and_side_file"]}
    report = from_result if from_result is not None else from_side
    if report.get("enabled") is not True:
        return {**base, "status": "unavailable", "reason": "manager_gc_candidate_not_enabled",
                "report": report}
    problems = []
    unavailable = []
    if report.get("module") != MANAGER_GC_MODULE:
        problems.append("module_mismatch")
    if report.get("classification") != MANAGER_GC_CLASSIFICATION:
        problems.append("classification_mismatch")
    if report.get("candidate") is not True:
        problems.append("candidate_flag_missing")
    if report.get("performance_pass") is not False:
        problems.append("performance_pass_claimed")
    for key in ("armed", "prepared", "restored"):
        if report.get(key) is not True:
            problems.append(f"{key}_not_true")
    if report.get("froze_own_graph") is not False:
        problems.append("frozen_graph_not_released")
    original = report.get("original") or {}
    if original.get("gc_enabled") is not True:
        problems.append("original_collector_not_enabled")
    if original.get("freeze_count") != 0:
        problems.append("original_freeze_count_not_zero")
    if report.get("freeze_count_before") != 0:
        problems.append("freeze_count_before_not_zero")
    before = report.get("before") or {}
    after = report.get("after") or {}
    if before.get("freeze_count") != 0:
        problems.append("before_freeze_count_not_zero")
    # freeze_count is a count of frozen objects, not of freeze() calls: one
    # freeze on a real manager graph moves thousands of objects, and releasing
    # ordinary references can shrink it without a second freeze. Require a
    # positive integer and internal consistency, never a literal 1.
    after_count = after.get("freeze_count")
    if not _positive_int(after_count):
        problems.append("after_freeze_count_not_positive_integer")
    if not _positive_int(report.get("freeze_count_after")):
        problems.append("freeze_count_after_not_positive_integer")
    elif _positive_int(after_count) and report.get("freeze_count_after") != after_count:
        problems.append("freeze_count_after_differs_from_after_snapshot")
    prepare_check = report.get("prepare_check") or {}
    if prepare_check.get("gc_enabled") is not True:
        problems.append("prepare_check_collector_not_enabled")
    if prepare_check.get("freeze_count") != 0:
        problems.append("prepare_check_freeze_count_not_zero")
    if prepare_check.get("thresholds") != original.get("thresholds"):
        problems.append("thresholds_changed")
    restore = report.get("restore") or {}
    if not _nonnegative_int(restore.get("freeze_count_before_unfreeze")):
        problems.append("restore_before_unfreeze_not_nonnegative_integer")
    elif _positive_int(after_count) and restore["freeze_count_before_unfreeze"] > after_count:
        problems.append("restore_before_unfreeze_exceeds_frozen_count")
    if restore.get("freeze_count_after_unfreeze") != 0:
        problems.append("restore_after_unfreeze_not_zero")
    if restore.get("expected_original_freeze_count") != 0:
        problems.append("restore_expected_original_not_zero")
    if restore.get("restored_to_original") is not True:
        problems.append("restore_not_confirmed")
    activation = report.get("activation") or {}
    if not _clock_ns(activation.get("moment_monotonic_ns")):
        problems.append("activation_moment_missing")
    if activation.get("clock_tick") != 0:
        problems.append("prepared_after_tick_zero")
    events = [event.get("event") for event in (report.get("events") or [])
              if isinstance(event, dict)]
    for required in _REQUIRED_EVENTS:
        if required not in events:
            problems.append(f"missing_event_{required}")
    if all(required in events for required in _REQUIRED_EVENTS):
        if not (events.index("armed") < events.index("prepared") < events.index("restored")):
            problems.append("event_order_not_armed_prepared_restored")
    if set(_SKIPPED_EVENTS) & set(events):
        problems.append("skipped_or_noop_lifecycle_path")
    source = report.get("source_sha256")
    declared = (result_document.get("source_sha256") or {}).get(MANAGER_GC_SOURCE_KEY)
    if not isinstance(source, str) or _HEX64.fullmatch(source) is None:
        problems.append("source_sha256_missing_or_malformed")
    elif declared is None:
        # A report string cannot authenticate itself: without the runner's
        # retained source map the identity is unverifiable, not validated.
        unavailable.append("source_sha256_not_in_result_source_map")
    elif declared != source:
        problems.append("source_sha256_differs_from_result_source_map")
    if problems:
        status = "rejected"
    elif unavailable:
        status = "unavailable"
    else:
        status = "validated"
    return {**base, "status": status, "problems": problems,
            "unavailable_reasons": unavailable,
            "validated_fields": {
                "armed": report.get("armed"), "prepared": report.get("prepared"),
                "restored": report.get("restored"), "froze_own_graph": report.get("froze_own_graph"),
                "original": original, "prepare_check": prepare_check,
                "activation": activation, "restore": restore,
                "freeze_count_before": report.get("freeze_count_before"),
                "freeze_count_after": report.get("freeze_count_after"),
                "after_freeze_count": after_count,
                "source_sha256": source, "result_source_sha256": declared,
                "events": events,
            },
            "report": report}


def scan_rate(path):
    """Only the quantities the interval analyzer does not report.

    Also returns the timed-segment bounds on the monotonic-nanosecond axis, the
    same axis the diagnostic GC/wait rows use: the rate anchor's wall_ns opens
    the timed window and the retained termination record (latch issued time, or
    the last group's end) closes it.
    """
    epochs = set()
    max_work = None
    max_work_over = None
    max_entry_lateness = None
    probe_rows = 0
    outcomes = {}
    pending = None
    anchor_wall_ns = None
    anchor_tick = None
    anchor_count = 0
    last_group_end_ns = None
    latch = None
    integrity_problems = []
    clock_problems = []
    for number, row in _lines(path):
        if not isinstance(row, dict):
            raise TypeError(f"rate_row_not_object:{number}:{type(row).__name__}")
        integrity_problems.extend(
            f"rate:{number}:{item}" for item in _integrity_hits(row))
        kind = row.get("kind")
        if kind in ("rate_group_start", "rate_group_end"):
            epochs.add((row.get("epoch"), row.get("segment_id"), row.get("request_id"),
                        row.get("requested_rate"), row.get("transition")))
        if kind == "rate_anchor":
            anchor_count += 1
            raw_anchor = row.get("anchor")
            if raw_anchor is not None and not isinstance(raw_anchor, dict):
                clock_problems.append(f"rate:{number}:anchor_not_object")
                continue
            anchor = raw_anchor or {}
            wall = anchor.get("wall_ns")
            if not _clock_ns(wall):
                clock_problems.append(f"rate:{number}:anchor_wall_ns_invalid")
            elif anchor_wall_ns is None:
                anchor_wall_ns = wall
                anchor_tick = anchor.get("tick")
        elif kind == "rate_group_start":
            pending = row
        elif kind == "rate_group_end" and pending is not None:
            start = pending.get("actual_start_ns")
            end = row.get("actual_end_ns")
            if not _clock_ns(start) or not _clock_ns(end):
                clock_problems.append(f"rate:{number}:group_clock_invalid")
                pending = None
                continue
            if end < start:
                clock_problems.append(f"rate:{number}:group_interval_reversed")
                pending = None
                continue
            work = end - start
            over = work - PERIOD_NS
            if max_work is None or work > max_work[0]:
                max_work = (work, pending["start_tick"])
            if over > 0 and (max_work_over is None or over > max_work_over[0]):
                max_work_over = (over, pending["start_tick"], work)
            last_group_end_ns = end
            pending = None
        elif kind == "rate_unmet":
            latch = row
        elif kind == "rate_timing_probe":
            probe_rows += 1
            outcomes[row.get("outcome")] = outcomes.get(row.get("outcome"), 0) + 1
            entry_ns = row.get("entry_ns")
            earliest = row.get("earliest_start_ns")
            if not _clock_ns(entry_ns) or not _clock_ns(earliest):
                clock_problems.append(f"rate:{number}:probe_clock_invalid")
                continue
            lateness = max(0, entry_ns - earliest)
            if max_entry_lateness is None or lateness > max_entry_lateness[0]:
                max_entry_lateness = (lateness, row.get("start_tick"))
    timed_end_ns = None
    termination = None
    if latch is not None:
        issued = latch.get("issued_monotonic_ns")
        if _clock_ns(issued):
            timed_end_ns = issued
            termination = "rate_unmet_record_issued_monotonic_ns"
        else:
            clock_problems.append("rate:latch_issued_monotonic_ns_invalid")
    elif last_group_end_ns is not None:
        timed_end_ns = last_group_end_ns
        termination = "last_group_actual_end_ns"
    bounds_status = "observed"
    bounds_reason = None
    if clock_problems:
        bounds_status = "unavailable"
        bounds_reason = "timestamp_type_invalid"
    elif anchor_count != 1:
        bounds_status = "unavailable"
        bounds_reason = ("no_rate_anchor" if anchor_count == 0
                         else "multiple_rate_anchors_not_partitioned")
    elif not _clock_ns(anchor_wall_ns) or not _clock_ns(timed_end_ns):
        bounds_status = "unavailable"
        bounds_reason = "anchor_or_termination_timestamp_missing"
    elif timed_end_ns < anchor_wall_ns:
        bounds_status = "unavailable"
        bounds_reason = "timed_window_reversed"
    return {
        "identity_tuples_in_groups": len(epochs),
        "identity_consistent": len(epochs) == 1,
        "max_group_work_ns": None if max_work is None else max_work[0],
        "max_group_work_tick": None if max_work is None else max_work[1],
        "max_work_over_ns": None if max_work_over is None else max_work_over[0],
        "max_work_over_tick": None if max_work_over is None else max_work_over[1],
        "max_work_over_group_work_ns": None if max_work_over is None else max_work_over[2],
        "probe_rows": probe_rows,
        "probe_outcomes": outcomes,
        "max_entry_lateness_ns": None if max_entry_lateness is None else max_entry_lateness[0],
        "max_entry_lateness_tick": None if max_entry_lateness is None else max_entry_lateness[1],
        "timed_bounds": {
            "clock": "monotonic_ns",
            "status": bounds_status,
            "reason": bounds_reason,
            "anchor_count": anchor_count,
            "anchor_tick": anchor_tick,
            "timed_start_ns": anchor_wall_ns,
            "timed_end_ns": timed_end_ns,
            "termination": termination,
        },
        "integrity_problems": integrity_problems,
        "clock_problems": clock_problems,
    }


WINDOW_NAMES = ("preparation", "timed", "post", "unclassified_boundary_straddling",
                "unclassified_missing_clock", "unclassified_invalid_clock",
                "unclassified_reversed_interval", "unclassified_no_bounds")
_TIMEBASE_WINDOWS = (
    "unclassified_missing_clock", "unclassified_invalid_clock",
    "unclassified_reversed_interval", "unclassified_no_bounds",
)


def _classify_window(start_ns, end_ns, bounds):
    if start_ns is None and end_ns is None:
        return "unclassified_missing_clock"
    if not _clock_ns(start_ns) or not _clock_ns(end_ns):
        return "unclassified_invalid_clock"
    if end_ns < start_ns:
        return "unclassified_reversed_interval"
    if bounds.get("status") != "observed":
        return "unclassified_no_bounds"
    timed_start = bounds.get("timed_start_ns")
    timed_end = bounds.get("timed_end_ns")
    if not _clock_ns(timed_start) or not _clock_ns(timed_end) or timed_end < timed_start:
        return "unclassified_no_bounds"
    if end_ns <= timed_start:
        return "preparation"
    if start_ns >= timed_end:
        return "post"
    if start_ns >= timed_start and end_ns <= timed_end:
        return "timed"
    return "unclassified_boundary_straddling"


def _gc_ledger(rows):
    usable = [row for row in rows if _finite_nonnegative_number(row.get("thread_cpu_ns"))]
    gen2 = [row for row in usable if row.get("generation") == 2]
    largest = max(usable, key=lambda row: row["thread_cpu_ns"], default=None)
    return {
        "samples": len(usable),
        "thread_cpu_sum_ns": sum(row["thread_cpu_ns"] for row in usable) if usable else None,
        "thread_cpu_max_ns": largest["thread_cpu_ns"] if largest else None,
        "thread_cpu_max_tick": largest["tick"] if largest else None,
        "generations": sorted({row.get("generation") for row in usable}),
        "gen2_samples": len(gen2),
        "gen2_thread_cpu_sum_ns": sum(row["thread_cpu_ns"] for row in gen2) if gen2 else None,
        "gen2_thread_cpu_max_ns": max((row["thread_cpu_ns"] for row in gen2), default=None),
        "gen2_thread_cpu_max_tick": max(gen2, key=lambda row: row["thread_cpu_ns"])["tick"]
        if gen2 else None,
    }


def scan_wire(path, timed_bounds):
    """Full GC/wait ledger plus a preparation/timed/post partition.

    A tick-0 preparation collect (the C1 shape) must not be reported as flight
    GC cost, and an event straddling a boundary must be reported as
    unclassifiable rather than dropped or silently assigned.
    """
    gc_rows = []
    native_rows = []
    step_rows = []
    integrity_problems = []
    clock_problems = []
    cost_problems = []
    for number, row in _lines(path):
        if not isinstance(row, dict):
            raise TypeError(f"wire_row_not_object:{number}:{type(row).__name__}")
        integrity_problems.extend(
            f"wire:{number}:{item}" for item in _integrity_hits(row))
        kind = row.get("kind")
        if kind == GC_KIND:
            gc_rows.append(row)
            start, end = row.get("wall_start_ns"), row.get("wall_end_ns")
            if start is None and end is None:
                clock_problems.append(f"wire:{number}:gc_clock_missing")
            elif not _clock_ns(start) or not _clock_ns(end):
                clock_problems.append(f"wire:{number}:gc_clock_invalid")
            elif end < start:
                clock_problems.append(f"wire:{number}:gc_interval_reversed")
            cpu = row.get("thread_cpu_ns")
            if cpu is not None and not _finite_nonnegative_number(cpu):
                cost_problems.append(f"wire:{number}:gc_thread_cpu_not_finite")
        elif kind == NATIVE_KIND:
            native_rows.append(row)
        elif kind == STEP_KIND:
            step_rows.append(row)
    windows = {name: [] for name in WINDOW_NAMES}
    for row in gc_rows:
        windows[_classify_window(row.get("wall_start_ns"), row.get("wall_end_ns"),
                                 timed_bounds)].append(row)
    stages = ("health_and_models", "encode_send", "native_inputs")
    stage_stats = {}
    for name in stages:
        walls = []
        cpus = []
        for row in step_rows:
            stages_map = row.get("stages")
            if not isinstance(stages_map, dict) or name not in stages_map:
                continue
            stage = stages_map[name]
            if not isinstance(stage, dict):
                cost_problems.append(f"wire:stage_{name}_not_object")
                continue
            wall = stage.get("wall_ns")
            cpu = stage.get("thread_cpu_ns")
            if wall is not None and not _finite_nonnegative_number(wall):
                cost_problems.append(f"wire:stage_{name}_wall_not_finite")
            elif _finite_nonnegative_number(wall):
                walls.append(wall)
            if cpu is not None and not _finite_nonnegative_number(cpu):
                cost_problems.append(f"wire:stage_{name}_cpu_not_finite")
            elif _finite_nonnegative_number(cpu):
                cpus.append(cpu)
        stage_stats[name] = {
            "samples": len(walls),
            "wall_sum_ns": sum(walls) if walls else None,
            "wall_max_ns": max(walls) if walls else None,
            "cpu_sum_ns": sum(cpus) if cpus else None,
            "cpu_max_ns": max(cpus) if cpus else None,
        }
    totals = []
    for row in step_rows:
        stages_map = row.get("stages")
        if not isinstance(stages_map, dict):
            continue
        values = []
        usable = True
        for stage in stages_map.values():
            if not isinstance(stage, dict) or not _finite_nonnegative_number(stage.get("wall_ns")):
                usable = False
                break
            values.append(stage["wall_ns"])
        if usable and values:
            totals.append(sum(values))
    return {
        "gc_rows": gc_rows,
        "native_rows": native_rows,
        "step_rows": step_rows,
        "gc": _gc_ledger(gc_rows),
        "gc_windows": {
            "bounds": timed_bounds,
            "preparation": _gc_ledger(windows["preparation"]),
            "timed": _gc_ledger(windows["timed"]),
            "post": _gc_ledger(windows["post"]),
            "unclassified_boundary_straddling": _gc_ledger(windows["unclassified_boundary_straddling"]),
            "unclassified_missing_clock": _gc_ledger(windows["unclassified_missing_clock"]),
            "unclassified_invalid_clock": _gc_ledger(windows["unclassified_invalid_clock"]),
            "unclassified_reversed_interval": _gc_ledger(windows["unclassified_reversed_interval"]),
            "unclassified_no_bounds": _gc_ledger(windows["unclassified_no_bounds"]),
            "all": _gc_ledger(gc_rows),
        },
        "stage_stats": stage_stats,
        "step_samples": len(step_rows),
        "step_total_wall_max_ns": max(totals) if totals else None,
        "integrity_problems": integrity_problems,
        "clock_problems": clock_problems,
        "cost_problems": cost_problems,
    }


def nesting_evidence(wire):
    """Report interval containment for the largest in-timed-window GC.

    A preparation collect (the C1 shape) must not be offered as flight nesting
    evidence, so the timed window is preferred; when it is unavailable or empty
    the largest overall GC is used and explicitly labelled.
    """
    timed = wire["gc_windows"]["timed"]
    if timed["samples"]:
        tick = timed["thread_cpu_max_tick"]
        target = timed["thread_cpu_max_ns"]
        window = "timed"
    else:
        gc = wire["gc"]
        tick = gc["thread_cpu_max_tick"]
        target = gc["thread_cpu_max_ns"]
        window = "all"
    if tick is None:
        return {"status": "unavailable", "reason": "no_gc_rows"}
    gc_row = next((row for row in wire["gc_rows"]
                   if row.get("tick") == tick and row.get("thread_cpu_ns") == target), None)
    if gc_row is None or not _clock_ns(gc_row.get("wall_start_ns")) \
            or not _clock_ns(gc_row.get("wall_end_ns")):
        return {"status": "unavailable", "reason": "gc_interval_missing_clock",
                "window": window, "tick": tick}
    native_row = next((row for row in wire["native_rows"] if row.get("tick") == tick), None)
    step_row = next((row for row in wire["step_rows"] if row.get("tick") == tick), None)
    waits = [] if native_row is None else [
        wait for wait in native_row.get("waits", [])
        if isinstance(wait, dict) and _clock_ns(wait.get("wall_start_ns"))
        and _clock_ns(wait.get("wall_end_ns"))]
    containing = [
        {"stack": wait.get("stack"), "wall_start_ns": wait.get("wall_start_ns"),
         "wall_end_ns": wait.get("wall_end_ns"), "wall_ns": wait.get("wall_ns"),
         "thread_cpu_ns": wait.get("thread_cpu_ns")}
        for wait in waits
        if (wait["wall_start_ns"] <= gc_row["wall_start_ns"]
            and gc_row["wall_end_ns"] <= wait["wall_end_ns"])
    ]
    native_start = min((wait["wall_start_ns"] for wait in waits), default=None)
    native_end = max((wait["wall_end_ns"] for wait in waits), default=None)
    step_start = None if step_row is None else step_row.get("wall_start_ns")
    step_end = None if step_row is None else step_row.get("wall_end_ns")
    step_contains_native = bool(
        step_start is not None and step_end is not None
        and native_start is not None and native_end is not None
        and step_start <= native_start and native_end <= step_end)
    on_cpu = bool(containing) and all(
        _finite_nonnegative_number(wait.get("thread_cpu_ns"))
        and _finite_nonnegative_number(wait.get("wall_ns"))
        and wait["thread_cpu_ns"] >= wait["wall_ns"] * 0.9 for wait in containing)
    return {
        "status": "observed",
        "window": window,
        "tick": tick,
        "gc_interval": {"wall_start_ns": gc_row["wall_start_ns"], "wall_end_ns": gc_row["wall_end_ns"],
                        "thread_cpu_ns": gc_row["thread_cpu_ns"], "generation": gc_row.get("generation")},
        "gc_nested_in_native_wait": bool(containing),
        "containing_waits": containing,
        "native_wait_wall_ns": None if native_row is None else native_row["native_wait_wall_ns"],
        "native_interval": {"wall_start_ns": native_start, "wall_end_ns": native_end},
        "native_wait_inside_step": step_contains_native,
        "containing_wait_on_cpu": on_cpu,
        "limitation": "interval containment only; it does not establish why the collection ran or who caused the wait",
    }


def plain_rate_path(path):
    """The interval analyzer reads plain text; decompress a .gz copy for it."""
    if not str(path).endswith(".gz"):
        return path, None
    handle = tempfile.NamedTemporaryFile("wb", suffix=".jsonl", delete=False)
    with gzip.open(path, "rb") as source:
        shutil.copyfileobj(source, handle)
    handle.close()
    return Path(handle.name), handle.name


def analyse_field(directory, overrides, role):
    inputs = resolve_inputs(directory, overrides)
    missing = [key for key in ("result", "rate", "wire") if inputs[key] is None]
    record = {
        "role": role,
        "directory": str(directory),
        "inputs": {key: (None if inputs[key] is None else str(inputs[key]))
                   for key in ("result", "rate", "wire", "pre_run_identity", "manager_gc_report")},
        "input_sha256": {},
    }
    if inputs["manager_gc_report"] is not None:
        record["input_sha256"]["manager_gc_report"] = _sha256(inputs["manager_gc_report"])
    if missing:
        record["analysis_status"] = "unavailable"
        record["reasons"] = ["missing_input:" + ",".join(missing)]
        return record, inputs
    for key in ("result", "rate", "wire"):
        record["input_sha256"][key] = _sha256(inputs[key])
    try:
        record["identity"], document = read_result(inputs["result"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        record["analysis_status"] = "unavailable"
        record["reasons"] = [f"result_unreadable:{type(error).__name__}: {error}"]
        return record, inputs
    pre = None
    if inputs["pre_run_identity"] is not None:
        try:
            pre = json.loads(Path(inputs["pre_run_identity"]).read_text(encoding="utf-8"))
            pre = _require_object(pre, "pre_run_identity")
            record["declared_environment"] = pre.get("environment")
            record["declared_async_model_evidence"] = pre.get("async_model_evidence")
            record["declared_probe_environment"] = pre.get("probe_environment")
            record["declared_manager_target"] = pre.get("manager_target_fifo_priority")
        except (OSError, ValueError, TypeError, AttributeError) as error:
            pre = None
            record["declared_environment"] = None
            record.setdefault("reasons", []).append(
                f"pre_run_identity_unreadable:{type(error).__name__}: {error}")
    try:
        record["rate_scan"] = scan_rate(inputs["rate"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        record["analysis_status"] = "rejected"
        record["reasons"] = [f"rate_trace_invalid:{type(error).__name__}: {error}"]
        return record, inputs
    if not record["rate_scan"]["identity_consistent"]:
        record["analysis_status"] = "rejected"
        record["reasons"] = ["mixed_identity_inside_one_field"]
        return record, inputs
    plain, temporary = plain_rate_path(inputs["rate"])
    try:
        record["latch"] = analyze_intervals(plain)
        record["latch_status"] = record["latch"]["latch_reconciliation"]["status"]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        record["analysis_status"] = "rejected"
        record["reasons"] = [f"interval_analyzer_rejected:{type(error).__name__}: {error}"]
        return record, inputs
    finally:
        if temporary is not None:
            os.unlink(temporary)
    try:
        wire = scan_wire(inputs["wire"], record["rate_scan"]["timed_bounds"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        record["analysis_status"] = "unavailable"
        record["reasons"] = [f"wire_unreadable:{type(error).__name__}: {error}"]
        return record, inputs
    record["gc"] = wire["gc"]
    record["gc_windows"] = wire["gc_windows"]
    record["stage_stats"] = wire["stage_stats"]
    record["step_samples"] = wire["step_samples"]
    record["step_total_wall_max_ns"] = wire["step_total_wall_max_ns"]
    record["nesting"] = nesting_evidence(wire)
    record["manager_gc_candidate_contract"] = manager_gc_contract(
        document, inputs["manager_gc_report"], role)
    record["boot_id"] = discover_boot_id(directory, document, pre)
    record["source_sha256"] = (record.get("identity") or {}).get("source_sha256") or {}
    record["source_unchanged"] = (record.get("identity") or {}).get("source_unchanged")
    record["known_field"] = known_field_token((record.get("identity") or {}).get("run_id"))
    record["diagnostic_marks"] = diagnostic_marks(
        document, record["rate_scan"], len(wire["gc_rows"]))
    record["window"] = window_completeness(record["rate_scan"], record["latch_status"])
    integrity_problems = list(record["rate_scan"].get("integrity_problems") or [])
    integrity_problems.extend(wire.get("integrity_problems") or [])
    integrity_problems.extend(scan_integrity(None, document)["problems"])
    record["integrity"] = {
        "status": "rejected" if integrity_problems else "clean",
        "problems": integrity_problems,
    }
    reasons = []
    if len(wire["gc_rows"]) == 0:
        reasons.append("missing_diagnostic_marks:gc_timing")
    if record["rate_scan"]["timed_bounds"]["status"] != "observed":
        reasons.append("timed_windows_unavailable:"
                       + str(record["rate_scan"]["timed_bounds"]["reason"]))
    if record["window"]["status"] != "complete":
        reasons.append("incomplete_window:" + ",".join(record["window"]["reasons"]))
    if record["integrity"]["status"] == "rejected":
        reasons.append("overflow_or_lost:" + ",".join(integrity_problems[:8]))
    if record["rate_scan"].get("clock_problems"):
        reasons.append("invalid_clock:" + ",".join(record["rate_scan"]["clock_problems"][:8]))
    if wire.get("clock_problems"):
        reasons.append("invalid_clock:" + ",".join(wire["clock_problems"][:8]))
    if wire.get("cost_problems"):
        reasons.append("invalid_cost:" + ",".join(wire["cost_problems"][:8]))
    if record["manager_gc_candidate_contract"]["status"] == "rejected":
        reasons.append("manager_gc_candidate_contract_rejected")
    if any((record["gc_windows"].get(name) or {}).get("samples") for name in _TIMEBASE_WINDOWS):
        reasons.append("timebase_inconsistent")
    record["reasons"] = reasons
    record["analysis_status"] = "analyzed"
    return record, inputs


def _px4_manifest(record):
    identity = record.get("identity") or {}
    manifests = identity.get("manifest_sha256") or {}
    if manifests.get("px4"):
        return manifests["px4"]
    admission = identity.get("admission_px4_manifest")
    if isinstance(admission, dict):
        return admission.get("sha256")
    return None


def compare_identity(baseline, candidate):
    def manifests(record):
        identity = record.get("identity") or {}
        return identity.get("manifest_sha256") or {}

    base_manifest = manifests(baseline)
    cand_manifest = manifests(candidate)
    differences = []
    fields = {}
    for key in ("ap", "control", "message"):
        left, right = base_manifest.get(key), cand_manifest.get(key)
        fields[key + "_match"] = bool(left is not None and left == right)
        if not fields[key + "_match"]:
            differences.append(f"{key}:{left}!={right}")
    px4_left, px4_right = _px4_manifest(baseline), _px4_manifest(candidate)
    fields["px4_match"] = None if (px4_left is None or px4_right is None) else bool(px4_left == px4_right)
    if fields["px4_match"] is False:
        differences.append(f"px4:{px4_left}!={px4_right}")
    profile_left = (baseline.get("identity") or {}).get("task_profile")
    profile_right = (candidate.get("identity") or {}).get("task_profile")
    fields["profile_match"] = bool(profile_left is not None and profile_left == profile_right)
    if not fields["profile_match"]:
        differences.append(f"profile:{profile_left}!={profile_right}")
    async_left = (baseline.get("identity") or {}).get("async_model_evidence_requested")
    async_right = (candidate.get("identity") or {}).get("async_model_evidence_requested")
    fields["async_match"] = None if (async_left is None or async_right is None) else bool(async_left == async_right)
    if fields["async_match"] is False:
        differences.append(f"async:{async_left}!={async_right}")
    probe_left = (baseline.get("rate_scan") or {}).get("probe_rows", 0) > 0
    probe_right = (candidate.get("rate_scan") or {}).get("probe_rows", 0) > 0
    cpu_left = any(stage.get("samples") for stage in (baseline.get("stage_stats") or {}).values())
    cpu_right = any(stage.get("samples") for stage in (candidate.get("stage_stats") or {}).values())
    fields["rate_timing_probe_match"] = probe_left == probe_right
    fields["cpu_timing_match"] = cpu_left == cpu_right
    if not fields["rate_timing_probe_match"]:
        differences.append(f"rate_timing_probe:{probe_left}!={probe_right}")
    if not fields["cpu_timing_match"]:
        differences.append(f"cpu_timing:{cpu_left}!={cpu_right}")
    marks_left = baseline.get("diagnostic_marks") or {}
    marks_right = candidate.get("diagnostic_marks") or {}
    fields["group_work_timing_match"] = (
        bool(marks_left.get("group_work_timing")) == bool(marks_right.get("group_work_timing")))
    fields["owned_scheduling_match"] = (
        bool(marks_left.get("owned_scheduling")) == bool(marks_right.get("owned_scheduling")))
    if not fields["group_work_timing_match"]:
        differences.append("group_work_timing:True!=False"
                           if marks_left.get("group_work_timing")
                           else "group_work_timing:False!=True")
    if not fields["owned_scheduling_match"]:
        differences.append("owned_scheduling_mismatch")
    boot_left, boot_right = baseline.get("boot_id"), candidate.get("boot_id")
    fields["boot_match"] = bool(_boot_id_ok(boot_left) and boot_left == boot_right)
    if not _boot_id_ok(boot_left) or not _boot_id_ok(boot_right):
        differences.append(f"boot:{boot_left}!={boot_right}")
    elif boot_left != boot_right:
        differences.append(f"boot:{boot_left}!={boot_right}")
    source_left = _verifiable_source_map(baseline.get("source_sha256"))
    source_right = _verifiable_source_map(candidate.get("source_sha256"))
    source_diffs = []
    if source_left is None or source_right is None:
        fields["source_match"] = False
        differences.append("source:unverifiable_or_empty")
    else:
        source_keys = set(_SOURCE_COMPARE_KEYS) | set(source_left) | set(source_right)
        for key in sorted(source_keys):
            left, right = source_left.get(key), source_right.get(key)
            if left is None and right is None:
                continue
            if key == MANAGER_GC_SOURCE_KEY and (left is None or right is None):
                continue
            if left != right:
                source_diffs.append(f"{key}:{left}!={right}")
        fields["source_match"] = not source_diffs
        if source_diffs:
            differences.extend("source:" + item for item in source_diffs)
    unchanged_left = baseline.get("source_unchanged")
    unchanged_right = candidate.get("source_unchanged")
    fields["source_unchanged_match"] = unchanged_left is True and unchanged_right is True
    if unchanged_left is not True or unchanged_right is not True:
        differences.append(f"source_unchanged:{unchanged_left}!={unchanged_right}")
    token_left = baseline.get("known_field")
    token_right = candidate.get("known_field")
    fields["known_field_tokens"] = [token_left, token_right]
    if token_left and token_right:
        if token_left != token_right:
            left_cond = KNOWN_FIELD_CONDITIONS[token_left]
            right_cond = KNOWN_FIELD_CONDITIONS[token_right]
            if left_cond != right_cond:
                differences.append(
                    f"known_field_condition:{token_left}/{left_cond['family']}"
                    f"!={token_right}/{right_cond['family']}")
                fields["known_field_compatible"] = False
            else:
                fields["known_field_compatible"] = True
        else:
            fields["known_field_compatible"] = True
    elif token_left or token_right:
        fields["known_field_compatible"] = False
        differences.append(f"known_field_vs_anonymous:{token_left}!={token_right}")
    else:
        fields["known_field_compatible"] = True
    run_left = (baseline.get("identity") or {}).get("run_id")
    run_right = (candidate.get("identity") or {}).get("run_id")
    epoch_left = (baseline.get("identity") or {}).get("scene_epoch")
    epoch_right = (candidate.get("identity") or {}).get("scene_epoch")
    fields["same_run_id"] = run_left == run_right
    fields["same_epoch"] = epoch_left == epoch_right
    checked = (fields["ap_match"], fields["control_match"], fields["message_match"],
               fields["profile_match"], fields["boot_match"], fields["source_match"],
               fields["source_unchanged_match"], fields["group_work_timing_match"],
               fields["owned_scheduling_match"], fields["known_field_compatible"])
    compatible = all(checked) and fields["rate_timing_probe_match"] and fields["cpu_timing_match"]
    if fields["async_match"] is False:
        compatible = False
    return {
        "baseline_run_id": run_left, "candidate_run_id": run_right,
        "baseline_epoch": epoch_left, "candidate_epoch": epoch_right,
        "baseline_boot_id": boot_left, "candidate_boot_id": boot_right,
        "run_epoch_note": (
            "different run_id/epoch is allowed only as a descriptive listing; "
            "controlled pairing still requires the same boot, source, window and marks"
        ),
        "fields": fields,
        "differences": differences,
        "compatible": bool(compatible),
    }


def deltas(baseline, candidate):
    def value(record, *path):
        current = record
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    pairs = {
        "gc_gen2_max_thread_cpu_ns": (("gc_windows", "timed", "gen2_thread_cpu_max_ns"), "timed"),
        "gc_thread_cpu_sum_ns": (("gc_windows", "timed", "thread_cpu_sum_ns"), "timed"),
        "gc_gen2_samples": (("gc_windows", "timed", "gen2_samples"), "timed"),
        "preparation_gc_thread_cpu_sum_ns":
            (("gc_windows", "preparation", "thread_cpu_sum_ns"), "preparation"),
        "preparation_gc_gen2_max_thread_cpu_ns":
            (("gc_windows", "preparation", "gen2_thread_cpu_max_ns"), "preparation"),
        "post_gc_thread_cpu_sum_ns": (("gc_windows", "post", "thread_cpu_sum_ns"), "post"),
        "max_entry_lateness_ns": (("rate_scan", "max_entry_lateness_ns"), None),
        "max_work_over_ns": (("rate_scan", "max_work_over_ns"), None),
        "release_excess_total_ns": (("latch", "release_excess_total_ns"), None),
        "creep_total_ns": (("latch", "creep_total_ns"), None),
        "recorded_latch_lateness_ns": (("latch", "recorded_latch_lateness_ns"), None),
    }
    result = {}
    for name, (path, window) in pairs.items():
        left, right = value(baseline, *path), value(candidate, *path)
        result[name] = {
            "baseline": left, "candidate": right,
            "delta_ns": None if (left is None or right is None) else right - left,
            "gc_window": window,
        }
    return result


def compare(baseline_dir, candidate_dir, baseline_overrides, candidate_overrides, self_check=False):
    baseline, _ = analyse_field(baseline_dir, baseline_overrides, "baseline")
    candidate, _ = analyse_field(candidate_dir, candidate_overrides, "candidate")
    report = {
        "schema": "wksim.joint-gc-diagnostic-comparison.v1",
        "mode": "self_check" if self_check else "comparison",
        "classification": "diagnostic_only",
        "production_performance": False,
        "performance_pass": False,
        "claim_class": {
            "descriptive": True,
            "controlled_pairing": False,
            "causal": False,
        },
        "claim_limits": [
            "Descriptive numbers may be listed from a retained field; they are not a pairing.",
            "Controlled pairing requires the same boot, a verifiable non-empty compatible source map, a complete timed window, diagnostic marks, and no overflow/lost.",
            "Integer clocks, counts and overflow/lost marks must be non-negative int and never bool; reversed or negative intervals fail closed.",
            "CPU/cost/ratio/duration values must be finite numbers; NaN/Infinity/strings/bool are rejected and never serialized via allow_nan.",
            "result.json, source maps and metadata must be objects; arrays/null/strings become unavailable or rejected, not AttributeError.",
            "A named field cannot pair with an anonymous run; empty source maps cannot be a controlled pairing.",
            "Causal conclusions are never emitted; two-field overlap is co-occurrence only.",
            "oayggl_s / x39qjvkw / 5lfbcy43 / rfw9nmbb keep their published conditions and are never a controlled pair with each other.",
            "A diagnostic field is probe/CPU-instrumented and is never formal acceptance evidence.",
            "Different run_id/epoch is a descriptive listing only; it does not replace boot/source/window/mark checks.",
            "Missing evidence is reported as unavailable or rejected, never as zero.",
            "The manager GC candidate report is consumed from the runner's real product (result['manager_gc_candidate'] and/or manager-gc-candidate.json); this tool never fabricates or converts it.",
        ],
        "baseline": baseline,
        "candidate": candidate,
        "reasons": [],
    }
    if self_check:
        report["claim_limits"].append(
            "self-check mode: the same retained field is compared with itself to prove the comparator reads it; it is not a candidate evaluation")
    for role in ("baseline", "candidate"):
        record = report[role]
        if record.get("analysis_status") != "analyzed":
            report["reasons"].append(f"{role}:{record.get('analysis_status')}:"
                                     + ",".join(record.get("reasons") or []))
    if report["reasons"]:
        rejected = any((report[role].get("analysis_status") == "rejected")
                       for role in ("baseline", "candidate"))
        report["status"] = "rejected" if rejected else "unavailable"
        return report
    report["identity_compatibility"] = compare_identity(baseline, candidate)
    contract = report["candidate"]["manager_gc_candidate_contract"]
    if contract["status"] == "rejected":
        report["reasons"].append("candidate:manager_gc_candidate_contract:rejected:"
                                 + ",".join(contract["problems"]))
    elif contract["status"] == "unavailable":
        report["reasons"].append("candidate:manager_gc_candidate_contract:unavailable:"
                                 + str(contract.get("reason")))
    if report["baseline"]["manager_gc_candidate_contract"]["status"] == "validated":
        report["reasons"].append("baseline:unexpected_gc_candidate_report")
    for role in ("baseline", "candidate"):
        bounds = (report[role].get("rate_scan") or {}).get("timed_bounds") or {}
        if bounds.get("status") != "observed":
            report["reasons"].append(f"timed_windows_unavailable_for:{role}:"
                                     + str(bounds.get("reason")))
    if not report["identity_compatibility"]["compatible"]:
        report["reasons"].append("identity_incompatible:"
                                 + ",".join(report["identity_compatibility"]["differences"]))
    for role in ("baseline", "candidate"):
        marks = report[role].get("diagnostic_marks") or {}
        if not marks.get("gc_timing"):
            report["reasons"].append(f"missing_diagnostic_marks:{role}:gc_timing")
        window = report[role].get("window") or {}
        if window.get("status") != "complete":
            report["reasons"].append(
                f"incomplete_window:{role}:" + ",".join(window.get("reasons") or []))
        integrity = report[role].get("integrity") or {}
        if integrity.get("status") == "rejected":
            report["reasons"].append(
                f"overflow_or_lost:{role}:" + ",".join((integrity.get("problems") or [])[:8]))
        windows = report[role].get("gc_windows") or {}
        if any((windows.get(name) or {}).get("samples") for name in _TIMEBASE_WINDOWS):
            report["reasons"].append(f"timebase_inconsistent:{role}")
        rate_scan = report[role].get("rate_scan") or {}
        field_reasons = report[role].get("reasons") or []
        if rate_scan.get("clock_problems") or any(
                item.startswith("invalid_clock:") for item in field_reasons):
            report["reasons"].append(f"invalid_clock:{role}")
        if any(item.startswith("invalid_cost:") for item in field_reasons):
            report["reasons"].append(f"invalid_cost:{role}")
    if report["reasons"]:
        report["status"] = ("rejected" if any("rejected" in reason or "unexpected" in reason
                                              or "incompatible" in reason
                                              or "overflow_or_lost" in reason
                                              or "missing_diagnostic_marks" in reason
                                              or "incomplete_window" in reason
                                              or "timebase_inconsistent" in reason
                                              or "invalid_clock" in reason
                                              or "invalid_cost" in reason
                                              for reason in report["reasons"])
                            else "unavailable")
        report["claim_class"]["controlled_pairing"] = False
        report["claim_class"]["causal"] = False
        return report
    report["deltas"] = deltas(baseline, candidate)
    report["status"] = "compared"
    report["claim_class"]["controlled_pairing"] = not self_check
    report["claim_class"]["causal"] = False
    report["nesting"] = report["candidate"]["nesting"]
    report["field_sections"] = {
        role: {
            "gc": report[role]["gc"],
            "latch_status": report[role]["latch_status"],
            "latch_reconciliation_status":
                report[role]["latch"]["latch_reconciliation"]["status"],
            "nesting": report[role]["nesting"]["status"],
            "manager_gc_candidate_contract_status":
                report[role]["manager_gc_candidate_contract"]["status"],
            "boot_id": report[role].get("boot_id"),
            "known_field": report[role].get("known_field"),
            "window": (report[role].get("window") or {}).get("status"),
        }
        for role in ("baseline", "candidate")
    }
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--self-check", action="store_true")
    for role in ("baseline", "candidate"):
        for key in ("result", "rate", "wire", "pre-run-identity", "manager-gc-report"):
            parser.add_argument(f"--{role}-{key}", type=Path)
    args = parser.parse_args(argv)
    overrides = {
        role: {key.replace("-", "_"): getattr(args, f"{role}_{key.replace('-', '_')}")
               for key in ("result", "rate", "wire", "pre-run-identity", "manager-gc-report")}
        for role in ("baseline", "candidate")
    }
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing evidence: {args.output}")
    try:
        report = compare(args.baseline, args.candidate,
                         overrides["baseline"], overrides["candidate"],
                         self_check=args.self_check)
    except Exception as error:
        report = {
            "schema": "wksim.joint-gc-diagnostic-comparison.v1",
            "status": "unavailable",
            "mode": "self_check" if args.self_check else "comparison",
            "classification": "diagnostic_only",
            "production_performance": False,
            "performance_pass": False,
            "claim_class": {
                "descriptive": True,
                "controlled_pairing": False,
                "causal": False,
            },
            "reasons": [f"compare_failed:{type(error).__name__}: {error}"],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = json.dumps(report, indent=1, allow_nan=False)
    except (ValueError, TypeError) as error:
        report = {
            "schema": "wksim.joint-gc-diagnostic-comparison.v1",
            "status": "rejected",
            "mode": report.get("mode", "comparison"),
            "classification": "diagnostic_only",
            "production_performance": False,
            "performance_pass": False,
            "claim_class": {
                "descriptive": True,
                "controlled_pairing": False,
                "causal": False,
            },
            "reasons": [f"report_not_json_finite:{type(error).__name__}"],
        }
        payload = json.dumps(report, indent=1, allow_nan=False)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(payload)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "mode": report["mode"],
                      "reasons": report["reasons"]}, allow_nan=False))
    return 0 if report["status"] == "compared" else 1


if __name__ == "__main__":
    sys.exit(main())
