"""Offline analyzer for early-manager-work probe reports (diagnostic only).

Reads one ``early-manager-work.json`` produced by the REAL
``tools/early_manager_work_probe.py`` (never re-implements its gates) and:
- verifies the run/epoch/segment/window identity (window = anchor + 10 s,
  warmup marker = anchor + 2 s);
- validates every sample against the window (bounds, types, monotonicity,
  crossing/warmup flag consistency), preserving invalid ones as evidence;
- reports per-phase wall/current-thread-CPU distributions and max sample tick
  for VALID ok samples;
- preserves truncation/drop/diagnostic-error/crossing/error-outcome states.

Hard non-claims (embedded in every output):
- the five phases are sequential hotspot segments; they and any outer overlap
  are NEVER summed into a window closure;
- thread CPU is the manager thread only and excludes model worker CPU;
- wall-minus-CPU is not a pure scheduling/descheduling attribution;
- rate_begin_group includes the active release sleep inside begin_group;
- a 10 s diagnostic window is never extrapolated to the full flight and is
  never a performance pass.

CLI: analyze_early_manager_work.py <report.json> --output <path> (exclusive
create; refuses to overwrite).  Exit 0 on pass, 1 on any verification failure.
"""

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path


EXPECTED_DIAGNOSTIC = "early_manager_work_probe"
WINDOW_NS = 10_000_000_000
WARMUP_NS = 2_000_000_000
PHASES = ("manager_health", "rate_begin_group", "physics_advance",
          "clock_publication_log", "post_advance_readiness_summary")
MAX_INVALID_LISTED = 64

NON_CLAIMS = (
    "phases are sequential segments and are never summed into a closure; outer overlap cannot be added either",
    "thread CPU is the manager thread only and excludes model worker CPU",
    "wall minus thread CPU is not a pure scheduling/descheduling attribution",
    "rate_begin_group includes the active release sleep inside begin_group",
    "the 10 s window is not extrapolated to the full flight",
    "diagnostic evidence, never a performance pass",
)


def _fail(reasons, message):
    reasons.append(message)


def _strict_int(value):
    return type(value) is int and not isinstance(value, bool)


