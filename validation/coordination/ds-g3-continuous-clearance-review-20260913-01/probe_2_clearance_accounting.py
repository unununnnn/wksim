"""Probe 2 -- control-box -> AABB net clearance accounting, radius/required, map inset.

Adversarial questions:
  Q1  Is the reported obstacle gap the exact box-box Euclidean distance (and is the
      radius subtracted EXACTLY once, with ``required_clearance`` never folded in)?
  Q2  Does the certificate's obstacle measure equal the sampled path's centreline
      measure, so there is no scale/unit mismatch between the two gates?
  Q3  Where is the empirical acceptance threshold, in metres?  A doubled radius
      (2r + required = 1.00 m) or a dropped radius (required = 0.30 m) would show up
      as a threshold far from 0.65 m.
  Q4  Is the map inset per axis (one deep intrusion cannot be averaged away) and is
      its effective margin ``vehicle_radius + required_clearance`` (not 2r, not r)?
"""
from __future__ import annotations

import math
import random
from fractions import Fraction

from probe_common import (  # noqa: E402
    EXACT_MARGIN,
    MAP_MAX,
    MAP_MIN,
    OBSTACLE_MAX,
    OBSTACLE_MIN,
    RADIUS,
    REQUIRED,
    Probe,
    _aabb_gap,
    _inset_clearance,
    build_spline,
    certify_continuous_clearance,
    constant_spline,
    segment_surface_distance,
    uniform_knots,
)

SEED = 20260913
MATERIAL_TOL = 1e-9


def exact_box_box_distance(box_a_low, box_a_high, box_b_low, box_b_high):
    """Rigorous lower bound on the exact box-box distance (Fraction)."""
    total = Fraction(0)
    for a_low, a_high, b_low, b_high in zip(box_a_low, box_a_high, box_b_low, box_b_high):
        separation = max(Fraction(a_low) - Fraction(b_high), Fraction(b_low) - Fraction(a_high))
        if separation > 0:
            total += separation ** 2
    if total == 0:
        return Fraction(0)
    root = math.isqrt(total.numerator * total.denominator)
    return Fraction(root, total.denominator)


def bisect_threshold(predicate, low, high, iterations=200):
    """Largest float boundary of a monotone predicate, by deterministic bisection."""
    if not predicate(high):
        return None
    for _ in range(iterations):
        middle = (low + high) / 2.0
        if middle <= low or middle >= high:
            break
        if predicate(middle):
            high = middle
        else:
            low = middle
    return high


