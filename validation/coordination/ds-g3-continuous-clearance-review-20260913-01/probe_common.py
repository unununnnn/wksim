"""Shared helpers for the independent G3 continuous-clearance adversarial probes.

Scope: pure Python.  No native build, no ROS/DDS, no SITL/UE/MATLAB, no socket,
no model worker, no wall clock, no unseeded RNG.  Nothing here writes outside the
review directory.  Every probe is a COUNTEREXAMPLE SEARCH (higher density only
makes a counterexample more likely to be found); a probe that finds nothing is
evidence, never a proof.

All scene constants are read from the committed binding, never re-declared.
"""
from __future__ import annotations

from fractions import Fraction
import json
import math
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Simulator.wksim_planning.ego_evaluator import (  # noqa: E402
    EgoSpline,
    SplineError,
    UniformBspline,
)
from Simulator.wksim_planning.ego_scene_admission import (  # noqa: E402
    CONTINUOUS_EVIDENCE_KIND,
    DEFAULT_SAMPLE_PERIOD_S,
    EVIDENCE_KIND,
    MAX_ADMISSION_SAMPLES,
    SceneAdmissionError,
    TrajectorySceneAdmission,
    _aabb_gap,
    _inset_clearance,
    _sample_times,
    assess_spline_clearance,
    certify_continuous_clearance,
)
from Simulator.wksim_planning.ego_trajectory_adapter import (  # noqa: E402
    EgoTrajectoryAdapter,
)
from Simulator.wksim_planning.scene_profile import (  # noqa: E402
    segment_clearance,
    segment_surface_distance,
)
from Simulator.wksim_planning.trajectory_session import TrajectorySession  # noqa: E402
from Simulator.wksim_runtime.planner_scene_binding import (  # noqa: E402
    EGO_SINGLE_BOX_BINDING,
)

PROFILE = EGO_SINGLE_BOX_BINDING.profile
RADIUS = PROFILE.vehicle_radius                     # 0.35
REQUIRED = PROFILE.required_clearance               # 0.30
MARGIN = RADIUS + REQUIRED                          # float(0.35 + 0.30) == 0.6499999999999999
EXACT_MARGIN = Fraction(RADIUS) + Fraction(REQUIRED)  # exactly 13/20
OBSTACLE_MIN = PROFILE.obstacle.minimum
OBSTACLE_MAX = PROFILE.obstacle.maximum
MAP_MIN = PROFILE.map_bounds.minimum
MAP_MAX = PROFILE.map_bounds.maximum
ORDER = 3
IDENTITY = dict(run_id="run-a", mission_id="mission-a", uav_id=1,
                control_epoch="epoch-a", planner_generation=0, command_high_water=0)
MAX_ADMISSION_SAMPLES = MAX_ADMISSION_SAMPLES


# --------------------------------------------------------------------------
# spline construction
# --------------------------------------------------------------------------
def build_spline(cps, knots):
    """One EgoSpline from explicit control points and an explicit knot vector."""
    return EgoSpline(ORDER, list(knots), [tuple(float(c) for c in p) for p in cps])


def uniform_knots(cps, knot_h=0.1):
    return list(UniformBspline(ORDER, [tuple(float(c) for c in p) for p in cps], knot_h).knots)


def uniform_spline(cps, knot_h=0.1):
    return build_spline(cps, uniform_knots(cps, knot_h))


def constant_spline(point, count=7, knot_h=0.1):
    return uniform_spline([tuple(float(c) for c in point)] * count, knot_h)


def clear_cps():
    """Straight order-3 path at y=3, z=1 (clear of the obstacle, inside the map)."""
    return [(float(i) * 0.5, 3.0, 1.0) for i in range(7)]


def collision_cps():
    """Straight path at y=0, z=1 crossing the obstacle x-slab (collides)."""
    return [(float(i - 3) * 0.5, 0.0, 1.0) for i in range(7)]


WITNESS_CENTER, WITNESS_AMPLITUDE, WITNESS_KNOT_H, WITNESS_POINTS = 1.15, 0.30, 0.005, 203


def witness_cps():
    return [(WITNESS_CENTER - WITNESS_AMPLITUDE * ((-1) ** i), 0.0, 2.0)
            for i in range(WITNESS_POINTS)]


def witness_spline():
    cps = witness_cps()
    return uniform_spline(cps, WITNESS_KNOT_H)


# --------------------------------------------------------------------------
# independent exact geometry (Fractions: no float rounding at all)
# --------------------------------------------------------------------------
def exact_squared_point_box(point, box_min, box_max):
    total = Fraction(0)
    for value, low, high in zip(point, box_min, box_max):
        value, low, high = Fraction(value), Fraction(low), Fraction(high)
        if value < low:
            total += (low - value) ** 2
        elif value > high:
            total += (value - high) ** 2
    return total


def exact_obstacle_shortfall_squared(point):
    """Exact ``dist(point, obstacle)^2 - (radius + required)^2`` as a Fraction.

    Strictly negative IF AND ONLY IF the centreline point is truly closer to the
    obstacle than ``radius + required``.  Squared comparison keeps the predicate
    exact and two-directional (no irrational approximation is involved).
    """
    return exact_squared_point_box(point, OBSTACLE_MIN, OBSTACLE_MAX) - EXACT_MARGIN ** 2


def exact_obstacle_slack(point):
    """Diagnostic metre-scale lower bound on ``dist - (radius + required)``.

    A rigorous LOWER bound (integer square root bracket), so a negative value is a
    genuine intrusion, while a value near zero cannot be used as a pass proof; all
    decisions in these probes use ``exact_obstacle_shortfall_squared`` instead.
    """
    squared = exact_squared_point_box(point, OBSTACLE_MIN, OBSTACLE_MAX)
    return _exact_sqrt_upper_lower(squared) - EXACT_MARGIN