def _verify_identity(report, reasons):
    if report.get("diagnostic") != EXPECTED_DIAGNOSTIC:
        _fail(reasons, "diagnostic kind mismatch")
    if report.get("diagnostic_only") is not True:
        _fail(reasons, "diagnostic_only flag missing")
    if report.get("production_performance") is not False:
        _fail(reasons, "production_performance must be false")
    sha = report.get("source_sha256")
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        _fail(reasons, "source_sha256 must be 64 lowercase hex")
    if report.get("window_ns") != WINDOW_NS:
        _fail(reasons, "window_ns must be 10 wall seconds")
    if report.get("warmup_ns") != WARMUP_NS:
        _fail(reasons, "warmup_ns must be 2 wall seconds")
    window = report.get("window")
    if not isinstance(window, dict):
        _fail(reasons, "window missing")
        return None
    anchor = window.get("anchor_wall_ns")
    cutoff = window.get("cutoff_wall_ns")
    warmup_after = window.get("warmup_after_ns")
    for name, value in (("anchor_wall_ns", anchor), ("cutoff_wall_ns", cutoff),
                        ("warmup_after_ns", warmup_after)):
        if not _strict_int(value):
            _fail(reasons, f"window.{name} must be an integer")
    if reasons:
        return None
    if cutoff - anchor != WINDOW_NS:
        _fail(reasons, "cutoff != anchor + 10 s")
    if warmup_after - anchor != WARMUP_NS:
        _fail(reasons, "warmup_after != anchor + 2 s")
    epoch = report.get("anchor_epoch")
    segment = report.get("anchor_segment")
    if not isinstance(epoch, str) or not epoch:
        _fail(reasons, "anchor_epoch missing")
    if not _strict_int(segment):
        _fail(reasons, "anchor_segment must be an integer")
    identity = report.get("identity")
    if not isinstance(identity, dict):
        _fail(reasons, "identity missing")
    else:
        if identity.get("scene_epoch") != epoch:
            _fail(reasons, "identity.scene_epoch differs from anchor_epoch")
        identity_segment = identity.get("segment")
        if not _strict_int(identity_segment):
            _fail(reasons, "identity.segment must be a plain integer (bool rejected)")
        elif identity_segment != segment:
            _fail(reasons, "identity.segment differs from anchor_segment")
        if not isinstance(identity.get("run_id"), str) or not identity["run_id"]:
            _fail(reasons, "identity.run_id missing")
    for name in ("truncated", "dropped", "max_samples",
                 "diagnostic_error_total", "diagnostic_error_dropped"):
        value = report.get(name)
        if name == "truncated":
            if type(value) is not bool:
                _fail(reasons, "truncated must be a bool")
        elif not _strict_int(value) or value < 0:
            _fail(reasons, f"{name} must be a non-negative integer")
    if _strict_int(report.get("max_samples")) and report["max_samples"] <= 0:
        _fail(reasons, "max_samples must be positive")
    error_list = report.get("diagnostic_errors")
    if not isinstance(error_list, list):
        _fail(reasons, "diagnostic_errors must be a list")
    elif (_strict_int(report.get("diagnostic_error_total"))
            and _strict_int(report.get("diagnostic_error_dropped"))
            and report["diagnostic_error_total"]
            != len(error_list) + report["diagnostic_error_dropped"]):
        _fail(reasons,
              "diagnostic_error_total != len(diagnostic_errors) + diagnostic_error_dropped")
    if _strict_int(report.get("diagnostic_error_total")) and report.get(
            "diagnostic_clean") is not (report["diagnostic_error_total"] == 0):
        _fail(reasons, "diagnostic_clean disagrees with diagnostic_error_total")
    if not isinstance(report.get("samples"), list):
        _fail(reasons, "samples missing")
    return None if reasons else (anchor, cutoff, warmup_after)


def _validate_sample(sample, index, bounds, reasons):
    """Returns an error string or None.  Never mutates."""
    anchor, cutoff, warmup_after = bounds
    if type(sample) is not dict:
        return f"samples[{index}] must be a dict"
    if sample.get("phase") not in PHASES:
        return f"samples[{index}].phase unknown"
    ints = ("start_ns", "end_ns", "wall_ns", "thread_cpu_ns",
            "start_tick", "end_tick")
    for name in ints:
        if not _strict_int(sample.get(name)):
            return f"samples[{index}].{name} must be an integer"
    start_ns, end_ns = sample["start_ns"], sample["end_ns"]
    wall_ns, cpu_ns = sample["wall_ns"], sample["thread_cpu_ns"]
    if sample["end_tick"] < sample["start_tick"]:
        return f"samples[{index}] end_tick < start_tick"
    if wall_ns != end_ns - start_ns:
        return f"samples[{index}].wall_ns inconsistent with start/end"
    if wall_ns < 0 or cpu_ns < 0:
        return f"samples[{index}] negative duration"
    if start_ns < anchor:
        return f"samples[{index}] starts before the anchor"
    if start_ns >= cutoff:
        return f"samples[{index}] starts past the cutoff"
    if type(sample.get("crossing")) is not bool:
        return f"samples[{index}].crossing must be a bool"
    if (end_ns >= cutoff) != sample["crossing"]:
        return f"samples[{index}].crossing inconsistent with cutoff"
    if type(sample.get("warmup")) is not bool:
        return f"samples[{index}].warmup must be a bool"
    if (start_ns < warmup_after) != sample["warmup"]:
        return f"samples[{index}].warmup inconsistent with warmup boundary"
    if sample.get("outcome") not in ("ok", "error"):
        return f"samples[{index}].outcome must be ok/error"
    return None


def _distribution(values):
    if not values:
        return dict(count=0)
    return dict(
        count=len(values),
        min_ns=min(values),
        median_ns=statistics.median(values),
        max_ns=max(values),
    )


