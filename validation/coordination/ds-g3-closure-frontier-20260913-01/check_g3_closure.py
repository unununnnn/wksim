#!/usr/bin/env python3
"""Read-only closure audit checks for the G3 Prometheus scene-admission frontier.

Scope: open issue #29 (AC2/AC3) and the #102 trajectory/scene-admission contract,
at the checkout HEAD recorded by ``env`` in the emitted JSON.

This script is PURE PYTHON and READ-ONLY with respect to the repository:
  * it imports committed modules and re-derives their published identities;
  * it runs the committed pure-Python suite in-process (no pytest needed);
  * it re-runs the two committed #29 fixture auditors via a file-captured
    subprocess (deliberately NOT a pipe: the harness sandbox forbids piped
    stdio in some modes);
  * it exhibits a false-PASS witness and a prototype sound certificate.

It does NOT run any native build, ROS, SITL, flight-controller, model worker,
UE, or MATLAB path, and it never writes outside its own output file.

Usage (from the repository root):
    python -B validation/coordination/ds-g3-closure-frontier-20260913-01/check_g3_closure.py

Output: checks.json next to this script (UTF-8, sorted keys, no NaN).
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import math
import os
import pathlib
import subprocess
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / "checks.json"

AUDIT_COMMIT = "0a1caa116e31700155a7abb567176c48668c0e8e"
ARCH_COMMIT = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"
TERRAIN_RESET_COMMIT = "b8d141c"  # baseline of the #29 terrain-reset artifact

# Exact artifacts this audit cites.  "pre-arch" = authored before ARCH_COMMIT.
ARTIFACTS = {
    "docs/plan/29-terrain-closure-report.md": "pre-arch",
    "docs/plan/102-trajectory-scene-admission-contract.md": "pre-arch",
    "Simulator/wksim_planning/ego_scene_admission.py": "seam",
    "Simulator/wksim_planning/scene_profile.py": "seam",
    "Simulator/wksim_planning/ego_bspline_bridge.py": "seam",
    "Simulator/wksim_planning/ego_evaluator.py": "seam",
    "Simulator/wksim_planning/ego_trajectory_adapter.py": "dep",
    "Simulator/wksim_planning/trajectory_session.py": "dep",
    "Simulator/wksim_runtime/planner_scene_binding.py": "seam",
    "Simulator/wksim_runtime/planner_transport_pump.py": "consumer",
    "Simulator/wksim_runtime/bspline_tcp_envelope.py": "transport",
    "validation/test_ego_scene_admission.py": "test",
    "validation/lunar-29-terrain-reset-c8f05c6e/result.json": "29-evidence",
}

CONTRACT_IDENTITIES = {
    "scene_id": "ego-single-box-v1",
    "scene_hash": "40ee928113c1ad6b2f9987c01506ee34171bd15099e6e7c9425496498cb8d0ba",
    "profile_hash": "49da4cccaf3c172c510daa3cc3bd0ddad521669c4d64f3c8bc1a7fe71d9730f7",
    "geometry_id": "ego-single-box-v1:obstacle",
    "obstacle_min": [-0.5, -1.0, 0.0],
    "obstacle_max": [0.5, 1.0, 5.5],
    "map_min": [-10.0, -6.0, 0.0],
    "map_max": [10.0, 6.0, 6.0],
    "vehicle_radius": 0.35,
    "required_clearance": 0.30,
    "clearance_margin": 0.65,
    "legacy_scene_hash": "60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514",
}

# Exactly the 10 source identities pinned by the #29 terrain-reset artifact.
TERRAIN_RESET_PINS = [
    "Simulator/wksim_core/joint.py",
    "Simulator/wksim_core/model.cpp",
    "Simulator/wksim_core/model.py",
    "Simulator/wksim_core/static_contact.py",
    "Simulator/wksim_core/worker.py",
    "Simulator/wksim_runtime/contact_observer.py",
    "Simulator/wksim_runtime/scene_clock.py",
    "Simulator/wksim_runtime/static-scene-v1.json",
    "Simulator/wksim_runtime/terrain_feedback.py",
    "tools/probe_joint_terrain_feedback.py",
]

checks: list[dict] = []


def check(name: str, ok: bool, detail) -> bool:
    checks.append({"check": name, "ok": bool(ok), "detail": detail})
    return bool(ok)


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


# --------------------------------------------------------------------------
# A. environment
# --------------------------------------------------------------------------
def section_env() -> dict:
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ARCH_COMMIT, "HEAD"], cwd=ROOT
    ).returncode
    base_ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", AUDIT_COMMIT, "HEAD"], cwd=ROOT
    ).returncode
    head = git("rev-parse", "HEAD")
    # The checkout is shared: a concurrent writer advanced HEAD past the
    # requested audit base while this audit ran.  The audit remains valid only
    # if none of the cited artifacts changed between that base and HEAD.
    changed = git("diff", "--name-only", AUDIT_COMMIT, "HEAD", "--", *ARTIFACTS).splitlines()
    changed = [line for line in changed if line.strip()]
    check("audit_commit_is_ancestor_of_head", base_ancestor == 0, f"exit={base_ancestor}")
    check("architecture_commit_is_ancestor", ancestor == 0, f"exit={ancestor}")
    check("cited_artifacts_unchanged_since_audit_commit", not changed, changed)
    return {
        "cwd": str(pathlib.Path.cwd()),
        "repo_root": str(ROOT),
        "head_observed_at_run": head,
        "audit_commit": AUDIT_COMMIT,
        "audit_commit_is_ancestor_of_head": base_ancestor == 0,
        "architecture_commit": ARCH_COMMIT,
        "architecture_commit_is_ancestor": ancestor == 0,
        "cited_artifacts_changed_since_audit_commit": changed,
        "python": sys.version.split()[0],
    }


# --------------------------------------------------------------------------
# B. cited artifact identity
# --------------------------------------------------------------------------
def section_artifacts() -> dict:
    out = {}
    for rel, kind in ARTIFACTS.items():
        path = ROOT / rel
        if not path.is_file():
            out[rel] = {"kind": kind, "present": False}
            check(f"artifact_present::{rel}", False, "missing")
            continue
        blob = git("rev-parse", f"HEAD:{rel}")
        last = git("log", "-1", "--format=%h %cI %s", "--", rel)
        out[rel] = {
            "kind": kind,
            "present": True,
            "sha256_file": sha256_file(path),
            "git_blob": blob,
            "last_commit": last,
        }
        check(f"artifact_present::{rel}", True, blob[:12])
    return out


# --------------------------------------------------------------------------
# C. contract claims
# --------------------------------------------------------------------------
def section_contract() -> dict:
    from Simulator.wksim_planning.ego_bspline_bridge import BSPLINE_FIELDS
    from Simulator.wksim_planning.ego_scene_admission import (
        ADMISSION_REASONS,
        DEFAULT_SAMPLE_PERIOD_S,
        EVIDENCE_KIND,
        MAX_ADMISSION_SAMPLES,
        NON_CLAIMS,
        SceneAdmissionError,
        _sample_times,
        assess_spline_clearance,
    )
    from Simulator.wksim_runtime.planner_scene_binding import EGO_SINGLE_BOX_BINDING as B
    from Simulator.wksim_planning.scene_profile import EGO_SINGLE_BOX_V1 as P

    obs, mb = P.obstacle, P.map_bounds
    derived = {
        "scene_id": B.scene_id,
        "scene_hash": B.scene_hash,
        "geometry_id": B.geometry_id,
        "profile_hash": P.profile_hash,
        "obstacle_min": list(obs.minimum),
        "obstacle_max": list(obs.maximum),
        "map_min": list(mb.minimum),
        "map_max": list(mb.maximum),
        "vehicle_radius": P.vehicle_radius,
        "required_clearance": P.required_clearance,
        "clearance_margin": P.vehicle_radius + P.required_clearance,
    }
    for key, expected in CONTRACT_IDENTITIES.items():
        if key == "legacy_scene_hash":
            continue
        if key == "clearance_margin":
            # The contract publishes 0.65; the sum is the nearest double 0.6499999999999999.
            check(
                "identity::clearance_margin",
                math.isclose(derived[key], expected, rel_tol=0.0, abs_tol=1e-12),
                {"derived": derived[key], "claimed": expected, "exact_equality": derived[key] == expected},
            )
            continue
        check(f"identity::{key}", derived[key] == expected, {"derived": derived[key], "claimed": expected})

    check("evidence_kind_constant", EVIDENCE_KIND == "sampled_segment_checked", EVIDENCE_KIND)
    check("default_sample_period_10ms", DEFAULT_SAMPLE_PERIOD_S == 0.010, DEFAULT_SAMPLE_PERIOD_S)
    check("max_admission_samples", MAX_ADMISSION_SAMPLES == 1_000_000, MAX_ADMISSION_SAMPLES)
    check("reason_count_11", len(ADMISSION_REASONS) == 11, list(ADMISSION_REASONS))
    check("non_claims_declare_sampled_only", any("not for the continuous" in n for n in NON_CLAIMS), list(NON_CLAIMS))

    # Grid-boundary claim from the contract: (MAX-1)*step is the largest allowed
    # duration; a duration above it fails closed with invalid_grid.
    step = DEFAULT_SAMPLE_PERIOD_S
    boundary = (MAX_ADMISSION_SAMPLES - 1) * step
    at = _sample_times(boundary, step)
    check("grid_boundary_yields_max_samples", len(at) == MAX_ADMISSION_SAMPLES, len(at))
    try:
        _sample_times(math.nextafter(boundary, math.inf), step)
        above = "accepted"
    except SceneAdmissionError as error:
        above = error.reason
    check("grid_above_boundary_fails_closed", above == "invalid_grid", above)
    check("grid_starts_at_exact_zero", at[0] == 0.0, at[0])
    check("grid_ends_at_exact_duration", at[-1] == float(boundary), at[-1])

    # A PASS must be labelled as non-continuous.
    from Simulator.wksim_planning.ego_evaluator import EgoSpline
    safe = EgoSpline(3, _uniform_knots(3, 8, 0.1), [(3.0, 0.0, 2.0)] * 8)
    report = assess_spline_clearance(safe)
    check("safe_spline_is_admitted", report.admitted is True, report.admitted)
    check("admitted_report_continuous_proof_false", report.continuous_proof is False, report.continuous_proof)
    check("admitted_report_evidence_kind", report.evidence_kind == "sampled_segment_checked", report.evidence_kind)
    return {"derived_identities": derived, "grid_boundary_duration_s": boundary, "sample_period_s": step}


def _uniform_knots(order: int, num_points: int, interval: float) -> list:
    n = num_points - 1
    m = n + order + 1
    knots = [0.0] * (m + 1)
    for i in range(m + 1):
        knots[i] = float(-order + i) * interval if i <= order else knots[i - 1] + interval
    return knots


# --------------------------------------------------------------------------
# D. committed pure-Python suite, re-run at HEAD
# --------------------------------------------------------------------------
def section_suite() -> dict:
    spec = importlib.util.spec_from_file_location(
        "committed_test_ego_scene_admission", ROOT / "validation" / "test_ego_scene_admission.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)
    detail = {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
    }
    check("committed_suite_22_tests", result.testsRun == 22, detail)
    check("committed_suite_all_pass", not result.failures and not result.errors, detail)
    return detail


# --------------------------------------------------------------------------
# E. #29 fixture auditors, re-run at HEAD (file-captured, no pipes)
# --------------------------------------------------------------------------
def section_lunar_audits() -> dict:
    out = {}
    for name, rel in (
        ("static_contact", "validation/lunar-29-static-contact/audit.py"),
        ("live_contact", "validation/lunar-29-live-contact/audit.py"),
    ):
        capture = HERE / f"_capture_{name}.txt"
        with open(capture, "w", encoding="utf-8", newline="") as handle:
            proc = subprocess.run(
                [sys.executable, "-B", str(ROOT / rel)],
                cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
            )
        text = capture.read_text(encoding="utf-8").strip()
        capture.unlink()
        try:
            parsed = json.loads(text.splitlines()[-1])
        except (ValueError, IndexError):
            parsed = {"unparsed": text}
        out[name] = {"exit_code": proc.returncode, "result": parsed}
        check(f"lunar29_{name}_exit0", proc.returncode == 0, proc.returncode)
        check(f"lunar29_{name}_status_pass", parsed.get("status") == "pass", parsed)
    check(
        "lunar29_static_assertions_85",
        out["static_contact"]["result"].get("assertions") == 85,
        out["static_contact"]["result"],
    )
    check(
        "lunar29_live_assertions_30895",
        out["live_contact"]["result"].get("assertions") == 30895,
        out["live_contact"]["result"],
    )
    return out


# --------------------------------------------------------------------------
# F. #29 terrain-reset artifact: pinned-source drift vs HEAD
# --------------------------------------------------------------------------
def section_pin_drift() -> dict:
    artifact = json.loads(
        (ROOT / "validation/lunar-29-terrain-reset-c8f05c6e/result.json").read_text(encoding="utf-8")
    )
    pins = artifact["source_sha256"]
    drift, same = [], []
    for rel in TERRAIN_RESET_PINS:
        pinned = pins[rel]
        current = sha256_file(ROOT / rel)
        record = {"path": rel, "pinned": pinned, "head": current}
        if current == pinned:
            same.append(record)
        else:
            # Was the pin exact at the artifact's OWN producing baseline?
            proc = subprocess.run(
                ["git", "show", f"{TERRAIN_RESET_COMMIT}:{rel}"], cwd=ROOT, capture_output=True
            )
            record["pin_matched_at_producing_commit"] = (
                proc.returncode == 0 and hashlib.sha256(proc.stdout).hexdigest() == pinned
            )
            record["head_last_commit"] = git("log", "-1", "--format=%h %cI %s", "--", rel)
            drift.append(record)
    check("terrain_reset_pin_drift_present", len(drift) == 2, [d["path"] for d in drift])
    return {
        "pinned_artifact_status": artifact.get("status"),
        "pinned_library_sha256": artifact.get("library", {}).get("sha256"),
        "pinned_count": len(pins),
        "same": same,
        "drift": drift,
        "artifact_reproducible_from_head": not drift,
    }


# --------------------------------------------------------------------------
# G. the gap: a sampled-PASS that is a true continuous clearance violation
# --------------------------------------------------------------------------
CASE_C, CASE_A, KNOT_H, N_POINTS = 1.15, 0.30, 0.005, 203


def witness_spline():
    """Alternating control points at knot interval H whose curve period equals the
    10 ms sample stride, so every sample lands on the curve's peak in x."""
    from Simulator.wksim_planning.ego_evaluator import EgoSpline
    pts = [(CASE_C - CASE_A * ((-1) ** i), 0.0, 2.0) for i in range(N_POINTS)]
    return EgoSpline(3, _uniform_knots(3, N_POINTS, KNOT_H), pts)


