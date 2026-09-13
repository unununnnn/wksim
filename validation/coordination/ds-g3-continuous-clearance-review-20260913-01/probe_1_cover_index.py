"""Probe 1 -- B-spline interval indexing, cover completeness, knot-layout boundaries.

Adversarial questions:
  Q1  Is the certificate's interval cover EXACTLY the evaluation domain
      [u_p, u_{m-p}] with no gap and no truncation, for uniform / non-uniform /
      shifted / extreme-aspect knot layouts?
  Q2  Is each interval's reported active window (first,last) == (j-p, j), i.e. the
      same window upstream ``evaluateDeBoor`` uses on span j?
  Q3  Does the curve actually stay inside the AABB of the active points its
      interval claims (the soundness premise)?
  Q4  Counterexample search: can a certificate with ``proven=True`` coexist with an
      exact (Fraction, squared-predicate) clearance or inset violation?

Density is only a counterexample search; absence of a hit is not a proof.
"""
from __future__ import annotations

import random

from probe_common import (  # noqa: E402
    ORDER,
    Probe,
    build_spline,
    certify_continuous_clearance,
    exact_inset_slack,
    exact_obstacle_shortfall_squared,
    exact_obstacle_slack,
    uniform_knots,
)

SEED = 20260913


def expected_intervals(knots, control_count, order):
    """The mathematical spec in the CODe's own tuple convention.

    The emitted tuple is ``(start_u, end_u, span_index_j, last_knot_index)`` with
    ``span_index_j == j`` and the active control window ``P_{j-p}..P_j`` (upstream
    ``evaluateDeBoor`` indices).  The in-scope contract document labels the third
    field ``first_active_index``, which is a different number for ``order > 0``;
    that discrepancy is called out explicitly in the checks below.
    """
    return tuple((knots[j], knots[j + 1], j, j) for j in range(order, control_count))


def distorted_knots(cps, base_h, ratio, first_gaps=None, tail_ratio=None):
    """Non-uniform layout: the first p gaps stay ``base_h``, later gaps scale."""
    count = len(cps)
    order = ORDER
    m = count + order
    tail_ratio = ratio if tail_ratio is None else tail_ratio
    knots = [0.0] * (m + 1)
    for i in range(order + 1):
        knots[i] = -(order - i) * base_h
    for i in range(order + 1, m + 1):
        gap = base_h * (ratio if i <= m - order else tail_ratio)
        knots[i] = knots[i - 1] + gap
    return knots


def random_gap_knots(cps, rng, low=-6.0, high=3.0):
    count = len(cps)
    order = ORDER
    m = count + order
    first = 10.0 ** rng.uniform(low, high)
    knots = [0.0] * (m + 1)
    for i in range(order + 1):
        knots[i] = -(order - i) * first
    for i in range(order + 1, m + 1):
        knots[i] = knots[i - 1] + 10.0 ** rng.uniform(low, high)
    return knots


def random_cps(rng, count, *, x=(-8.0, 8.0), y=(-5.0, 5.0), z=(0.5, 5.5)):
    return [(rng.uniform(*x), rng.uniform(*y), rng.uniform(*z)) for _ in range(count)]


def straight_cps(y, z, count=7, step=0.5, x0=-1.5):
    return [(x0 + i * step, y, z) for i in range(count)]


def family_cases(rng):
    """Deterministic family of (label, cps, knots) triples spanning the layouts."""
    for count in (4, 5, 7, 9, 12, 20, 41):
        for knot_h in (0.002, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5):
            cps = random_cps(rng, count)
            yield f"upstream-uniform n={count} h={knot_h}", cps, uniform_knots(cps, knot_h)
    for y in (2.0, 1.65, 1.6500000000000001, 1.6, -3.0):
        for z in (1.0, 2.75, 5.0):
            cps = straight_cps(y, z)
            yield f"straight y={y} z={z}", cps, uniform_knots(cps, 0.1)
    for count in (4, 7, 12):
        for ratio in (0.25, 0.5, 2.0, 4.0, 10.0):
            cps = random_cps(rng, count)
            knots = distorted_knots(cps, 0.05, ratio)
            yield f"scaled-gap n={count} ratio={ratio}", cps, knots
    for count in (5, 8, 15):
        for _ in range(4):
            cps = random_cps(rng, count)
            knots = random_gap_knots(cps, rng)
            yield f"random-gap n={count}", cps, knots
    for count in (6, 11):
        cps = random_cps(rng, count)
        base = uniform_knots(cps, 0.07)
        shifted = [value - 7.5 for value in base]
        yield f"shifted-domain n={count}", cps, shifted
    for knot_h in (1e-6, 1e-3, 50.0):
        cps = random_cps(rng, 7)
        yield f"extreme-h h={knot_h}", cps, uniform_knots(cps, knot_h)


