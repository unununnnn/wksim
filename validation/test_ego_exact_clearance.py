"""Independent tests for the candidate exact clearance certificate.

Covers, without importing the audit probe or the module's private helpers:

* representation invariance (R1): one exactly fixed geometric curve built at
  9/13/17/21/33/65 control points and an exact Boehm knot-refinement sequence
  must produce one verdict inside a declared 2*t band;
* the committed recorded EGO payload: bracket near its true clearance and
  strictly tighter than the committed certificate's 0.377 net result;
* soundness: unsafe / intersecting paths are never admitted;
* the near-threshold 2*t band fails closed;
* malformed and non-finite inputs, exhausted work caps, determinism, obstacle
  versus map binding, and a high-resolution independent critic cross-check over
  a fixed case set;
* the Lipschitz premise itself: the reported per-span speed bounds must dominate
  a dense absolute-parameter evaluation of ||gamma'(u)||;
* knot-vector translation: ordinary +1/+4/+10 s shifts keep the verdict and
  must never admit the +1 s corner-dip witness; translations whose speed-scaled
  ULP exceeds the declared FLOAT_GUARD_M envelope fail closed and are not
  claimed invariant;
* adjacent-float (1-ulp) knot spans are never admitted (exact-rational critic);
* finite overflow: ±1e308 / tiny-interval geometry and huge private-state
  integers return a certificate, never an exception;
* early-exit / work-cap certificates leave global bounds null under a documented
  partial scope;
* candidate-only wiring: the committed admission gate and pump must not import
  or reference this module.

Run from the repository root, on either platform:

    python -m pytest validation/test_ego_exact_clearance.py -q
    python -m unittest validation.test_ego_exact_clearance -v

The ``DenseCritic`` below is an INDEPENDENT sampling estimator: its numbers are
estimates and are never used to certify anything.  It only falsifies -- a
certified admission contradicted by the critic is a defect.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import math
import os
import sys
import unittest
from fractions import Fraction

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from Simulator.wksim_planning.ego_evaluator import EgoSpline, UniformBspline  # noqa: E402
from Simulator.wksim_planning.ego_exact_clearance import (  # noqa: E402
    BINDING_OBJECT_MAP_INSET,
    BINDING_OBJECT_OBSTACLE,
    BOUNDS_SCOPE_CURVE,
    BOUNDS_SCOPE_PARTIAL,
    CANDIDATE_STATUS,
    CERTIFICATE_REASONS,
    DEFAULT_TOLERANCE_M,
    EVIDENCE_KIND,
    FLOAT_GUARD_M,
    MAX_TOLERANCE_M,
    REASON_BAND,
    REASON_DOMAIN,
    REASON_KNOTS,
    REASON_MAP,
    REASON_OBSTACLE,
    REASON_ROUNDOFF,
    REASON_STRUCTURE,
    REASON_WORK_CAP,
    STATUS_ADMITTED,
    STATUS_INDETERMINATE,
    STATUS_REJECTED,
    ExactClearanceError,
    certify_exact_clearance,
)
from Simulator.wksim_planning.ego_scene_admission import (  # noqa: E402
    assess_spline_clearance,
    certify_continuous_clearance,
)
from Simulator.wksim_runtime.planner_scene_binding import EGO_SINGLE_BOX_BINDING  # noqa: E402

PROFILE = EGO_SINGLE_BOX_BINDING.profile
OBSTACLE_MIN = PROFILE.obstacle.minimum
OBSTACLE_MAX = PROFILE.obstacle.maximum
MAP_MIN = PROFILE.map_bounds.minimum
MAP_MAX = PROFILE.map_bounds.maximum
RADIUS = PROFILE.vehicle_radius
REQUIRED = PROFILE.required_clearance
TOLERANCE = DEFAULT_TOLERANCE_M

RECORDED_PAYLOAD_PATH = os.path.join(
    REPO_ROOT, "validation", "ego-planner-static-20260912-02", "bspline.json")
RECORDED_PAYLOAD_SHA256 = "d4d318cc99cc55460a5de229881f8c83bbd032a7c97fd80f7f603ca4e2684447"
# Values independently reproduced by validation/coordination/deepseek-g3-strict-gate-20260914-01/
RECORDED_PAYLOAD_DENSE_TRUE_NET = 0.9971917383329542
COMMITTED_CERTIFICATE_NET = 0.37725020658857944
COMMITTED_CERTIFICATE_GAP = 0.7272502065885794
RECORDED_PAYLOAD_SAMPLED_NET = 0.9971919183081722
AUDIT_FAMILY_TRUE_NET = 0.8696328198877233   # converged dense value of the fixed curve


# --------------------------------------------------------------------------
# independent estimator (NEVER a certificate)
# --------------------------------------------------------------------------
def pbox(point, low, high):
    """Independent point-to-AABB distance (own implementation)."""
    total = 0.0
    for value, lo, hi in zip(point, low, high):
        if value < lo:
            total += (lo - value) ** 2
        elif value > hi:
            total += (value - hi) ** 2
    return math.sqrt(total)


def pmap(point, low, high):
    """Independent signed inward distance to the nearest map face."""
    return min(min(value - lo, hi - value) for value, lo, hi in zip(point, low, high))


class DenseCritic:
    """Sampling estimator over a fixed uniform grid (estimate, not proof)."""

    def __init__(self, spline, samples=40001):
        self.samples = samples
        duration = spline.duration
        step = duration / samples
        obstacle = math.inf
        inset = math.inf
        points = []
        for index in range(samples + 1):
            t = duration * index / samples
            point = spline.position_at(t)
            points.append(point)
            obstacle = min(obstacle, pbox(point, OBSTACLE_MIN, OBSTACLE_MAX))
            inset = min(inset, pmap(point, MAP_MIN, MAP_MAX))
        self.step = step
        self.obstacle_net = obstacle - RADIUS
        self.inset_net = inset - RADIUS
        # Crude (heuristic, non-certified) speed estimate for the critic's own
        # sampling slack, computed from the sampled positions themselves.
        speed = 0.0
        for first, second in zip(points, points[1:]):
            delta = math.dist(first, second)
            if delta > speed:
                speed = delta
        self.speed = speed / step if step > 0 else 0.0

    @property
    def slack(self):
        """One-sided sampling slack of this estimator (metres)."""
        return self.speed * self.step / 2.0

    def lower_bound_estimate(self):
        return self.obstacle_net - self.slack


# --------------------------------------------------------------------------
# fixed curve family (exactly one geometry, many representations)
# --------------------------------------------------------------------------
FAMILY = {"x_start": -2.0, "x_end": 2.5, "apex_u": -0.2, "apex_height": 3.0,
          "curvature": 0.45, "z": 3.0, "duration_s": 3.0}
FAMILY_DENSITIES = (9, 13, 17, 21, 33, 65)


def family_path(t):
    speed = (FAMILY["x_end"] - FAMILY["x_start"]) / FAMILY["duration_s"]
    x = FAMILY["x_start"] + speed * t
    y = FAMILY["apex_height"] - FAMILY["curvature"] * (x - FAMILY["apex_u"]) ** 2
    return (x, y, FAMILY["z"])


def family_knots(density):
    h = FAMILY["duration_s"] / (density - 3)
    return [(index - 3) * h for index in range(density + 4)]


def family_control_points(density):
    """Exact blossom (Oslo) control points: reproduces family_path identically."""
    h = FAMILY["duration_s"] / (density - 3)
    speed = (FAMILY["x_end"] - FAMILY["x_start"]) / FAMILY["duration_s"]
    offset = FAMILY["x_start"] - FAMILY["apex_u"]
    c2 = -FAMILY["curvature"] * speed * speed
    c1 = -2.0 * FAMILY["curvature"] * offset * speed
    c0 = FAMILY["apex_height"] - FAMILY["curvature"] * offset * offset
    points = []
    for index in range(density):
        e1 = (3 * index - 3) * h
        e2 = ((index - 2) * (index - 1) + (index - 1) * index
              + (index - 2) * index) * h * h
        points.append((FAMILY["x_start"] + speed * e1 / 3.0,
                       c0 + c1 * e1 / 3.0 + c2 * e2 / 3.0,
                       FAMILY["z"]))
    return points


def family_spline(density):
    return EgoSpline(3, family_knots(density), family_control_points(density))


def family_deviation(spline, samples=2001):
    worst = 0.0
    for index in range(samples + 1):
        t = FAMILY["duration_s"] * index / samples
        actual = spline.position_at(t)
        expected = family_path(t)
        worst = max(worst, max(abs(a - b) for a, b in zip(actual, expected)))
    return worst


def boehm_insert(spline, u):
    """Exact knot insertion at an in-domain knot value (independent implementation)."""
    order = spline.position.order
    knots = list(spline.position.knots)
    points = list(spline.position._points)
    count = len(points) - 1
    span = max(index for index in range(len(knots) - 1) if knots[index] <= u)
    if not order <= span <= count:
        raise ValueError("knot insertion must be inside the certified domain")
    inserted = []
    for index in range(count + 2):
        if index <= span - order:
            inserted.append(points[index])
        elif index >= span + 1:
            inserted.append(points[index - 1])
        else:
            alpha = (u - knots[index]) / (knots[index + order] - knots[index])
            inserted.append(tuple(
                alpha * points[index][axis] + (1.0 - alpha) * points[index - 1][axis]
                for axis in range(3)))
    return EgoSpline(order, knots[:span + 1] + [u] + knots[span + 1:], inserted)


def refined_sequence(steps=6):
    """(control_points, spline) sequence produced by exact Boehm refinement."""
    spline = family_spline(9)
    sequence = [(len(spline.position._points), spline)]
    for _ in range(steps):
        knots = list(spline.position.knots)
        count = len(spline.position._points) - 1
        mids = [(knots[index] + knots[index + 1]) / 2.0
                for index in range(3, count) if knots[index + 1] > knots[index]]
        for mid in mids:
            spline = boehm_insert(spline, mid)
        sequence.append((len(spline.position._points), spline))
    return sequence


# --------------------------------------------------------------------------
# fixed straight-line and witness fixtures
# --------------------------------------------------------------------------
def line_spline(y, *, count=5, x_start=-3.0, x_end=3.0, z=3.0, duration=1.0):
    """Straight-line spline; the curve reproduces the line exactly on the domain."""
    h = duration / (count - 3)
    knots = [(index - 3) * h for index in range(count + 4)]
    points = [(x_start + (x_end - x_start) * index / (count - 1), y, z)
              for index in range(count)]
    return EgoSpline(3, knots, points)


def line_at_net(net_clearance, **kwargs):
    """Line parallel to the obstacle's +y face whose net clearance is requested."""
    return line_spline(OBSTACLE_MAX[1] + RADIUS + net_clearance, **kwargs)