def true_min_clearance(spline, samples: int = 400_000) -> float:
    """Dense independent scan of the CONTINUOUS curve (not the 10 ms grid)."""
    from Simulator.wksim_planning.scene_profile import segment_clearance
    duration = spline.duration
    best = math.inf
    previous = spline.position_at(0.0)
    for k in range(1, samples + 1):
        current = spline.position_at(duration * k / samples)
        best = min(best, segment_clearance(previous, current))
        previous = current
    return best


def section_gap() -> dict:
    from Simulator.wksim_planning.ego_scene_admission import assess_spline_clearance
    from Simulator.wksim_planning.scene_profile import EGO_SINGLE_BOX_V1 as P

    spline = witness_spline()
    report = assess_spline_clearance(spline)
    truth = true_min_clearance(spline)
    sampled_x = [spline.position_at(t)[0] for t in (0.0, 0.005, 0.01, 0.015, 0.05)]
    detail = {
        "sampled_grid_admitted": report.admitted,
        "sampled_grid_min_obstacle_clearance": report.min_obstacle_clearance,
        "sampled_grid_violation": report.violation,
        "true_min_obstacle_clearance_400k": truth,
        "required_clearance": P.required_clearance,
        "infringement_m": P.required_clearance - truth,
        "infringement_fraction_of_requirement": (P.required_clearance - truth) / P.required_clearance,
        "control_point_x_range": [CASE_C - CASE_A, CASE_C + CASE_A],
        "curve_x_at_t": sampled_x,
        "knot_interval_s": KNOT_H,
        "sample_stride_s": 0.010,
    }
    # The gate reports a clean PASS while the continuous curve is inside the margin.
    check("gap_witness_grid_admits", report.admitted is True, report.admitted)
    check("gap_witness_declares_no_continuous_proof", report.continuous_proof is False, report.continuous_proof)
    check(
        "gap_witness_true_curve_violates",
        truth < P.required_clearance - 1e-6,
        {"true": truth, "required": P.required_clearance},
    )
    check(
        "gap_witness_infringement_is_material",
        (P.required_clearance - truth) >= 0.05,
        P.required_clearance - truth,
    )
    return detail


