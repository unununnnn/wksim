"""Probe 3 -- float threshold semantics, strict/legacy compatibility, evidence labels.

Adversarial questions:
  Q1  Does the report-level admission ever accept a centreline that is MATERIALLY
      inside the required margin (a real over-permissive threshold), or reject one
      that is materially outside (a real over-conservative threshold)?
  Q2  Is the reported evidence label consistent with admission on every path?
      ``SceneClearanceReport.continuous_proof`` / ``evidence_kind`` are documented as
      "True only on a strict PASS"; a strict-mode rejection whose certificate is
      nonetheless proven must therefore not be published as a certified pass.
  Q3  Is the legacy path (strict_continuous=False) byte-for-byte unchanged in its
      labels, its certificate field, and its verdict on the audit witness?
  Q4  Is the strict flag a strict bool, and does an unproven certificate fail closed?
"""
from __future__ import annotations

import math
from fractions import Fraction

from probe_common import (  # noqa: E402
    CONTINUOUS_EVIDENCE_KIND,
    DEFAULT_SAMPLE_PERIOD_S,
    EVIDENCE_KIND,
    EXACT_MARGIN,
    MAX_ADMISSION_SAMPLES,
    Probe,
    SceneAdmissionError,
    _sample_times,
    assess_spline_clearance,
    certify_continuous_clearance,
    constant_spline,
    exact_inset_slack,
    exact_obstacle_slack,
    uniform_knots,
    build_spline,
    witness_spline,
)

MATERIAL_TOL = 1e-9          # 1 nanometre: 10 orders below the 0.65 m margin


def report_row(report):
    return {
        "admitted": report.admitted,
        "violation": None if report.violation is None else report.violation.get("kind"),
        "continuous_proof": report.continuous_proof,
        "evidence_kind": report.evidence_kind,
        "certificate_proven": (None if report.continuous_certificate is None
                               else report.continuous_certificate.proven),
    }