def alternating_witness():
    """The G3 seal's alternating-control-point witness (net ~0.20 m, unsafe)."""
    points = [(1.15 - 0.30 * ((-1) ** index), 0.0, 2.0) for index in range(203)]
    return EgoSpline(3, list(UniformBspline(3, points, 0.005).knots), points)


def corner_dip_witness():
    """A curve that dips into the obstacle's +x/+y corner region (unsafe)."""
    points = [(-3.0, 3.0, 3.0), (-1.0, 2.2, 3.0), (0.2, 0.6, 3.0),
              (1.4, 0.2, 3.0), (3.0, 2.0, 3.0), (4.0, 3.0, 3.0)]
    knots = list(UniformBspline(3, points, 0.4).knots)
    return EgoSpline(3, knots, points)


def shift_knots(spline, delta):
    """Translate every knot by ``delta``; the geometric image is unchanged."""
    knots = [value + delta for value in spline.position.knots]
    return EgoSpline(3, knots, list(spline.position._points))


COLLAPSE_POINTS = [
    (0.0, 4.0, 3.0), (0.0, 4.0, 3.0), (0.0, -4.0, 3.0), (0.0, -4.0, 3.0),
    (0.0, 4.0, 3.0), (0.0, 4.0, 3.0), (0.0, 4.0, 3.0), (0.0, 4.0, 3.0),
]


def adjacent_float_knots(start, spacings, count=12):
    """Strictly increasing knots spaced by ``spacings`` ulps from ``start``."""
    knots = [float(start)]
    for _ in range(count - 1):
        value = knots[-1]
        for _ in range(spacings):
            value = math.nextafter(value, math.inf)
        knots.append(value)
    return knots


def adjacent_float_spline(start, spacings=1):
    return EgoSpline(3, adjacent_float_knots(start, spacings), COLLAPSE_POINTS)


def _deboor_frac(knots, points, order, u):
    fknots = [Fraction(value) for value in knots]
    fpoints = [[Fraction(coordinate) for coordinate in point] for point in points]
    fu = Fraction(u)
    count = len(points) - 1
    low, high = fknots[order], fknots[count + 1]
    ub = low if fu < low else (high if fu > high else fu)
    span = order
    while span < count and not (fknots[span + 1] >= ub):
        span += 1
    work = [list(fpoints[span - order + index]) for index in range(order + 1)]
    for level in range(1, order + 1):
        for index in range(order, level - 1, -1):
            left = fknots[index + span - order]
            right = fknots[index + 1 + span - level]
            alpha = (ub - left) / (right - left)
            lower, upper = work[index - 1], work[index]
            work[index] = [(1 - alpha) * lower[axis] + alpha * upper[axis]
                           for axis in range(len(upper))]
    return tuple(work[order])


def _box_distance_frac(point, low=OBSTACLE_MIN, high=OBSTACLE_MAX):
    total = Fraction(0)
    for value, lo, hi in zip(point, low, high):
        flo, fhi = Fraction(lo), Fraction(hi)
        if value < flo:
            total += (flo - value) ** 2
        elif value > fhi:
            total += (value - fhi) ** 2
    return math.sqrt(float(total))