def exact_inset_slack(point):
    """Exact per-axis inset slack min_i min(c_i - lo_i, hi_i - c_i) - (radius+required)."""
    slack = None
    for value, low, high in zip(point, MAP_MIN, MAP_MAX):
        value, low, high = Fraction(value), Fraction(low), Fraction(high)
        axis = min(value - low, high - value) - EXACT_MARGIN
        slack = axis if slack is None else min(slack, axis)
    return slack


def _exact_sqrt_upper_lower(squared):
    """Exact enough: return the true sqrt as a Fraction with a tight rational bracket.

    Only used for reporting a *magnitude*; all PASS/FAIL decisions in the probes use
    squared comparisons so no irrational value is ever approximated.
    """
    if squared == 0:
        return Fraction(0)
    # Integer square root of numerator/denominator, plus a residual fraction so the
    # value is a rigorous lower bound on the true sqrt.
    num = squared.numerator
    den = squared.denominator
    root = math.isqrt(num * den)
    return Fraction(root, den)


# --------------------------------------------------------------------------
# probe bookkeeping
# --------------------------------------------------------------------------
def jsonable(value):
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return repr(value)
        return value
    if isinstance(value, Fraction):
        return f"{value.numerator}/{value.denominator}"
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


class Probe:
    """Collects deterministic named checks plus informational notes."""

    def __init__(self, probe_id, title, output_name):
        self.probe_id = probe_id
        self.title = title
        self.output_name = output_name
        self.checks = []
        self.notes = []
        self.observations = {}
        self.passed = 0
        self.failed = 0

    def check(self, ok, label, detail=None):
        ok = bool(ok)
        self.passed += int(ok)
        self.failed += int(not ok)
        self.checks.append({"check": label, "ok": ok, "detail": jsonable(detail)})
        return ok

    def note(self, text):
        self.notes.append(str(text))

    def observe(self, key, value):
        self.observations[str(key)] = jsonable(value)

    def fail(self, label, detail=None):
        self.check(False, label, detail)

    def finish(self):
        payload = {
            "probe": self.probe_id,
            "title": self.title,
            "checks_total": len(self.checks),
            "checks_passed": self.passed,
            "checks_failed": self.failed,
            "failures": [c for c in self.checks if not c["ok"]],
            "checks": self.checks,
            "observations": self.observations,
            "notes": self.notes,
        }
        path = Path(__file__).resolve().parent / self.output_name
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(jsonable(payload), handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(f"{self.probe_id}: {self.passed}/{len(self.checks)} checks passed"
              f" ({self.failed} failed) -> {self.output_name}")
        for failure in payload["failures"][:10]:
            print(f"  FAIL {failure['check']} :: {failure['detail']}")
        return self.failed


def attempt(callable_obj, *args, **kwargs):
    """Return (value, None) or (None, exception) without letting anything escape."""
    try:
        return callable_obj(*args, **kwargs), None
    except Exception as error:  # noqa: BLE001 - probes must record, not crash
        return None, error


# --------------------------------------------------------------------------
# adapter / session harness (unit-level atomicity)
# --------------------------------------------------------------------------
def make_session_adapter():
    session = TrajectorySession(dict(IDENTITY))
    adapter = EgoTrajectoryAdapter(session)
    return session, adapter


def session_snapshot(session):
    return {
        "state": session.state,
        "generation": session.generation,
        "last_event_sequence": session.last_event_sequence,
        "last_command_id": session.last_command_id,
        "identity": [session.identity.run_id, session.identity.mission_id,
                     session.identity.uav_id, session.identity.control_epoch,
                     session.identity.planner_generation],
    }


def make_mapping(cps, *, traj_id=1, start_time_ns=0, knot_h=0.1):
    return {
        "drone_id": 0,
        "order": ORDER,
        "traj_id": traj_id,
        "start_time": start_time_ns,
        "knots": uniform_knots(cps, knot_h),
        "pos_pts": [tuple(float(c) for c in p) for p in cps],
        "yaw_pts": [],
        "yaw_dt": 0.0,
    }


def count_adapter_calls(adapter):
    """Wrap replan_and_activate so probes can count and still run the real call."""
    calls = []
    original = adapter.replan_and_activate

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    adapter.replan_and_activate = spy
    return calls


__all__ = [
    "CONTINUOUS_EVIDENCE_KIND", "DEFAULT_SAMPLE_PERIOD_S", "EVIDENCE_KIND", "EXACT_MARGIN",
    "IDENTITY", "MAP_MAX", "MAP_MIN", "MAX_ADMISSION_SAMPLES", "MARGIN", "OBSTACLE_MAX",
    "OBSTACLE_MIN", "ORDER", "PROFILE", "Probe", "RADIUS", "REPO_ROOT", "REQUIRED",
    "SceneAdmissionError", "SplineError", "TrajectorySceneAdmission", "WITNESS_AMPLITUDE",
    "WITNESS_CENTER", "WITNESS_KNOT_H", "WITNESS_POINTS", "_aabb_gap", "_inset_clearance",
    "_sample_times", "assess_spline_clearance", "attempt", "build_spline", "certify_continuous_clearance",
    "clear_cps", "collision_cps", "constant_spline", "count_adapter_calls", "exact_inset_slack",
    "exact_obstacle_shortfall_squared", "exact_obstacle_slack", "exact_squared_point_box",
    "make_mapping", "make_session_adapter",
    "segment_clearance", "segment_surface_distance", "session_snapshot", "uniform_knots",
    "uniform_spline", "witness_cps", "witness_spline",
]