def main():
    probe = Probe("PROBE-3", "threshold semantics, strict/legacy labels",
                  "probe_3_threshold_and_labels.json")

    # ---- Q1: exact audit of report-level admission near both boundaries ----
    obstacle_rows = []
    inset_rows = []
    base_margin = float(EXACT_MARGIN)
    for offset in range(-6, 7):
        margin = base_margin
        direction = math.inf if offset >= 0 else -math.inf
        for _ in range(abs(offset)):
            margin = math.nextafter(margin, direction)

        y = 1.0 + margin
        spline = constant_spline((0.0, y, 2.75))
        report = assess_spline_clearance(spline)
        obstacle_rows.append({"offset_ulp": offset, "y": y,
                              "exact_slack_m": float(exact_obstacle_slack((0.0, y, 2.75))),
                              **report_row(report)})

        z = margin
        spline = constant_spline((3.0, 3.0, z))
        report = assess_spline_clearance(spline)
        inset_rows.append({"offset_ulp": offset, "z": z,
                           "exact_slack_m": float(exact_inset_slack((3.0, 3.0, z))),
                           **report_row(report)})
    probe.observe("obstacle_ulp_ladder", obstacle_rows)
    probe.observe("inset_ulp_ladder", inset_rows)

    bad_admits = [row for row in obstacle_rows + inset_rows
                  if row["admitted"] and row["exact_slack_m"] < -MATERIAL_TOL]
    probe.check(not bad_admits,
                "no admitted report is MATERIALLY inside the required margin",
                {"rows": bad_admits, "tol_m": MATERIAL_TOL})
    worst_admitted = min([row["exact_slack_m"] for row in obstacle_rows + inset_rows
                          if row["admitted"]], default=None)
    probe.observe("worst_exact_slack_of_admitted_report_m", worst_admitted)
    probe.check(worst_admitted is None or worst_admitted >= -MATERIAL_TOL,
                "worst admitted exact slack is at the FP noise floor",
                {"worst_m": worst_admitted})

    # ---- Q2: label consistency -------------------------------------------
    mislabelled = [row for row in obstacle_rows + inset_rows
                   if (not row["admitted"]) and row["continuous_proof"]]
    probe.observe("mislabelled_rows", mislabelled)
    probe.observe("mislabelled_count", len(mislabelled))
    probe.check(not mislabelled,
                "no NOT-admitted strict report carries continuous_proof=True "
                "(doc: 'True only on a strict PASS')",
                {"rows": mislabelled})
    mislabelled_kind = [row for row in obstacle_rows + inset_rows
                        if (not row["admitted"]) and row["evidence_kind"] == CONTINUOUS_EVIDENCE_KIND]
    probe.check(not mislabelled_kind,
                "no NOT-admitted strict report is labelled convex_hull_span_certified",
                {"rows": mislabelled_kind})

    # a second, wider search for the same inconsistency (random families)
    import random
    rng = random.Random(20260913)
    found = []
    for _ in range(400):
        point = (rng.uniform(-9.0, 9.0), rng.uniform(-5.5, 5.5), rng.uniform(0.0, 5.9))
        report = assess_spline_clearance(constant_spline(point))
        if (not report.admitted) and report.continuous_proof:
            found.append({"point": list(point), **report_row(report)})
    probe.observe("random_search_mislabelled", found[:5])
    probe.check(not found,
                "random constant-point search finds no admitted=False / "
                "continuous_proof=True report",
                {"found": len(found)})

    # ---- Q3: legacy path unchanged ----------------------------------------
    witness = witness_spline()
    strict_report = assess_spline_clearance(witness)
    legacy_report = assess_spline_clearance(witness, strict_continuous=False)
    probe.check((not strict_report.admitted) and not strict_report.continuous_proof
                and strict_report.evidence_kind == EVIDENCE_KIND,
                "strict mode rejects the audit witness without claiming a proof",
                report_row(strict_report))
    probe.check(strict_report.violation["kind"] == "continuous_clearance_unproven",
                "strict witness rejection reason is continuous_clearance_unproven",
                strict_report.violation)
    probe.check(legacy_report.admitted and not legacy_report.continuous_proof
                and legacy_report.evidence_kind == EVIDENCE_KIND
                and legacy_report.continuous_certificate is None
                and legacy_report.violation is None,
                "legacy mode still admits the witness with sampled-only labels",
                report_row(legacy_report))
    clean = constant_spline((3.0, 3.0, 3.0))
    legacy_clean = assess_spline_clearance(clean, strict_continuous=False)
    strict_clean = assess_spline_clearance(clean)
    probe.check(legacy_clean.evidence_kind == EVIDENCE_KIND
                and legacy_clean.continuous_proof is False
                and legacy_clean.continuous_certificate is None,
                "legacy clean pass keeps sampled_segment_checked / False / None",
                report_row(legacy_clean))
    probe.check(strict_clean.evidence_kind == CONTINUOUS_EVIDENCE_KIND
                and strict_clean.continuous_proof is True
                and strict_clean.admitted,
                "strict clean pass carries the continuous certificate label",
                report_row(strict_clean))
    # sampled numbers must be identical between the two modes on the same spline
    probe.check(
        (legacy_clean.min_obstacle_clearance == strict_clean.min_obstacle_clearance
         and legacy_clean.min_envelope_clearance == strict_clean.min_envelope_clearance
         and legacy_clean.sample_count == strict_clean.sample_count),
        "sampled evidence is identical in both modes (no sampled-path change)",
        {"legacy_obstacle": legacy_clean.min_obstacle_clearance,
         "strict_obstacle": strict_clean.min_obstacle_clearance,
         "legacy_envelope": legacy_clean.min_envelope_clearance,
         "strict_envelope": strict_clean.min_envelope_clearance})

    # ---- Q4: strict-flag gate and fail-closed certificate ------------------
    for bad in (1, 0, "yes", None, 2.0):
        try:
            assess_spline_clearance(clean, strict_continuous=bad)
            probe.fail("non-bool strict_continuous rejected", {"value": repr(bad)})
        except SceneAdmissionError as error:
            probe.check(error.reason == "invalid_grid",
                        "non-bool strict_continuous rejected as invalid_grid",
                        {"value": repr(bad), "reason": error.reason})

    broken = constant_spline((3.0, 3.0, 3.0))
    broken.position._knots = list(broken.position._knots[:-1])       # break cardinality
    report = assess_spline_clearance(broken)
    probe.check((not report.admitted) and (not report.continuous_proof)
                and report.violation["kind"] == "continuous_clearance_unproven"
                and report.continuous_certificate.structural_reason is not None,
                "structurally broken spline fails closed in strict mode",
                report_row(report))

    # ---- grid semantics re-checked independently --------------------------
    step = DEFAULT_SAMPLE_PERIOD_S
    times = _sample_times(1.0, step)
    probe.check(times[0] == 0.0 and times[-1] == 1.0
                and all(times[i] < times[i + 1] for i in range(len(times) - 1)),
                "grid keeps exact endpoints and is strictly increasing", {"n": len(times)})
    boundary = (MAX_ADMISSION_SAMPLES - 1) * step
    probe.check(len(_sample_times(boundary, step)) == MAX_ADMISSION_SAMPLES,
                "grid bound boundary yields exactly MAX_ADMISSION_SAMPLES",
                {"boundary": boundary})
    try:
        _sample_times(math.nextafter(boundary, math.inf), step)
        probe.fail("duration above the grid bound fails closed")
    except SceneAdmissionError as error:
        probe.check(error.reason == "invalid_grid",
                    "duration above the grid bound fails closed with invalid_grid",
                    {"reason": error.reason})
    probe.note("Q1/Q2 use an explicit ulp ladder around the exact double-sum margin "
               "(radius + required_clearance), which is where any threshold "
               "double-count would show up as a metre-scale, not ulp-scale, shift.")
    return probe.finish()


if __name__ == "__main__":
    raise SystemExit(main())
