"""Probe 4 -- clamped / non-uniform / repeated knot boundaries, and dead-branch proof.

Adversarial questions:
  Q1  Can a genuinely CLAMPED (end-multiplicity p+1) knot vector reach the
      certificate at all through the reviewed pipeline?
  Q2  The module docstring and the in-scope contract document claim that repeated
      left knots "widen the active set, which keeps the bound sound" and that
      degenerate zero-length spans are "skipped, never fused".  Is that grouping /
      skip code ever executed, for ANY reachable or tampered knot vector?
  Q3  A dynamic line-coverage proof of Q2 (not just a static reading): run a legal
      vector and several cardinality-preserving repeating vectors under a line
      tracer and record exactly which certificate lines execute.
  Q4  Can the FP evaluator even evaluate a repeated-knot vector (out of contract)?
  Q5  Do shifted (u_p != 0) and non-uniform (upstream lengthenTime-shaped) layouts
      keep the cover exact and the domain equal to the evaluated duration?
"""
from __future__ import annotations

import sys

from probe_common import (  # noqa: E402
    ORDER,
    REPO_ROOT,
    Probe,
    SplineError,
    assess_spline_clearance,
    build_spline,
    certify_continuous_clearance,
    uniform_knots,
)

SOURCE = REPO_ROOT / "Simulator" / "wksim_planning" / "ego_scene_admission.py"


def source_markers():
    """Locate the certificate's monotone gate and grouping lines by text."""
    text = SOURCE.read_text(encoding="utf-8").splitlines()
    markers = {}
    for number, line in enumerate(text, start=1):
        stripped = line.strip()
        if stripped.startswith('return unproven("non_monotone_knots"'):
            markers["non_monotone_return"] = number
        if stripped.startswith("while last + 1 <= control_count - 1"):
            markers["grouping_loop"] = number
        if stripped == "last += 1":
            markers["grouping_step"] = number
        if stripped == "continue":
            markers["skip_continue"] = number
        if stripped.startswith("interval_start = knots[index]"):
            markers["walk_enter"] = number
        if stripped.startswith("active = control_points[index - order:last + 1]"):
            markers["active_slice"] = number
    return markers


def trace_certificate(cps, knots, base_knots=None):
    """Return (executed_line_numbers, certificate) for one certify call.

    A tampered (repeating) vector cannot pass EgoSpline construction, so the spline
    is built with the legal layout and the live ``_knots`` list is then replaced --
    exactly the tamper path the certificate's fail-closed invariants defend.
    """
    spline = build_spline(cps, base_knots if base_knots is not None else knots)
    if base_knots is not None:
        spline.position._knots = list(knots)
    executed = set()

    def tracer(frame, event, arg):
        if event == "line" and frame.f_code.co_filename.endswith("ego_scene_admission.py"):
            executed.add(frame.f_lineno)
        return tracer

    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        certificate = certify_continuous_clearance(spline)
    finally:
        sys.settrace(previous)
    return executed, certificate


def repeat_patterns(cps, knots):
    """Cardinality-preserving knot vectors that introduce one or more repeats."""
    count = len(cps)
    order = ORDER
    patterns = {}
    for name, index in (("interior_repeat", order + 3),
                        ("second_span_repeat", order + 1),
                        ("near_domain_start", order),
                        ("last_span_repeat", count),
                        ("pre_domain_repeat", order - 1)):
        if 1 <= index < len(knots):
            tampered = list(knots)
            tampered[index] = tampered[index - 1]
            patterns[name] = tampered
    doubled = list(knots)
    doubled[order + 2] = doubled[order + 1]
    patterns["double_repeat"] = doubled
    return patterns