# --------------------------------------------------------------------------
# H. prototype SOUND certificate (convex-hull / control-bbox per knot span)
# --------------------------------------------------------------------------
def _aabb_gap(a_lo, a_hi, b_lo, b_hi) -> float:
    total = 0.0
    for alo, ahi, blo, bhi in zip(a_lo, a_hi, b_lo, b_hi):
        total += max(0.0, max(alo - bhi, blo - ahi)) ** 2
    return math.sqrt(total)


def sound_certificate(spline, profile) -> dict:
    """Conservative but SOUND: on span [u_k,u_{k+1}) the curve lies in the convex
    hull of P_{k-p}..P_k, hence in their bounding box."""
    bs = spline.position
    order, knots, pts = bs.order, list(bs.knots), list(bs._points)
    n, p = len(pts) - 1, bs.order
    m = n + p + 1
    obs_lo, obs_hi = profile.obstacle.minimum, profile.obstacle.maximum
    mb = profile.map_bounds
    inset_lo = tuple(lo + profile.vehicle_radius + profile.required_clearance for lo in mb.minimum)
    inset_hi = tuple(hi - profile.vehicle_radius - profile.required_clearance for hi in mb.maximum)
    worst_obs, worst_env, spans = math.inf, math.inf, 0
    for k in range(p, m - p):
        active = pts[k - p:k + 1]
        spans += 1
        lo = tuple(min(q[c] for q in active) for c in range(3))
        hi = tuple(max(q[c] for q in active) for c in range(3))
        worst_obs = min(worst_obs, _aabb_gap(lo, hi, obs_lo, obs_hi) - profile.vehicle_radius)
        for c in range(3):
            worst_env = min(worst_env, lo[c] - inset_lo[c], inset_hi[c] - hi[c])
    return {
        "span_count": spans,
        "min_obstacle_net_clearance": worst_obs,
        "min_envelope_margin": worst_env,
        "obstacle_ok": worst_obs >= profile.required_clearance,
        "envelope_ok": worst_env >= 0.0,
        "continuous_proof": worst_obs >= profile.required_clearance and worst_env >= 0.0,
    }