def exact_rational_net_clearance(spline, span_indices=(3, 5), samples=400):
    """Independent Fraction de Boor net obstacle clearance on selected spans."""
    knots = list(spline.position.knots)
    points = list(spline.position._points)
    best = math.inf
    for span_index in span_indices:
        left, right = Fraction(knots[span_index]), Fraction(knots[span_index + 1])
        for index in range(samples + 1):
            u = left + (right - left) * index / samples
            value = _box_distance_frac(_deboor_frac(knots, points, 3, u)) - RADIUS
            if value < best:
                best = value
    return best


def overflow_opposite_controls(magnitude=1e308, interval=1e-8):
    """Finite controls whose derivative norms overflow (P1 witness)."""
    points = [
        (magnitude, 0.0, 3.0),
        (-magnitude, 0.0, 3.0),
        (magnitude, 0.0, 3.0),
        (-magnitude, 0.0, 3.0),
        (0.0, 4.0, 3.0),
    ]
    knots = list(UniformBspline(3, points, interval).knots)
    return EgoSpline(3, knots, points)


def recorded_payload_spline():
    with open(RECORDED_PAYLOAD_PATH, encoding="utf-8") as handle:
        payload = json.load(handle)["payload"]
    return EgoSpline(3, payload["knots"], [tuple(point) for point in payload["pos_pts"]])


def fixed_critic_cases():
    """Deterministic case set used for the false-admission cross-check."""
    cases = [("family-%d" % density, family_spline(density)) for density in FAMILY_DENSITIES]
    cases.extend([
        ("recorded-payload", recorded_payload_spline()),
        ("line-safe-far", line_spline(4.0)),
        ("line-obstacle-binding", line_at_net(REQUIRED + 0.10)),
        ("line-map-binding", line_spline(5.34)),
        ("line-map-unsafe", line_spline(5.36)),
        ("line-band-exact", line_at_net(REQUIRED)),
        ("line-unsafe-close", line_at_net(REQUIRED - 0.05)),
        ("line-unsafe-surface", line_spline(OBSTACLE_MAX[1])),
        ("line-through-box", line_spline(0.5 * (OBSTACLE_MIN[1] + OBSTACLE_MAX[1]))),
        ("alternating-witness", alternating_witness()),
        ("corner-dip", corner_dip_witness()),
        ("corner-dip-shift-1s", shift_knots(corner_dip_witness(), 1.0)),
        ("family-13-shift-4s", shift_knots(family_spline(13), 4.0)),
    ])
    return cases


# --------------------------------------------------------------------------
class RepresentationInvarianceTests(unittest.TestCase):
    """R1: the verdict must be a function of the curve, not of its representation."""

    def test_six_densities_are_the_same_curve_and_share_one_verdict(self):
        deviations = []
        statuses = set()
        brackets = []
        for density in FAMILY_DENSITIES:
            spline = family_spline(density)
            deviations.append(family_deviation(spline))
            certificate = certify_exact_clearance(spline)
            statuses.add(certificate.status)
            self.assertTrue(certificate.tolerance_met,
                            "density %d did not close its bracket" % density)
            self.assertTrue(certificate.admitted, "density %d was not admitted" % density)
            brackets.append((certificate.obstacle_clearance_lower,
                             certificate.obstacle_clearance_upper))
        self.assertLessEqual(max(deviations), 1e-12,
                             "the six representations are not the same curve")
        self.assertEqual(statuses, {STATUS_ADMITTED},
                         "the candidate verdict is representation-dependent: %r" % (statuses,))
        for lower, upper in brackets:
            self.assertLessEqual(lower, AUDIT_FAMILY_TRUE_NET)
            self.assertGreaterEqual(upper, AUDIT_FAMILY_TRUE_NET - 1e-12)
            self.assertLessEqual(upper - lower, TOLERANCE * (1.0 + 1e-9))

    def test_exact_boehm_refinement_keeps_the_candidate_verdict(self):
        sequence = refined_sequence(steps=6)
        counts = [count for count, _ in sequence]
        self.assertEqual(counts[0], 9)
        self.assertGreater(counts[-1], 300, "refinement did not reach a dense representation")
        for count, spline in sequence:
            self.assertLessEqual(family_deviation(spline, samples=801), 1e-12,
                                 "refinement at %d controls changed the curve" % count)
            certificate = certify_exact_clearance(spline)
            self.assertEqual(certificate.status, STATUS_ADMITTED,
                             "refinement to %d controls changed the verdict" % count)
            self.assertTrue(certificate.tolerance_met)

    def test_committed_predicate_is_representation_dependent_at_this_head(self):
        """Characterization of the committed gate at HEAD (owner decision pending).

        This is the contrast that motivates the candidate.  It must be revisited
        when the owner promotes an exact predicate into the default gate.
        """
        verdicts = []
        for density in (9, 13, 21, 33):
            verdicts.append(certify_continuous_clearance(family_spline(density)).proven)
        self.assertEqual(verdicts, [False, False, False, True],
                         "committed strict-gate characterization changed: %r" % (verdicts,))
        candidate = [certify_exact_clearance(family_spline(density)).status
                     for density in (9, 13, 21, 33)]
        self.assertEqual(set(candidate), {STATUS_ADMITTED})