def cover_and_containment(probe, label, cps, knots):
    spline = build_spline(cps, knots)
    points = [tuple(float(c) for c in p) for p in cps]
    live = tuple(spline.position.knots)
    count = len(points)
    certificate = certify_continuous_clearance(spline)
    expected = expected_intervals(live, count, ORDER)

    probe.check(certificate.structural_reason is None,
                f"{label}: certificate structure built", certificate.structural_reason)
    probe.check(certificate.interval_count == count - ORDER,
                f"{label}: interval_count == N - order",
                {"interval_count": certificate.interval_count, "expected": count - ORDER})
    probe.check(tuple(certificate.intervals) == expected,
                f"{label}: interval (start,end,span_index,last_knot) exact and in order")
    if certificate.intervals:
        span_index = certificate.intervals[0][2]
        first_active = span_index - ORDER
        probe.check(span_index == ORDER and first_active == 0,
                    f"{label}: third field is span j (not first_active); j-p == 0",
                    {"span_index": span_index, "first_active": first_active,
                     "doc_field_label_is_first_active_index": False})
    probe.check(certificate.domain_start_u == live[ORDER] and certificate.domain_end_u == live[count],
                f"{label}: domain == [u_p, u_(m-p)]",
                {"start": certificate.domain_start_u, "end": certificate.domain_end_u,
                 "u_p": live[ORDER], "u_m_p": live[count]})
    probe.check(spline.duration == certificate.domain_end_u - certificate.domain_start_u,
                f"{label}: cover span == evaluated duration",
                {"duration": spline.duration,
                 "cover": certificate.domain_end_u - certificate.domain_start_u})
    if certificate.intervals:
        cover_start = certificate.intervals[0][0]
        cover_end = certificate.intervals[-1][1]
        gap_free = all(certificate.intervals[i][1] == certificate.intervals[i + 1][0]
                       for i in range(len(certificate.intervals) - 1))
        probe.check(gap_free, f"{label}: cover is gap-free")
        probe.check(cover_start == live[ORDER] and cover_end == live[count],
                    f"{label}: cover endpoints exact")

    # Q3 containment: does the curve stay in the AABB its own interval claims?
    # The emitted third field is the SPAN index j, so the active window is
    # P_{j-order}..P_j (verified independently against the spec above).
    worst_excess = 0.0
    samples = 0
    for start_u, end_u, span_index, last in certificate.intervals:
        active = points[span_index - ORDER:last + 1]
        low = [min(point[axis] for point in active) for axis in range(3)]
        high = [max(point[axis] for point in active) for axis in range(3)]
        for step in range(65):
            u = start_u + (end_u - start_u) * step / 64.0
            position = spline.position_at(u - live[ORDER])
            samples += 1
            for axis in range(3):
                worst_excess = max(worst_excess, low[axis] - position[axis],
                                   position[axis] - high[axis])
    probe.check(worst_excess <= 1e-9,
                f"{label}: curve inside every claimed active-set AABB",
                {"worst_excess_m": worst_excess, "samples": samples})
    return spline, certificate, worst_excess


def soundness_audit(probe, label, spline, certificate, samples=801, material_tol=1e-9):
    """If the certificate claims a proof, attack it from the curve side, exactly.

    ``material_tol`` is 1 nanometre: ten orders of magnitude below the 0.65 m
    margin.  The strict Fraction predicate is reported as well, because the
    certificate bounds the EXACT real-arithmetic curve while the evaluator used
    here is floating-point de Boor; a few-ulp evaluator excursion outside the
    control-point box is a measurable precision statement, not a clearance gap.
    """
    if not certificate.proven:
        return
    duration = spline.duration
    worst_obstacle_m = None
    worst_inset_m = None
    strict_obstacle = 0
    strict_inset = 0
    material_obstacle = 0
    material_inset = 0
    for step in range(samples + 1):
        position = spline.position_at(duration * step / samples)
        obstacle_shortfall = exact_obstacle_shortfall_squared(position)
        obstacle_slack_m = exact_obstacle_slack(position)
        inset_slack = exact_inset_slack(position)
        if obstacle_shortfall < 0:
            strict_obstacle += 1
        if obstacle_slack_m < -material_tol:
            material_obstacle += 1
        if inset_slack < 0:
            strict_inset += 1
        if inset_slack < -material_tol:
            material_inset += 1
        worst_obstacle_m = (obstacle_slack_m if worst_obstacle_m is None
                            else min(worst_obstacle_m, obstacle_slack_m))
        worst_inset_m = inset_slack if worst_inset_m is None else min(worst_inset_m, inset_slack)
    probe.observe(f"{label}: exact worst obstacle slack (m)", float(worst_obstacle_m))
    probe.observe(f"{label}: exact worst inset slack (m)", float(worst_inset_m))
    probe.observe(f"{label}: strict exact obstacle hits", strict_obstacle)
    probe.observe(f"{label}: strict exact inset hits", strict_inset)
    probe.check(material_obstacle == 0,
                f"{label}: proven certificate has no material obstacle violation",
                {"violations": material_obstacle, "tol_m": material_tol,
                 "samples": samples + 1})
    probe.check(material_inset == 0,
                f"{label}: proven certificate has no material inset violation",
                {"violations": material_inset, "tol_m": material_tol,
                 "samples": samples + 1})



def main():
    probe = Probe("PROBE-1", "interval indexing, cover completeness, knot boundaries",
                  "probe_1_cover_index.json")
    rng = random.Random(SEED)
    cases = 0
    proven = 0
    max_containment_excess = 0.0
    for label, cps, knots in family_cases(rng):
        cases += 1
        spline, certificate, worst_excess = cover_and_containment(probe, label, cps, knots)
        max_containment_excess = max(max_containment_excess, worst_excess)
        if certificate.proven:
            proven += 1
            if cases % 3 == 0:            # keep the exact audit bounded
                soundness_audit(probe, label, spline, certificate)
    probe.observe("cases", cases)
    probe.observe("cases_with_proven_certificate", proven)
    probe.observe("max_curve_outside_claimed_box_m", max_containment_excess)
    probe.observe("seed", SEED)
    probe.note("Every interval claim is compared against the mathematical spec "
               "span j -> P_{j-p}..P_j (upstream evaluateDeBoor indices), not against "
               "the certificate's own bookkeeping.")
    probe.note("Q4 is a counterexample search over a deterministic family; it cannot "
               "prove soundness, only fail to refute it.")
    return probe.finish()


if __name__ == "__main__":
    raise SystemExit(main())