def _peak_sample(samples, key):
    """The complete single sample with the largest ``key`` value."""
    peak = max(samples, key=lambda s: (s[key], s["start_ns"]), default=None)
    if peak is None:
        return None
    return dict(start_tick=peak["start_tick"], start_ns=peak["start_ns"],
                end_ns=peak["end_ns"], wall_ns=peak["wall_ns"],
                thread_cpu_ns=peak["thread_cpu_ns"])


def analyze(report):
    """Pure analysis of one probe report dict; returns the analysis dict."""
    reasons = []
    bounds = _verify_identity(report, reasons)
    samples = report.get("samples") if isinstance(report.get("samples"), list) else []
    valid, invalid = [], []
    invalid_total = 0
    if bounds is not None and not reasons:
        for index, sample in enumerate(samples):
            error = _validate_sample(sample, index, bounds, reasons)
            if error is None:
                valid.append(sample)
            else:
                invalid_total += 1
                invalid.append(error)
        if len(invalid) > MAX_INVALID_LISTED:
            invalid = invalid[:MAX_INVALID_LISTED] + [
                f"... {invalid_total - MAX_INVALID_LISTED} more invalid samples"]
    elif isinstance(report.get("samples"), list):
        invalid_total = len(samples)
        invalid.append("sample validation skipped: identity verification failed")

    per_phase = {}
    for phase in PHASES:
        ok = [s for s in valid if s["phase"] == phase and s["outcome"] == "ok"]
        per_phase[phase] = dict(
            wall=_distribution([s["wall_ns"] for s in ok]),
            thread_cpu=_distribution([s["thread_cpu_ns"] for s in ok]),
            # The PEAK samples, whole: wall_peak and cpu_peak are DIFFERENT
            # samples in general; each record is one complete sample.
            wall_peak_sample=_peak_sample(ok, "wall_ns"),
            cpu_peak_sample=_peak_sample(ok, "thread_cpu_ns"),
            last_sample_tick=(max((s["start_tick"] for s in ok), default=None)),
            error_outcome=sum(1 for s in valid
                              if s["phase"] == phase and s["outcome"] == "error"),
            crossing=sum(1 for s in valid if s["phase"] == phase and s["crossing"]),
        )

    states = dict(
        truncated=report.get("truncated"),
        dropped=report.get("dropped"),
        diagnostic_error_total=report.get("diagnostic_error_total"),
        diagnostic_error_dropped=report.get("diagnostic_error_dropped"),
        diagnostic_errors=list(report.get("diagnostic_errors", []))
        if isinstance(report.get("diagnostic_errors"), list) else [],
        valid_samples=len(valid),
        invalid_samples=invalid_total,
        crossing_total=sum(1 for s in valid if s["crossing"]),
        error_outcome_total=sum(1 for s in valid if s["outcome"] == "error"),
    )
    if invalid and not reasons:
        reasons.append(f"{len(invalid)} invalid sample(s) present (preserved)")
    return dict(
        status="failed" if reasons else "pass",
        reasons=reasons,
        scope="10 wall-second early manager work window, diagnostic only",
        identity=report.get("identity"),
        anchor_epoch=report.get("anchor_epoch"),
        anchor_segment=report.get("anchor_segment"),
        window=report.get("window"),
        per_phase=per_phase,
        states=states,
        non_claims=list(NON_CLAIMS),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    raw = args.report.read_bytes()
    analysis = analyze(json.loads(raw.decode("utf-8")))
    analysis["input_sha256"] = hashlib.sha256(raw).hexdigest()
    if args.output.exists():
        print(f"refusing to overwrite existing output: {args.output}",
              file=sys.stderr)
        return 1
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(analysis, indent=2) + "\n")
    print(json.dumps({"status": analysis["status"], "output": str(args.output),
                      "reasons": analysis["reasons"]}, indent=1))
    return 0 if analysis["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