def main():
    probe = Probe("PROBE-4", "clamped / non-uniform / repeated knot boundaries",
                  "probe_4_knot_boundaries.json")
    markers = source_markers()
    probe.observe("source_markers", markers)
    probe.check(set(markers) >= {"non_monotone_return", "grouping_loop", "grouping_step",
                                 "skip_continue", "walk_enter", "active_slice"},
                "certificate source markers located for the coverage proof", markers)

    cps = [(float(i) * 0.5 - 1.5, 3.0, 1.0) for i in range(10)]
    legal_knots = uniform_knots(cps, 0.1)

    # ---- Q1: genuinely clamped vectors cannot be constructed ---------------
    clamped = ([0.0, 0.0, 0.0, 0.0]
               + [0.1 * i for i in range(1, len(cps) - ORDER + 1)]
               + [0.1 * (len(cps) - ORDER)] * ORDER)
    probe.observe("clamped_candidate_length", len(clamped))
    try:
        build_spline(cps, clamped)
        probe.fail("clamped knot vector (end multiplicity p+1) is rejected at construction")
    except SplineError as error:
        probe.check(True,
                    "clamped knot vector (end multiplicity p+1) is rejected at construction",
                    {"error": str(error)})
    probe.check(all(legal_knots[index] > legal_knots[index - 1]
                    for index in range(1, len(legal_knots))),
                "the only constructible layouts are strictly increasing (non-clamped)")

    # ---- Q2/Q3: dead-branch proof under a line tracer ----------------------
    executed_legal, legal_cert = trace_certificate(cps, legal_knots)
    probe.check(markers["walk_enter"] in executed_legal
                and markers["active_slice"] in executed_legal,
                "tracer sanity: the interval walk and active-slice lines execute on a legal vector")
    probe.check(legal_cert.proven and legal_cert.interval_count == len(cps) - ORDER,
                "legal vector certifies with N-order intervals",
                {"intervals": legal_cert.interval_count})
    probe.check(markers["grouping_step"] not in executed_legal
                and markers["skip_continue"] not in executed_legal,
                "legal (strictly increasing) vector never enters the repeat grouping branch")

    repeat_hits = {}
    for name, tampered in repeat_patterns(cps, legal_knots).items():
        executed, certificate = trace_certificate(cps, tampered, legal_knots)
        repeat_hits[name] = {
            "reason": certificate.structural_reason,
            "interval_count": certificate.interval_count,
            "proven": certificate.proven,
            "non_monotone_return_executed": markers["non_monotone_return"] in executed,
            "grouping_step_executed": markers["grouping_step"] in executed,
            "skip_continue_executed": markers["skip_continue"] in executed,
            "active_slice_executed": markers["active_slice"] in executed,
        }
    probe.observe("repeat_patterns", repeat_hits)
    probe.check(all(row["reason"] == "non_monotone_knots" for row in repeat_hits.values()),
                "every repeating knot vector fails closed as non_monotone_knots",
                {name: row["reason"] for name, row in repeat_hits.items()})
    probe.check(all(row["interval_count"] == 0 and not row["proven"]
                    for row in repeat_hits.values()),
                "every repeating knot vector proves nothing (interval_count 0, proven False)")
    probe.check(all(not row["grouping_step_executed"] and not row["skip_continue_executed"]
                    and not row["active_slice_executed"] for row in repeat_hits.values()),
                "DORMANT BRANCH: the repeated-knot grouping/skip lines never execute, "
                "even for tampered repeating vectors",
                repeat_hits)
    probe.check(all(row["non_monotone_return_executed"] for row in repeat_hits.values()),
                "the strict-monotone gate is what rejects every repeat")

    # ---- Q4: can the evaluator evaluate a repeated-knot vector? ------------
    evaluator_errors = {}
    for name, tampered in repeat_patterns(cps, legal_knots).items():
        spline = build_spline(cps, legal_knots)
        spline.position._knots = list(tampered)
        errors = 0
        points = 0
        for step in range(41):
            try:
                spline.position_at(spline.duration * step / 40.0)
                points += 1
            except SplineError:
                errors += 1
        evaluator_errors[name] = {"spline_errors": errors, "evaluated": points}
    probe.observe("tampered_evaluator_errors", evaluator_errors)
    probe.check(any(row["spline_errors"] > 0 for row in evaluator_errors.values()),
                "the FP evaluator itself raises SplineError (division by zero) on some "
                "tampered repeated-knot vectors, so repeated-knot evaluation is out of "
                "contract",
                evaluator_errors)

    # ---- Q5: shifted and non-uniform layouts ------------------------------
    shifted = [value - 7.5 for value in legal_knots]
    shifted_spline = build_spline(cps, shifted)
    shifted_cert = certify_continuous_clearance(shifted_spline)
    probe.check(shifted_cert.domain_start_u == shifted[ORDER]
                and shifted_cert.domain_end_u == shifted[len(cps)]
                and shifted_cert.interval_count == len(cps) - ORDER,
                "shifted domain: cover == [u_p, u_(m-p)] and full interval count",
                {"start": shifted_cert.domain_start_u, "end": shifted_cert.domain_end_u})
    report = assess_spline_clearance(shifted_spline)
    probe.check(report.start_point == tuple(shifted_spline.position_at(0.0))
                and report.end_point == tuple(shifted_spline.position_at(shifted_spline.duration)),
                "shifted domain: endpoints still evaluated exactly by the sampled gate")

    nonuniform = list(legal_knots)
    for index in range(ORDER + 1, len(nonuniform)):
        nonuniform[index] += 0.05 * (index - ORDER)
    nonuniform_spline = build_spline(cps, nonuniform)
    nonuniform_cert = certify_continuous_clearance(nonuniform_spline)
    probe.check(nonuniform_cert.domain_start_u == nonuniform[ORDER]
                and nonuniform_cert.domain_end_u == nonuniform[len(cps)]
                and nonuniform_cert.interval_count == len(cps) - ORDER
                and tuple(nonuniform_cert.intervals)
                == tuple((nonuniform[j], nonuniform[j + 1], j, j)
                         for j in range(ORDER, len(cps))),
                "lengthenTime-shaped non-uniform layout: cover and windows exact")

    upstream = uniform_knots(cps, 0.1)
    probe.check(upstream[0] < upstream[ORDER] and upstream[-1] > upstream[len(cps)],
                "the real upstream layout is NOT clamped (extra knots outside the domain)",
                {"u0": upstream[0], "u_p": upstream[ORDER],
                 "u_m_p": upstream[len(cps)], "u_m": upstream[-1]})
    probe.note("Q2/Q3 is a dynamic dead-branch proof: source lines are located by text, "
               "then executed line numbers are collected with sys.settrace.  The "
               "repeated-knot grouping and zero-length-span skip can never run because "
               "the strict-monotone gate returns first for every repeat, so the "
               "docstring/contract claim that grouping 'keeps the bound sound' describes "
               "an inoperative path.  Behaviour is still fail-closed.")
    return probe.finish()


if __name__ == "__main__":
    raise SystemExit(main())
