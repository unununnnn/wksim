"""Independent admission-safeguard review tests (cb-admission-review-20260913-01).

Runs the REAL joint_profile._mixed_proofs validator against the real shared
fixture helper (validation.test_joint_profile._mixed_proof_fixture) - no
validator monkeypatching.  Where the fixture lacks a knob, this module re-pins
the mutated artifact chain honestly: mutate JSON -> rewrite file -> recompute
sha -> update the dependent audit/pin digests, so the validator reaches the
targeted check instead of dying on an early pin mismatch.

Covered here (gaps after validation/test_joint_profile.py):
- both diagnostic markers (rate_timing_probe, group_work_timing) rejected on
  key PRESENCE for values True / False / None / {};
- each pacer source (joint_rate.py, joint_rate_probe.py) missing, flight-hash
  tampered, and retained-snapshot tampered;
- admission source-pin binding a pacer with a wrong digest (explicit message);
- unbound message candidate in a legacy proof (explicit message).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from Simulator.wksim_runtime import joint_profile as profile  # noqa: E402
from validation.test_joint_profile import _mixed_proof_fixture, PACERS  # noqa: E402

MARKERS = ("rate_timing_probe", "group_work_timing")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _write_json(path, obj):
    data = json.dumps(obj, indent=1, sort_keys=True).encode()
    path.write_bytes(data)
    return _sha(data)


def repin_result(p, root, run_index, mutate):
    """Mutate result.json consistently through audit and pins."""
    run = root / ("run%d" % run_index)
    pin = p["evidence"][run_index]
    flight = json.loads((run / "result.json").read_text())
    mutate(flight)
    result_sha = _write_json(run / "result.json", flight)
    pin["result"]["sha256"] = result_sha
    audit = json.loads((run / "audit.json").read_text())
    audit["result_sha256"] = result_sha
    pin["audit"]["sha256"] = _write_json(run / "audit.json", audit)
    return flight


def repin_admission(p, root, run_index, mutate):
    """Mutate experimental-admission.json consistently through audit and pins."""
    run = root / ("run%d" % run_index)
    pin = p["evidence"][run_index]
    admission = json.loads((run / "experimental-admission.json").read_text())
    mutate(admission)
    admission_sha = _write_json(run / "experimental-admission.json", admission)
    pin["admission"]["sha256"] = admission_sha
    flight = json.loads((run / "result.json").read_text())
    flight["mixed_admission"] = admission
    result_sha = _write_json(run / "result.json", flight)
    pin["result"]["sha256"] = result_sha
    audit = json.loads((run / "audit.json").read_text())
    audit["evidence_sha256"]["experimental-admission.json"] = admission_sha
    audit["result_sha256"] = result_sha
    pin["audit"]["sha256"] = _write_json(run / "audit.json", audit)
    return admission


class AdmissionSafeguardReviewTests(unittest.TestCase):
    """Real validator over the real fixture; independent of the upstream file."""

    def test_positive_fixture_passes_real_validator(self):
        with tempfile.TemporaryDirectory() as directory:
            p, records, identities, _, _ = _mixed_proof_fixture(directory)
            healthy, resources = profile._mixed_proofs(p, records, identities)
            self.assertEqual(healthy["task_profile"], profile.MIXED_TASKS[1])
            self.assertEqual(resources["model"]["library"], "model.so")

    def test_both_markers_rejected_on_key_presence_for_any_value(self):
        for marker in MARKERS:
            for value in (True, False, None, {}):
                with self.subTest(marker=marker, value=value), \
                        tempfile.TemporaryDirectory() as directory:
                    p, records, identities, _, _ = _mixed_proof_fixture(
                        directory, marker=(marker, value))
                    with self.assertRaisesRegex(
                            ValueError, "cannot include " + marker):
                        profile._mixed_proofs(p, records, identities)

    def test_each_pacer_missing_tampered_or_retained_tampered(self):
        for name in PACERS:
            with self.subTest(pacer=name, mode="missing"), \
                    tempfile.TemporaryDirectory() as directory:
                p, records, identities, _, flights = _mixed_proof_fixture(
                    directory, drop=(name,))
                self.assertNotIn(name, flights[0]["source_sha256"])
                with self.assertRaisesRegex(
                        ValueError, "Missing executed mixed proof source identity"):
                    profile._mixed_proofs(p, records, identities)
            with self.subTest(pacer=name, mode="flight-hash-tampered"), \
                    tempfile.TemporaryDirectory() as directory:
                p, records, identities, _, _ = _mixed_proof_fixture(
                    directory, tamper_flight_hash=name)
                with self.assertRaisesRegex(
                        ValueError, "Retained executed source is not sealed"):
                    profile._mixed_proofs(p, records, identities)
            with self.subTest(pacer=name, mode="retained-snapshot-tampered"), \
                    tempfile.TemporaryDirectory() as directory:
                p, records, identities, root, _ = _mixed_proof_fixture(directory)
                seal = root / "run0" / (
                    "source__" + name.replace("/", "__") + ".txt")
                seal.write_bytes(b"tampered retained source")
                with self.assertRaisesRegex(
                        ValueError, "Raw flight evidence differs"):
                    profile._mixed_proofs(p, records, identities)

    def test_admission_pin_binding_names_tampered_pacer(self):
        for name in PACERS:
            with self.subTest(pacer=name), \
                    tempfile.TemporaryDirectory() as directory:
                p, records, identities, root, _ = _mixed_proof_fixture(directory)

                def tamper(admission):
                    admission["identities"]["source_sha256"][name] = "0" * 64
                repin_admission(p, root, 0, tamper)
                with self.assertRaisesRegex(
                        ValueError, "Admission/execution source differs: "
                        + name.replace("/", r"\/")):
                    profile._mixed_proofs(p, records, identities)

    def test_unbound_message_candidate_rejected_with_explicit_message(self):
        with tempfile.TemporaryDirectory() as directory:
            p, records, identities, root, _ = _mixed_proof_fixture(directory)

            def add_candidate(flight):
                flight["message_candidate"] = {
                    "root": "/unbound", "packages": {}}
            repin_result(p, root, 0, add_candidate)
            with self.assertRaisesRegex(
                    ValueError, "Unbound message candidate in legacy mixed proof"):
                profile._mixed_proofs(p, records, identities)


if __name__ == "__main__":
    unittest.main()