def section_certificate() -> dict:
    from Simulator.wksim_planning.ego_evaluator import EgoSpline
    from Simulator.wksim_planning.scene_profile import EGO_SINGLE_BOX_V1 as P

    def build(points):
        return EgoSpline(3, _uniform_knots(3, N_POINTS, KNOT_H), points)

    cases = {
        "witness_false_pass": [(CASE_C - CASE_A * ((-1) ** i), 0.0, 2.0) for i in range(N_POINTS)],
        "constant_1cm_margin": [(CASE_C + 0.01, 0.0, 2.0) for i in range(N_POINTS)],
        "small_safe_sinusoid": [
            (CASE_C + 0.02 + 0.01 * math.sin(i * math.pi / 25.0), 0.0, 2.0) for i in range(N_POINTS)
        ],
    }
    out = {name: sound_certificate(build(points), P) for name, points in cases.items()}
    check(
        "certificate_rejects_false_pass",
        out["witness_false_pass"]["continuous_proof"] is False,
        out["witness_false_pass"],
    )
    check(
        "certificate_accepts_safe_curves",
        out["constant_1cm_margin"]["continuous_proof"] is True
        and out["small_safe_sinusoid"]["continuous_proof"] is True,
        {k: v["continuous_proof"] for k, v in out.items()},
    )
    return out