class RecordedPayloadTests(unittest.TestCase):
    """The committed recorded planner payload."""

    def setUp(self):
        with open(RECORDED_PAYLOAD_PATH, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        self.assertEqual(digest, RECORDED_PAYLOAD_SHA256,
                         "the recorded payload artifact changed")
        self.spline = recorded_payload_spline()

    def test_bracket_contains_the_true_clearance_and_is_tighter_than_the_committed_net(self):
        certificate = certify_exact_clearance(self.spline)
        self.assertEqual(certificate.status, STATUS_ADMITTED)
        self.assertTrue(certificate.tolerance_met)
        lower = certificate.obstacle_clearance_lower
        upper = certificate.obstacle_clearance_upper
        self.assertLessEqual(lower, RECORDED_PAYLOAD_DENSE_TRUE_NET)
        self.assertGreaterEqual(upper, RECORDED_PAYLOAD_DENSE_TRUE_NET - 1e-12)
        self.assertLessEqual(upper - lower, TOLERANCE * (1.0 + 1e-9))
        self.assertGreater(lower, COMMITTED_CERTIFICATE_NET + 0.5,
                           "the candidate bracket is not strictly tighter than the committed net")
        audit = DenseCritic(self.spline, samples=20001)
        self.assertGreaterEqual(audit.obstacle_net, lower,
                                "the critic contradicts the certified lower bound")

    def test_committed_predicate_values_are_unchanged(self):
        legacy = assess_spline_clearance(self.spline, strict_continuous=False)
        strict = assess_spline_clearance(self.spline)
        self.assertAlmostEqual(legacy.min_obstacle_clearance, RECORDED_PAYLOAD_SAMPLED_NET, places=15)
        self.assertAlmostEqual(strict.continuous_certificate.obstacle_hull_gap,
                               COMMITTED_CERTIFICATE_GAP, places=12)
        self.assertAlmostEqual(strict.continuous_certificate.min_net_obstacle_clearance,
                               COMMITTED_CERTIFICATE_NET, places=12)

    def test_candidate_and_committed_disagree_only_by_conservatism(self):
        certificate = certify_exact_clearance(self.spline)
        committed = certify_continuous_clearance(self.spline)
        self.assertTrue(committed.proven, "the committed gate no longer admits the payload")
        self.assertGreater(certificate.obstacle_clearance_lower,
                           committed.min_net_obstacle_clearance)


class ThresholdBandTests(unittest.TestCase):
    """The declared 2*t band must fail closed and must not leak outside."""

    def _status(self, delta, tolerance=TOLERANCE):
        certificate = certify_exact_clearance(line_at_net(REQUIRED + delta),
                                              tolerance_m=tolerance)
        return certificate

    def test_tolerance_default_and_bounds(self):
        self.assertEqual(DEFAULT_TOLERANCE_M, 1e-3)
        self.assertLessEqual(MAX_TOLERANCE_M, 0.1)

    def test_band_fails_closed_and_outside_band_is_decided(self):
        for delta, expected in ((-3.0 * TOLERANCE, STATUS_REJECTED),
                                (-0.5 * TOLERANCE, STATUS_REJECTED),
                                (0.0, STATUS_INDETERMINATE),
                                (0.5 * TOLERANCE, STATUS_INDETERMINATE),
                                (3.0 * TOLERANCE, STATUS_ADMITTED)):
            with self.subTest(delta=delta):
                certificate = self._status(delta)
                self.assertEqual(certificate.status, expected,
                                 "delta=%r gave %s (%s)" % (delta, certificate.status,
                                                            certificate.reason))
                self.assertEqual(certificate.admitted, expected == STATUS_ADMITTED)
                if expected == STATUS_INDETERMINATE:
                    self.assertEqual(certificate.reason, REASON_BAND)

    def test_band_scales_with_the_declared_tolerance(self):
        for tolerance in (1e-3, 2e-3, 1e-2):
            with self.subTest(tolerance=tolerance):
                in_band = certify_exact_clearance(line_at_net(REQUIRED + 0.5 * tolerance),
                                                  tolerance_m=tolerance)
                outside = certify_exact_clearance(line_at_net(REQUIRED + 3.0 * tolerance),
                                                  tolerance_m=tolerance)
                self.assertEqual(in_band.status, STATUS_INDETERMINATE)
                self.assertEqual(outside.status, STATUS_ADMITTED)
                self.assertLessEqual(outside.obstacle_clearance_upper
                                     - outside.obstacle_clearance_lower,
                                     tolerance * (1.0 + 1e-9))

    def test_band_never_admits_below_required(self):
        for delta in (-0.9 * TOLERANCE, -0.5 * TOLERANCE, -0.1 * TOLERANCE):
            certificate = certify_exact_clearance(line_at_net(REQUIRED + delta))
            self.assertFalse(certificate.admitted)
            self.assertIn(certificate.status, (STATUS_REJECTED, STATUS_INDETERMINATE))


class SafetyTests(unittest.TestCase):
    """Unsafe or intersecting curves must never be admitted."""

    def test_intersecting_and_unsafe_cases_are_never_admitted(self):
        cases = [
            ("line-through-box", line_spline(0.5 * (OBSTACLE_MIN[1] + OBSTACLE_MAX[1]))),
            ("line-on-obstacle-surface", line_spline(OBSTACLE_MAX[1])),
            ("line-net-minus-0.05", line_at_net(REQUIRED - 0.05)),
            ("line-net-minus-0.25", line_at_net(REQUIRED - 0.25)),
            ("alternating-witness", alternating_witness()),
            ("corner-dip", corner_dip_witness()),
            ("corner-dip-shift-1s", shift_knots(corner_dip_witness(), 1.0)),
        ]
        for name, spline in cases:
            with self.subTest(case=name):
                certificate = certify_exact_clearance(spline)
                self.assertFalse(certificate.admitted, "%s was admitted" % name)
                self.assertIn(certificate.status, (STATUS_REJECTED, STATUS_INDETERMINATE))
                critic = DenseCritic(spline, samples=20001)
                self.assertLess(critic.obstacle_net, REQUIRED,
                                "%s is actually safe; the fixture is wrong" % name)

    def test_safe_curve_just_inside_the_band_is_not_admitted_but_safe_curve_is(self):
        unsafe = certify_exact_clearance(line_at_net(REQUIRED - 0.5 * TOLERANCE))
        safe = certify_exact_clearance(line_at_net(REQUIRED + 0.5))
        self.assertFalse(unsafe.admitted)
        self.assertTrue(safe.admitted)
        self.assertGreaterEqual(safe.obstacle_clearance_lower, REQUIRED)

    def test_admitted_curves_always_have_a_certified_lower_bound_above_required(self):
        for name, spline in fixed_critic_cases():
            with self.subTest(case=name):
                certificate = certify_exact_clearance(spline)
                if certificate.admitted:
                    self.assertGreaterEqual(certificate.obstacle_clearance_lower, REQUIRED)
                    self.assertGreaterEqual(certificate.map_inset_clearance_lower, REQUIRED)
                    self.assertTrue(certificate.tolerance_met)


class KnotTranslationTests(unittest.TestCase):
    """Ordinary knot translations inside the declared parameter-roundoff envelope."""

    def test_plus_one_second_corner_dip_is_never_admitted(self):
        for delta in (0.0, 1.0, 5.0, 10.0):
            spline = shift_knots(corner_dip_witness(), delta)
            with self.subTest(delta=delta):
                certificate = certify_exact_clearance(spline)
                self.assertFalse(certificate.admitted)
                self.assertEqual(certificate.status, STATUS_REJECTED)
                self.assertEqual(certificate.reason, REASON_OBSTACLE)
                critic = DenseCritic(spline, samples=8001)
                self.assertLess(critic.obstacle_net, REQUIRED)

    def test_knot_vector_translation_preserves_verdict_and_bounds(self):
        cases = [
            ("family-13", family_spline(13)),
            ("family-33", family_spline(33)),
            ("line-safe", line_spline(3.0)),
            ("line-unsafe", line_at_net(REQUIRED - 0.05)),
            ("corner-dip", corner_dip_witness()),
        ]
        for name, spline in cases:
            base = certify_exact_clearance(spline)
            for delta in (1.0, 4.0, 10.0):
                with self.subTest(case=name, delta=delta):
                    shifted = certify_exact_clearance(shift_knots(spline, delta))
                    self.assertEqual(shifted.status, base.status)
                    self.assertEqual(shifted.admitted, base.admitted)
                    self.assertEqual(shifted.reason, base.reason)
                    if base.obstacle_clearance_lower is None:
                        self.assertIsNone(shifted.obstacle_clearance_lower)
                        continue
                    self.assertAlmostEqual(
                        shifted.obstacle_clearance_lower,
                        base.obstacle_clearance_lower, places=9)
                    self.assertAlmostEqual(
                        shifted.obstacle_clearance_upper,
                        base.obstacle_clearance_upper, places=9)
                    self.assertAlmostEqual(
                        shifted.map_inset_clearance_lower,
                        base.map_inset_clearance_lower, places=9)
                    self.assertAlmostEqual(
                        shifted.map_inset_clearance_upper,
                        base.map_inset_clearance_upper, places=9)

    def test_shifted_safe_family_lower_does_not_exceed_true(self):
        spline = shift_knots(family_spline(13), 4.0)
        certificate = certify_exact_clearance(spline)
        self.assertTrue(certificate.admitted)
        critic = DenseCritic(spline, samples=20001)
        self.assertLessEqual(certificate.obstacle_clearance_lower, critic.obstacle_net + 1e-9)
        self.assertLessEqual(certificate.obstacle_clearance_lower, AUDIT_FAMILY_TRUE_NET + 1e-9)


class OverflowArithmeticTests(unittest.TestCase):
    """P1: finite overflow must return a certificate, never raise, never admit."""

    def _assert_fail_closed(self, spline, *, cap=64):
        certificate = certify_exact_clearance(spline)
        self.assertFalse(certificate.admitted)
        self.assertIn(certificate.status, (STATUS_REJECTED, STATUS_INDETERMINATE))
        self.assertIn(certificate.reason, CERTIFICATE_REASONS)
        self.assertLessEqual(certificate.evaluations, cap)
        self.assertLessEqual(certificate.nodes, cap)
        encoded = json.dumps(certificate.to_dict(), allow_nan=False, sort_keys=True)
        self.assertTrue(encoded)

    def test_plus_minus_1e308_tiny_interval_returns_certificate(self):
        for magnitude in (1e308, -1e308):
            with self.subTest(magnitude=magnitude):
                self._assert_fail_closed(overflow_opposite_controls(magnitude, 1e-8))

    def test_tiny_interval_and_huge_opposite_controls_do_not_raise(self):
        for interval in (1e-8, 1e-12, 1e-16):
            with self.subTest(interval=interval):
                self._assert_fail_closed(overflow_opposite_controls(1e308, interval))

    def test_overflow_certificate_is_deterministic(self):
        first = certify_exact_clearance(overflow_opposite_controls())
        second = certify_exact_clearance(overflow_opposite_controls())
        self.assertEqual(json.dumps(first.to_dict(), sort_keys=True, allow_nan=False),
                         json.dumps(second.to_dict(), sort_keys=True, allow_nan=False))

    def test_huge_private_int_state_returns_certificate(self):
        for label, mutate in (
                ("knot", lambda spline: setattr(
                    spline.position, "_knots",
                    list(spline.position._knots)[:6] + [10 ** 400] + list(spline.position._knots)[7:])),
                ("point", lambda spline: setattr(
                    spline.position, "_points",
                    list(spline.position._points)[:5] + [(10 ** 400, 0.0, 3.0)]
                    + list(spline.position._points)[6:])),
        ):
            with self.subTest(case=label):
                spline = family_spline(13)
                mutate(spline)
                certificate = certify_exact_clearance(spline)
                self.assertFalse(certificate.admitted)
                self.assertEqual(certificate.status, STATUS_REJECTED)
                self.assertEqual(certificate.reason, REASON_STRUCTURE)
                self.assertEqual(certificate.evaluations, 0)


class AdjacentFloatSpanTests(unittest.TestCase):
    """Adjacent-float spans fail closed before evaluate(); no fabricated brackets."""

    COORDINATOR_STARTS = (1.0, 1000.0, 1e6)
    ALL_STARTS = (1.0, 1000.0, 1e6, 1e15)
    ALL_SPACINGS = (1, 2, 4, 8)

    def _assert_empty_fail_closed(self, certificate, *, reasons):
        self.assertFalse(certificate.admitted)
        self.assertIn(certificate.status, (STATUS_REJECTED, STATUS_INDETERMINATE))
        self.assertIn(certificate.reason, reasons)
        self.assertEqual(certificate.evaluations, 0)
        self.assertEqual(certificate.nodes, 0)
        self.assertEqual(certificate.evaluated_span_count, 0)
        self.assertEqual(certificate.spans, ())
        self.assertIsNone(certificate.bounds_scope)
        self.assertIsNone(certificate.obstacle_clearance_lower)
        self.assertIsNone(certificate.obstacle_clearance_upper)
        self.assertIsNone(certificate.map_inset_clearance_lower)
        self.assertIsNone(certificate.map_inset_clearance_upper)
        self.assertIsNone(certificate.binding_object)
        self.assertIsNone(certificate.binding_span_index)
        for span in certificate.spans:
            self.fail("fabricated span %r" % (span,))

    def test_one_ulp_false_admission_witness_is_rejected_at_map_and_shifted_starts(self):
        import Simulator.wksim_planning.ego_exact_clearance as module
        source = inspect.getsource(module)
        self.assertNotIn("peak_prepared_speed", source)
        self.assertNotIn("charge one evaluation", source)
        self.assertNotIn("inspectable evidence", source)
        self.assertNotIn("> 1e6", source)
        for start in self.ALL_STARTS:
            with self.subTest(start=start, spacings=1):
                spline = adjacent_float_spline(start, 1)
                if start != 1e15:
                    exact_net = exact_rational_net_clearance(spline)
                    self.assertLess(exact_net, REQUIRED - 1e-6)
                certificate = certify_exact_clearance(spline)
                self._assert_empty_fail_closed(certificate, reasons=(REASON_STRUCTURE,))
                self.assertEqual(certificate.status, STATUS_REJECTED)

    def test_wider_than_one_ulp_collapse_witness_is_not_admitted(self):
        reasons = set()
        for start in self.ALL_STARTS:
            for spacings in self.ALL_SPACINGS:
                with self.subTest(start=start, spacings=spacings):
                    spline = adjacent_float_spline(start, spacings)
                    certificate = certify_exact_clearance(spline)
                    knots = list(spline.position.knots)
                    mid = knots[3] + 0.5 * (knots[4] - knots[3])
                    mid_ok = knots[3] < mid < knots[4]
                    expected = (REASON_STRUCTURE,) if not mid_ok else (REASON_ROUNDOFF,)
                    self._assert_empty_fail_closed(certificate, reasons=expected)
                    reasons.add(certificate.reason)
        self.assertTrue(reasons <= {REASON_STRUCTURE, REASON_ROUNDOFF})
        for start in self.COORDINATOR_STARTS:
            for spacings in self.ALL_SPACINGS:
                certificate = certify_exact_clearance(adjacent_float_spline(start, spacings))
                self.assertEqual(certificate.evaluations, 0)
                self.assertEqual(len(certificate.spans), 0)


class ParameterRoundoffEnvelopeTests(unittest.TestCase):
    """F2: documented speed-scaled ULP envelope; no admission outside it."""

    def test_ordinary_and_one_million_second_family_shifts_stay_inside_the_envelope(self):
        base = certify_exact_clearance(family_spline(13))
        self.assertTrue(base.admitted)
        for delta in (1.0, 4.0, 1e6):
            with self.subTest(delta=delta):
                certificate = certify_exact_clearance(shift_knots(family_spline(13), delta))
                self.assertTrue(certificate.admitted)
                self.assertEqual(certificate.status, STATUS_ADMITTED)
                self.assertEqual(certificate.bounds_scope, BOUNDS_SCOPE_CURVE)

    def test_large_translation_exhausts_the_envelope_deterministically(self):
        outcomes = []
        for delta in (1e7, 1e12, 1e15):
            with self.subTest(delta=delta):
                first = certify_exact_clearance(shift_knots(family_spline(13), delta))
                second = certify_exact_clearance(shift_knots(family_spline(13), delta))
                self.assertFalse(first.admitted)
                self.assertEqual(first.status, STATUS_INDETERMINATE)
                self.assertEqual(first.reason, REASON_ROUNDOFF)
                self.assertEqual(first.evaluations, 0)
                self.assertEqual(first.spans, ())
                self.assertEqual(json.dumps(first.to_dict(), sort_keys=True, allow_nan=False),
                                 json.dumps(second.to_dict(), sort_keys=True, allow_nan=False))
                outcomes.append(first.reason)
        self.assertEqual(set(outcomes), {REASON_ROUNDOFF})


class PartialBoundsScopeTests(unittest.TestCase):
    """F3: unfinished evaluation never publishes partial extrema as global bounds."""

    def test_default_caps_finish_every_span_and_publish_curve_scope(self):
        for name, spline in (("family-13", family_spline(13)),
                             ("alternating", alternating_witness()),
                             ("corner-dip", corner_dip_witness())):
            with self.subTest(case=name):
                certificate = certify_exact_clearance(spline)
                self.assertEqual(certificate.evaluated_span_count, certificate.span_count)
                self.assertGreater(certificate.span_count, 0)
                self.assertEqual(certificate.bounds_scope, BOUNDS_SCOPE_CURVE)
                self.assertIsNotNone(certificate.obstacle_clearance_lower)
                self.assertIsNotNone(certificate.obstacle_clearance_upper)
                self.assertIsNotNone(certificate.map_inset_clearance_lower)
                self.assertIsNotNone(certificate.map_inset_clearance_upper)

    def test_work_cap_leaves_global_bounds_null_and_keeps_per_span_evidence(self):
        certificate = certify_exact_clearance(line_spline(3.0), max_evaluations=10)
        self.assertEqual(certificate.status, STATUS_INDETERMINATE)
        self.assertEqual(certificate.reason, REASON_WORK_CAP)
        self.assertLess(certificate.evaluated_span_count, certificate.span_count)
        self.assertEqual(certificate.bounds_scope, BOUNDS_SCOPE_PARTIAL)
        self.assertIsNone(certificate.obstacle_clearance_lower)
        self.assertIsNone(certificate.obstacle_clearance_upper)
        self.assertIsNone(certificate.map_inset_clearance_lower)
        self.assertIsNone(certificate.map_inset_clearance_upper)
        self.assertTrue(certificate.spans)
        self.assertEqual(len(certificate.spans), certificate.evaluated_span_count)


class CriticCrossCheckTests(unittest.TestCase):
    """Fixed critic set: the certificate must never be falsified by the critic."""

    def test_no_certified_admission_is_contradicted_by_the_independent_critic(self):
        checked = 0
        admitted = 0
        for name, spline in fixed_critic_cases():
            with self.subTest(case=name):
                certificate = certify_exact_clearance(spline)
                critic = DenseCritic(spline, samples=40001)
                checked += 1
                self.assertGreaterEqual(
                    critic.obstacle_net, certificate.obstacle_clearance_lower,
                    "%s: critic %.9f is below the certified lower bound %.9f"
                    % (name, critic.obstacle_net, certificate.obstacle_clearance_lower))
                if certificate.admitted:
                    admitted += 1
                    self.assertGreaterEqual(critic.obstacle_net, REQUIRED,
                                            "%s admitted but critic clearance is %.9f"
                                            % (name, critic.obstacle_net))
                    self.assertLessEqual(critic.lower_bound_estimate(),
                                         certificate.obstacle_clearance_upper
                                         + 10.0 * FLOAT_GUARD_M,
                                         "%s: critic lower estimate exceeds the certified upper bound"
                                         % name)
                    self.assertGreaterEqual(critic.inset_net, REQUIRED,
                                            "%s admitted but critic inset is %.9f"
                                            % (name, critic.inset_net))
        self.assertEqual(checked, len(fixed_critic_cases()))
        self.assertGreaterEqual(admitted, 8, "too few admitted cases to be meaningful")

    def test_critic_set_is_deterministic(self):
        first = [(name, DenseCritic(spline, samples=2001).obstacle_net)
                 for name, spline in fixed_critic_cases()]
        second = [(name, DenseCritic(spline, samples=2001).obstacle_net)
                  for name, spline in fixed_critic_cases()]
        self.assertEqual(first, second)


class SpeedBoundTests(unittest.TestCase):
    """The Lipschitz premise: reported per-span speed bounds must be valid."""

    def _check(self, spline, samples=97):
        certificate = certify_exact_clearance(spline)
        self.assertTrue(certificate.spans)
        worst_ratio = 0.0
        for span in certificate.spans:
            for index in range(samples + 1):
                t = span.u_start + (span.u_end - span.u_start) * index / samples
                speed = math.dist(spline.position.derivative().evaluate(t), (0.0, 0.0, 0.0))
                self.assertLessEqual(
                    speed, span.speed_bound * (1.0 + 1e-9),
                    "dense speed %.9f exceeds the certified bound %.9f at t=%.6f"
                    % (speed, span.speed_bound, t))
                if span.speed_bound > 0.0:
                    worst_ratio = max(worst_ratio, speed / span.speed_bound)
        return worst_ratio

    def test_speed_bounds_hold_on_every_case(self):
        ratios = []
        for name, spline in fixed_critic_cases():
            with self.subTest(case=name):
                ratios.append(self._check(spline, samples=41))
        self.assertGreater(max(ratios), 0.2,
                           "speed bounds are so loose that this test proves little")

    def test_speed_bounds_hold_on_wide_random_geometry(self):
        import random
        generator = random.Random(20260914)
        for trial in range(12):
            count = generator.randint(4, 12)
            points = [(generator.uniform(-6.0, 6.0), generator.uniform(-5.0, 5.0),
                       generator.uniform(0.5, 5.4)) for _ in range(count)]
            interval = generator.choice((0.05, 0.2, 0.7))
            spline = EgoSpline(3, list(UniformBspline(3, points, interval).knots), points)
            with self.subTest(trial=trial, count=count):
                self._check(spline, samples=31)


class StructuralFailClosedTests(unittest.TestCase):
    """Malformed internal structure is rejected, never admitted and never raised."""

    def test_repeated_knot_fails_closed(self):
        spline = family_spline(13)
        knots = list(spline.position._knots)
        knots[6] = knots[5]
        spline.position._knots = knots
        certificate = certify_exact_clearance(spline)
        self.assertEqual(certificate.status, STATUS_REJECTED)
        self.assertEqual(certificate.reason, REASON_KNOTS)
        self.assertFalse(certificate.admitted)
        self.assertIsNone(certificate.obstacle_clearance_lower)

    def test_non_finite_control_point_fails_closed(self):
        spline = family_spline(13)
        points = list(spline.position._points)
        points[5] = (math.nan, points[5][1], points[5][2])
        spline.position._points = points
        certificate = certify_exact_clearance(spline)
        self.assertEqual(certificate.status, STATUS_REJECTED)
        self.assertEqual(certificate.reason, REASON_STRUCTURE)
        self.assertFalse(certificate.admitted)

    def test_infinite_knot_fails_closed(self):
        spline = family_spline(13)
        knots = list(spline.position._knots)
        knots[7] = math.inf
        spline.position._knots = knots
        certificate = certify_exact_clearance(spline)
        self.assertEqual(certificate.status, STATUS_REJECTED)
        self.assertEqual(certificate.reason, REASON_STRUCTURE)

    def test_knot_cardinality_and_order_fail_closed(self):
        spline = family_spline(13)
        spline.position._knots = list(spline.position._knots)[:-1]
        certificate = certify_exact_clearance(spline)
        self.assertEqual(certificate.status, STATUS_REJECTED)
        self.assertEqual(certificate.reason, REASON_STRUCTURE)

        spline = family_spline(13)
        spline.position.order = 4
        certificate = certify_exact_clearance(spline)
        self.assertEqual(certificate.status, STATUS_REJECTED)
        self.assertEqual(certificate.reason, REASON_STRUCTURE)

    def test_collapsed_domain_tamper_fails_closed(self):
        """A knot tamper that would collapse the certified domain fails closed.

        With strictly increasing knots the certified domain ``[u_p, u_n]`` can
        never collapse, so the module's degenerate-domain branch is defensive
        only; this asserts the tamper is still rejected and never admitted.
        """
        spline = family_spline(13)
        knots = list(spline.position._knots)
        knots[3] = knots[4]              # domain start collapses onto its neighbour
        spline.position._knots = knots
        certificate = certify_exact_clearance(spline)
        self.assertEqual(certificate.status, STATUS_REJECTED)
        self.assertEqual(certificate.reason, REASON_KNOTS)
        self.assertFalse(certificate.admitted)
        self.assertIn(REASON_DOMAIN, CERTIFICATE_REASONS)

    def test_domain_tamper_that_is_still_monotone_is_still_certified(self):
        """A structurally valid but different spline is certified, not rejected."""
        spline = family_spline(13)
        knots = list(spline.position._knots)
        for index in range(len(knots)):
            if knots[index] > 0.0:
                knots[index] += 0.25
        spline.position._knots = knots
        certificate = certify_exact_clearance(spline)
        self.assertIn(certificate.status,
                      (STATUS_ADMITTED, STATUS_REJECTED, STATUS_INDETERMINATE))
        self.assertEqual(certificate.status == STATUS_ADMITTED, certificate.admitted)


class CallerErrorTests(unittest.TestCase):
    """Caller/protocol errors raise; geometric and structural ones do not."""

    def test_invalid_spline_binding_and_tolerance_raise(self):
        cases = [
            ("spline", lambda: certify_exact_clearance(None)),
            ("spline-type", lambda: certify_exact_clearance("spline")),
            ("binding", lambda: certify_exact_clearance(family_spline(9), binding=None)),
            ("binding-type", lambda: certify_exact_clearance(family_spline(9), binding={})),
            ("tol-zero", lambda: certify_exact_clearance(family_spline(9), tolerance_m=0.0)),
            ("tol-negative", lambda: certify_exact_clearance(family_spline(9), tolerance_m=-1e-3)),
            ("tol-nan", lambda: certify_exact_clearance(family_spline(9), tolerance_m=math.nan)),
            ("tol-inf", lambda: certify_exact_clearance(family_spline(9), tolerance_m=math.inf)),
            ("tol-bool", lambda: certify_exact_clearance(family_spline(9), tolerance_m=True)),
            ("tol-string", lambda: certify_exact_clearance(family_spline(9), tolerance_m="1e-3")),
            ("tol-too-large",
             lambda: certify_exact_clearance(family_spline(9), tolerance_m=MAX_TOLERANCE_M * 2)),
            ("tol-below-guard",
             lambda: certify_exact_clearance(family_spline(9), tolerance_m=1e-12)),
            ("nodes-zero", lambda: certify_exact_clearance(family_spline(9), max_nodes_per_span=0)),
            ("nodes-bool", lambda: certify_exact_clearance(family_spline(9), max_nodes_per_span=True)),
            ("nodes-float", lambda: certify_exact_clearance(family_spline(9), max_nodes_per_span=4.0)),
            ("evals-zero", lambda: certify_exact_clearance(family_spline(9), max_evaluations=0)),
            ("evals-negative", lambda: certify_exact_clearance(family_spline(9), max_evaluations=-5)),
        ]
        for name, call in cases:
            with self.subTest(case=name):
                with self.assertRaises(ExactClearanceError) as context:
                    call()
                self.assertIn(context.exception.reason, CERTIFICATE_REASONS)

    def test_error_reason_vocabulary_is_stable(self):
        self.assertEqual(len(set(CERTIFICATE_REASONS)), len(CERTIFICATE_REASONS))
        with self.assertRaises(ValueError):
            ExactClearanceError("not_a_reason", "x")


class WorkCapTests(unittest.TestCase):
    """Explicit caps: hitting one is indeterminate, fail-closed, and reported."""

    def test_global_evaluation_cap_yields_indeterminate(self):
        certificate = certify_exact_clearance(line_spline(3.0), max_evaluations=10)
        self.assertEqual(certificate.status, STATUS_INDETERMINATE)
        self.assertEqual(certificate.reason, REASON_WORK_CAP)
        self.assertFalse(certificate.admitted)
        self.assertFalse(certificate.tolerance_met)
        self.assertLessEqual(certificate.evaluations, 10)
        self.assertEqual(certificate.max_evaluations, 10)

    def test_per_span_node_cap_yields_indeterminate_on_a_safe_curve(self):
        certificate = certify_exact_clearance(line_spline(3.0), max_nodes_per_span=1)
        self.assertEqual(certificate.status, STATUS_INDETERMINATE)
        self.assertEqual(certificate.reason, REASON_WORK_CAP)
        self.assertFalse(certificate.admitted)
        self.assertEqual(certificate.max_nodes_per_span, 1)

    def test_cap_does_not_prevent_a_conclusive_rejection(self):
        certificate = certify_exact_clearance(line_spline(OBSTACLE_MAX[1] - 0.5),
                                              max_evaluations=8)
        self.assertEqual(certificate.status, STATUS_REJECTED)
        self.assertEqual(certificate.reason, REASON_OBSTACLE)
        self.assertFalse(certificate.admitted)

    def test_default_caps_are_large_but_finite(self):
        certificate = certify_exact_clearance(family_spline(33))
        self.assertGreater(certificate.max_evaluations, 100000)
        self.assertGreater(certificate.max_nodes_per_span, 1000)
        self.assertLessEqual(certificate.evaluations, certificate.max_evaluations)
        self.assertTrue(all(span.nodes <= certificate.max_nodes_per_span
                            for span in certificate.spans))


class BindingObjectTests(unittest.TestCase):
    """Obstacle binding and map binding must be reported distinctly."""

    def test_obstacle_binding_is_reported(self):
        certificate = certify_exact_clearance(line_at_net(REQUIRED + 0.10))
        self.assertEqual(certificate.status, STATUS_ADMITTED)
        self.assertEqual(certificate.binding_object, BINDING_OBJECT_OBSTACLE)
        self.assertIsNotNone(certificate.binding_span_index)
        self.assertLess(certificate.obstacle_clearance_lower,
                        certificate.map_inset_clearance_lower)

    def test_map_binding_is_reported(self):
        certificate = certify_exact_clearance(line_spline(5.34))
        self.assertEqual(certificate.status, STATUS_ADMITTED)
        self.assertEqual(certificate.binding_object, BINDING_OBJECT_MAP_INSET)
        self.assertLess(certificate.map_inset_clearance_lower,
                        certificate.obstacle_clearance_lower)

    def test_map_rejection_reports_the_map_reason(self):
        certificate = certify_exact_clearance(line_spline(5.36))
        self.assertEqual(certificate.status, STATUS_REJECTED)
        self.assertEqual(certificate.reason, REASON_MAP)
        self.assertEqual(certificate.binding_object, BINDING_OBJECT_MAP_INSET)
        self.assertLess(certificate.map_inset_clearance_upper, REQUIRED)

    def test_binding_interval_is_a_real_active_span(self):
        spline = family_spline(33)
        certificate = certify_exact_clearance(spline)
        knots = list(spline.position.knots)
        index = certificate.binding_span_index
        self.assertIsNotNone(index)
        self.assertEqual(certificate.binding_u_start, knots[index])
        self.assertEqual(certificate.binding_u_end, knots[index + 1])
        self.assertIn(index, [span.span_index for span in certificate.spans])
        self.assertLessEqual(index, len(spline.position._points) - 1)


class DeterminismTests(unittest.TestCase):
    """Same input, same certificate -- including across fresh objects."""

    def test_repeated_calls_are_identical(self):
        for name, spline in fixed_critic_cases()[:6]:
            with self.subTest(case=name):
                first = certify_exact_clearance(spline)
                second = certify_exact_clearance(spline)
                self.assertEqual(json.dumps(first.to_dict(), sort_keys=True),
                                 json.dumps(second.to_dict(), sort_keys=True))

    def test_fresh_but_equal_splines_are_identical(self):
        first = certify_exact_clearance(family_spline(33))
        second = certify_exact_clearance(family_spline(33))
        self.assertEqual(json.dumps(first.to_dict(), sort_keys=True),
                         json.dumps(second.to_dict(), sort_keys=True))
        payload_first = certify_exact_clearance(recorded_payload_spline())
        payload_second = certify_exact_clearance(recorded_payload_spline())
        self.assertEqual(json.dumps(payload_first.to_dict(), sort_keys=True),
                         json.dumps(payload_second.to_dict(), sort_keys=True))

    def test_to_dict_is_json_serializable_and_complete(self):
        certificate = certify_exact_clearance(family_spline(17))
        encoded = json.dumps(certificate.to_dict(), sort_keys=True, allow_nan=False)
        decoded = json.loads(encoded)
        for key in ("status", "admitted", "evidence_kind", "reason", "tolerance_m",
                    "obstacle_clearance_lower", "obstacle_clearance_upper",
                    "map_inset_clearance_lower", "map_inset_clearance_upper",
                    "binding_object", "binding_span_index", "span_count",
                    "evaluated_span_count", "nodes", "evaluations", "spans",
                    "bounds_scope", "candidate_only", "non_claims"):
            self.assertIn(key, decoded)
        self.assertEqual(decoded["bounds_scope"], BOUNDS_SCOPE_CURVE)
        self.assertEqual(len(decoded["spans"]), certificate.evaluated_span_count)


class EvidenceSurfaceTests(unittest.TestCase):
    """The certificate must be honest, complete and candidate-only."""

    def test_evidence_fields_and_candidate_status(self):
        certificate = certify_exact_clearance(family_spline(9))
        self.assertEqual(certificate.evidence_kind, EVIDENCE_KIND)
        self.assertEqual(EVIDENCE_KIND, "lipschitz_bracket_certified")
        self.assertEqual(CANDIDATE_STATUS, "candidate_only")
        self.assertTrue(certificate.candidate_only)
        self.assertEqual(certificate.float_guard_m, FLOAT_GUARD_M)
        self.assertGreaterEqual(len(certificate.non_claims), 4)
        self.assertTrue(any("candidate only" in claim for claim in certificate.non_claims))
        self.assertEqual(certificate.scene_id, EGO_SINGLE_BOX_BINDING.scene_id)
        self.assertEqual(certificate.profile_hash, PROFILE.profile_hash)
        self.assertEqual(certificate.vehicle_radius, RADIUS)
        self.assertEqual(certificate.required_clearance, REQUIRED)
        self.assertEqual(certificate.clearance_margin, RADIUS + REQUIRED)

    def test_margin_convention_matches_the_committed_geometry(self):
        certificate = certify_exact_clearance(line_at_net(0.5))
        self.assertAlmostEqual(certificate.clearance_margin, 0.6499999999999999, places=15)

    def test_module_is_not_wired_into_the_committed_gate_or_pump(self):
        import Simulator.wksim_planning.ego_scene_admission as admission
        import Simulator.wksim_runtime.planner_transport_pump as pump
        for module in (admission, pump):
            source = inspect.getsource(module)
            self.assertNotIn("ego_exact_clearance", source,
                             "%s references the candidate module" % module.__name__)
            self.assertNotIn("certify_exact_clearance", source,
                             "%s references the candidate entry point" % module.__name__)
            self.assertNotIn("ExactClearanceCertificate", source,
                             "%s references the candidate certificate" % module.__name__)

    def test_declared_reason_vocabulary_covers_every_observed_outcome(self):
        observed = set()
        for _, spline in fixed_critic_cases():
            certificate = certify_exact_clearance(spline)
            if certificate.reason is not None:
                observed.add(certificate.reason)
        observed.add(certify_exact_clearance(line_spline(3.0), max_evaluations=5).reason)
        observed.add(certify_exact_clearance(line_spline(5.36)).reason)
        for reason in observed:
            self.assertIn(reason, CERTIFICATE_REASONS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