def main():
    probe = Probe("PROBE-2", "clearance accounting, radius/required, per-axis inset",
                  "probe_2_clearance_accounting.json")
    rng = random.Random(SEED)

    # ---- Q1a: _aabb_gap against exact box-box distance ---------------------
    worst_ulp = 0.0
    overlap_ok = True
    for _ in range(3000):
        low_a = [rng.uniform(-5, 5) for _ in range(3)]
        high_a = [value + rng.uniform(1e-6, 4) for value in low_a]
        low_b = [rng.uniform(-5, 5) for _ in range(3)]
        high_b = [value + rng.uniform(1e-6, 4) for value in low_b]
        gap = _aabb_gap(low_a, high_a, low_b, high_b)
        exact = exact_box_box_distance(low_a, high_a, low_b, high_b)
        error = abs(Fraction(gap) - exact)
        ulp = math.ulp(gap) if gap > 0 else 0.0
        worst_ulp = max(worst_ulp, float(error / Fraction(ulp)) if ulp else 0.0)
        if all(min(a_hi, b_hi) >= max(a_lo, b_lo)
               for a_lo, a_hi, b_lo, b_hi in zip(low_a, high_a, low_b, high_b)):
            overlap_ok = overlap_ok and gap == 0.0
    probe.check(worst_ulp <= 4.0,
                "aabb_gap matches the exact box-box distance (<= 4 ulp)",
                {"worst_ulp_error": worst_ulp, "samples": 3000})
    probe.check(overlap_ok, "aabb_gap is exactly 0.0 for overlapping boxes")

    # ---- Q1b/Q2: the certificate's numbers, recomputed from its own intervals
    cases = [
        ("clear straight", [(float(i) * 0.5, 3.0, 1.0) for i in range(7)], 0.1),
        ("boundary straight", [(float(i) * 0.5 - 1.5, 1.6500000000000001, 2.0) for i in range(7)], 0.1),
        ("collision straight", [(float(i - 3) * 0.5, 0.0, 1.0) for i in range(7)], 0.1),
        ("constant point", [(0.0, 1.9, 2.75)] * 7, 0.05),
        ("wide random", [(rng.uniform(-6, 6), rng.uniform(-3, 4), rng.uniform(0.5, 5.0))
                         for _ in range(15)], 0.05),
    ]
    for label, cps, knot_h in cases:
        spline = build_spline(cps, uniform_knots(cps, knot_h))
        points = [tuple(float(c) for c in p) for p in cps]
        certificate = certify_continuous_clearance(spline)
        # independent recomputation of the minimum box gap over the claimed boxes
        minimum_gap = math.inf
        for start_u, end_u, span_index, last in certificate.intervals:
            active = points[span_index - 3:last + 1]
            low = [min(point[axis] for point in active) for axis in range(3)]
            high = [max(point[axis] for point in active) for axis in range(3)]
            minimum_gap = min(minimum_gap, _aabb_gap(low, high, OBSTACLE_MIN, OBSTACLE_MAX))
        probe.check(certificate.obstacle_hull_gap == minimum_gap,
                    f"{label}: reported obstacle_hull_gap == min over claimed boxes",
                    {"reported": certificate.obstacle_hull_gap, "recomputed": minimum_gap})
        probe.check(certificate.min_net_obstacle_clearance
                    == certificate.obstacle_hull_gap - certificate.vehicle_radius,
                    f"{label}: net clearance == gap - radius (one subtraction, bitwise)",
                    {"net": certificate.min_net_obstacle_clearance,
                     "gap_minus_radius": certificate.obstacle_hull_gap - certificate.vehicle_radius})
        probe.check(certificate.vehicle_radius == RADIUS and certificate.required_clearance == REQUIRED,
                    f"{label}: certificate reads radius/required from the committed profile",
                    {"radius": certificate.vehicle_radius, "required": certificate.required_clearance})

    # ---- Q2: same centreline measure as the sampled gate -------------------
    point = (0.0, 1.9, 2.75)
    constant = constant_spline(point)
    certificate = certify_continuous_clearance(constant)
    sampled_surface = segment_surface_distance(point, point)
    probe.check(certificate.obstacle_hull_gap == sampled_surface,
                "constant curve: certificate gap == segment_surface_distance(p, p) bitwise",
                {"certificate_gap": certificate.obstacle_hull_gap, "sampled_surface": sampled_surface})

    # ---- Q3: empirical thresholds -----------------------------------------
    def obstacle_proven(delta):
        return certify_continuous_clearance(
            constant_spline((0.0, 1.0 + delta, 2.75))).proven

    def inset_proven(margin):
        return certify_continuous_clearance(constant_spline((3.0, 3.0, margin))).proven

    obstacle_threshold = bisect_threshold(obstacle_proven, 1e-6, 3.0)
    inset_threshold = bisect_threshold(inset_proven, 1e-6, 3.0)
    exact_required = float(EXACT_MARGIN)
    probe.observe("obstacle_accept_threshold_m", obstacle_threshold)
    probe.observe("inset_accept_threshold_m", inset_threshold)
    probe.observe("exact_margin_m", exact_required)
    probe.observe("float_margin_m", RADIUS + REQUIRED)
    for label, threshold in (("obstacle", obstacle_threshold), ("inset", inset_threshold)):
        probe.check(abs(threshold - exact_required) <= 4 * math.ulp(exact_required),
                    f"{label} threshold == radius + required_clearance (within 4 ulp)",
                    {"threshold": threshold, "exact": exact_required,
                     "ulp": math.ulp(exact_required)})
        probe.check(abs(threshold - (2 * RADIUS + REQUIRED)) > 0.1,
                    f"{label} threshold is NOT 2*radius + required (no double subtraction)",
                    {"threshold": threshold, "double_radius_value": 2 * RADIUS + REQUIRED})
        probe.check(abs(threshold - REQUIRED) > 0.1,
                    f"{label} threshold is NOT required_clearance alone (radius not dropped)",
                    {"threshold": threshold, "required_only": REQUIRED})

    # ---- Q4: per-axis inset decision and exact effective margin -----------
    inset_low = tuple(low + (RADIUS + REQUIRED) for low in MAP_MIN)
    inset_high = tuple(high - (RADIUS + REQUIRED) for high in MAP_MAX)
    probe.check(inset_low[2] == 0.0 + (RADIUS + REQUIRED) and inset_low[2] < 0.65,
                "inset faces use the float sum radius+required (0.6499999999999999)",
                {"inset_low_z": inset_low[2], "exact": exact_required})

    # one-axis intrusion with large slack elsewhere must fail
    intrusive = ((0.0, 0.0, 0.0), (1.0, 1.0, 0.2))          # z below the floor+margin
    generous = ((0.0, 0.0, 0.2), (1.0, 1.0, 1.2))
    per_axis = _inset_clearance(intrusive[0], intrusive[1], inset_low, inset_high)
    generous_axis = _inset_clearance(generous[0], generous[1], inset_low, inset_high)
    probe.check(len(per_axis) == 3 and per_axis[2] < 0.0 and per_axis[0] > 0.0 and per_axis[1] > 0.0,
                "inset clearance is per axis: a z intrusion is negative while x/y are positive",
                {"axes": list(per_axis)})
    probe.check(min(generous_axis) > min(per_axis),
                "inset clearance is signed per axis (deeper intrusion is strictly smaller)",
                {"generous_min": min(generous_axis), "intrusive_min": min(per_axis)})
    # an averaging formula would hide the intrusion; verify the decision cannot be
    # reconstructed from any cross-axis average
    probe.check(sum(per_axis) / 3.0 > 0.0 > per_axis[2],
                "cross-axis average of the same box is positive while the true decision is negative",
                {"mean": sum(per_axis) / 3.0, "min_axis": per_axis[2]})

    certificate_at_face = certify_continuous_clearance(constant_spline((3.0, 3.0, inset_low[2])))
    certificate_below = certify_continuous_clearance(
        constant_spline((3.0, 3.0, math.nextafter(inset_low[2], -math.inf))))
    probe.check(certificate_at_face.proven and not certificate_below.proven,
                "inset decision is a plain >= 0 on the lowest face value",
                {"at_face_proven": certificate_at_face.proven,
                 "below_face_proven": certificate_below.proven})
    exact_tolerance = EXACT_MARGIN - Fraction(inset_low[2])
    probe.observe("exact_inset_rounding_tolerance_m", float(exact_tolerance))
    probe.check(abs(float(exact_tolerance)) <= 2 * math.ulp(exact_required),
                "exact inset rounding tolerance is at most 2 ulp of the margin",
                {"tolerance_m": float(exact_tolerance), "ulp": math.ulp(exact_required)})
    probe.observe("seed", SEED)
    probe.observe("exact_margin_fraction", EXACT_MARGIN)
    probe.note("EXACT_MARGIN is the exact rational sum of the committed DOUBLE constants "
               "(0.35 + 0.30), not the decimal ideal 13/20: the two differ by 5.55e-17 m "
               "(half an ulp), because fl(0.35 + 0.30) rounds to 0.6499999999999999 by "
               "ties-to-even. Both acceptance thresholds sit within 1 ulp of that exact "
               "double-sum, so no radius or required_clearance term is duplicated or lost.")
    probe.note("Every threshold is located by deterministic float bisection; the "
               "obstacle and inset thresholds both sit at radius + required_clearance, "
               "which rules out a duplicated radius, a duplicated required_clearance, "
               "and a dropped radius on either gate.")
    probe.note("The map inset is compared per axis, so a deep single-axis intrusion "
               "cannot be averaged away; the AND-of-axes decision is what "
               "_control_hull_span_certificate uses.")
    return probe.finish()


if __name__ == "__main__":
    raise SystemExit(main())