# --------------------------------------------------------------------------
# I. wiring: is the seam reachable from a runtime path?
# --------------------------------------------------------------------------
def section_wiring() -> dict:
    pump = (ROOT / "Simulator/wksim_runtime/planner_transport_pump.py").read_text(encoding="utf-8")
    consumers = []
    for rel in (
        "Simulator/wksim_runtime/planner_transport_pump.py",
        "ros2/src/prometheus_control/CMakeLists.txt",
        "tools/build-joint-control.sh",
    ):
        path = ROOT / rel
        if path.is_file() and "ego_scene_admission" in path.read_text(encoding="utf-8", errors="replace"):
            consumers.append(rel)
    check("seam_has_runtime_consumer", "Simulator/wksim_runtime/planner_transport_pump.py" in consumers, consumers)
    honest = "no continuous-curve or flight-safety claim" in pump
    check("pump_declares_no_continuous_claim", honest, honest)
    return {"consumers_referencing_seam": consumers, "pump_declares_no_continuous_claim": honest}


def main() -> int:
    sys.path.insert(0, str(ROOT))
    result = {
        "schema": "wksim.g3-closure-frontier-audit.v1",
        "env": section_env(),
        "artifacts": section_artifacts(),
        "contract": section_contract(),
        "committed_suite": section_suite(),
        "lunar29_auditors": section_lunar_audits(),
        "terrain_reset_pin_drift": section_pin_drift(),
        "continuous_gap": section_gap(),
        "sound_certificate_prototype": section_certificate(),
        "wiring": section_wiring(),
    }
    result["checks"] = checks
    result["checks_summary"] = {
        "total": len(checks),
        "passed": sum(1 for c in checks if c["ok"]),
        "failed": [c["check"] for c in checks if not c["ok"]],
    }
    OUT.write_text(
        json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(json.dumps(result["checks_summary"], sort_keys=True))
    print(f"wrote {OUT}")
    return 0 if not result["checks_summary"]["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
