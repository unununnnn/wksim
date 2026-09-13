"""Adversarial offline regression tests for the #33 mixed evidence-packet classifier.

The classifier is a fail-closed pre-filter over committed contracts.  It never
promotes #33/#84 and never launches ROS/FC/native/model/UE/MATLAB.  Packets are
synthetic fixtures, not flight proof.

Coverage is mapped to the independent review findings in
``validation/coordination/codebuddy-33-mixed-review-20260914-01``:

* D1 - ``--directory`` is a real two-run packet contract, never a constant.
* D2 - retained raw evidence maps (``audit['evidence_sha256']``) are required.
* D3 - absent ``run_id``/``scene_epoch``/PX4 is rejected, never treated as a match.
* D4 - result/audit/admission/root/manifests/candidate/control/message/source
  bindings are required before ``current_combo_not_accepted``.
* D5 - rejected classifications return a non-zero CLI exit.
* D6 - catalog-row truth and packet-specific catalog binding are reported
  separately.

Because the committed FINAL AP/control/message artifacts live on the Linux host,
``FinalCase`` patches the tool's FINAL_* literals with the digests of the files
the fixture itself writes, so the whole proof chain is exercised offline.  The
real literals are asserted separately and are never replaced globally.
"""
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
# Direct-script execution on a clean POSIX host puts ``validation/`` on sys.path
# instead of the repo root, so the repo root must be inserted before the package
# imports below (module execution already provides it, hence the membership test).
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Simulator.wksim_runtime import joint_profile as joint

from tools import audit_33_mixed_packet as tool
from tools.audit_33_mixed_packet import (
    CLASSIFIED,
    DIAGNOSTIC_MARKERS,
    EXIT_CLASSIFIED,
    EXIT_REJECTED,
    SCHEMA,
    classify,
    classify_directory,
    classify_path,
    main,
)


# Identity strings for the synthetic installs.  They are root-independent so two
# builders in different run directories stay byte-identical.
MESSAGE_ROOT = ROOT / "validation" / "synthetic-message-install"
CONTROL_ROOT = ROOT / "validation" / "synthetic-control-install"
AP_ROOT = ROOT / "validation" / "synthetic-ap-install"
SOURCE_FILES = (
    "tools/run_joint_flight.py",
    "tools/ap_mixed_candidate.py",
    "tools/prepare_ap_mixed_candidate.py",
    "tools/verify_ap_pv_candidate.py",
    "Simulator/wksim_runtime/joint_profile.py",
    "Simulator/wksim_core/model.py",
    "Simulator/wksim_runtime/joint_rate.py",
    "Simulator/wksim_runtime/joint_rate_probe.py",
)


def _literals(relative):
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    values = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            values[node.targets[0].id] = node.value.value
    return values


MIXED_SRC = _literals("tools/ap_mixed_candidate.py")
AUDIT_SRC = _literals("tools/audit_mixed_control.py")
FINAL_AP = MIXED_SRC["FINAL_AP_SHA"]
FINAL_CONTROL = MIXED_SRC["FINAL_CONTROL_SHA"]
FINAL_MESSAGE = MIXED_SRC["FINAL_MESSAGE_SHA"]
LEGACY_MIXED_CONTROL = MIXED_SRC["LEGACY_CONTROL_SHA"]
HISTORICAL_PV_CONTROL = AUDIT_SRC["HISTORICAL_PV_CONTROL_SHA"]
PREVIOUS_PV_CONTROL = AUDIT_SRC["PREVIOUS_PV_CONTROL_SHA"]
PV_FIRMWARE = AUDIT_SRC["PV_SHA"]


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _digest_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write(path, obj):
    raw = json.dumps(obj, sort_keys=True).encode("utf-8")
    Path(path).write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _never_accepted(report):
    return (
        report["acceptance_eligible"] is False
        and report["issue_33_accepted"] is False
        and report["issue_84_accepted"] is False
        and report.get("issues_accepted") is not True
    )


def _capability(task):
    if task == joint.MIXED_TASKS[0]:
        return dict(
            profile=task,
            position_axes="xyz",
            velocity_axes="xyz",
            yaw=True,
            acceleration=False,
            yaw_rate=False,
            mixed_axes=False,
            arducopter_type_mask=2496,
        )
    return dict(
        profile=task,
        position_axes="z",
        velocity_axes="xy",
        yaw=True,
        yaw_rate=False,
        acceleration=False,
        terrain=False,
        arducopter_type_mask=2531,
        native_submode=7,
        vertical_velocity_avoidance=False,
    )


def _silent_main(argv):
    with mock.patch("sys.stdout", io.StringIO()):
        return main(argv)


class PacketBuilder:
    """Self-consistent synthetic two-task packet.

    Every retained digest is derived from the bytes this builder writes, so the
    packet satisfies the committed proof chain once ``FinalCase`` patches the
    FINAL_* literals to ``builder.triple``.  Without that substitution the real
    committed digests cannot match any locally written file, and the packet is
    correctly rejected for missing retained evidence.
    """

    def __init__(self, root, *, combo="final"):
        self.root = Path(root).resolve()
        self.catalog = joint.select_profile(joint.MIXED_PROFILE)
        self.legacy = joint.select_profile(joint.LEGACY_PROFILE)
        self.runs = {task: self.root / task for task in joint.MIXED_TASKS}
        for run in self.runs.values():
            run.mkdir(parents=True, exist_ok=True)
        self.message_root = MESSAGE_ROOT
        self.candidate = {
            "version": 1,
            "root": str(MESSAGE_ROOT),
            "packages": {
                name: {
                    "prefix": str(MESSAGE_ROOT / "install" / name),
                    "installed_sha256": _digest_text("package " + name),
                }
                for name in ("prometheus_msgs", "wksim_msgs")
            },
        }
        self.message_sha = self._shared("message-build.json", self.candidate)
        self.control_record = {
            "root": str(CONTROL_ROOT),
            "message_candidate": json.loads(json.dumps(self.candidate)),
            "message_manifest_path": str(MESSAGE_ROOT / "message-build.json"),
            "message_manifest_sha256": self.message_sha,
        }
        self.control_sha = self._shared("control-build.json", self.control_record)
        self.mixed_source_sha = self._shared(
            "mixed-source.json",
            {"schema_version": 1, "status": "source-only-not-built-not-admitted"},
        )
        self.baseline_pv_sha = self._shared(
            "baseline-pv-build.json", {"schema_version": 1, "status": "built-not-admitted"}
        )
        self.ap_record = {
            "schema_version": 1,
            "status": "built-not-admitted",
            "baseline_manifest_sha256": self.baseline_pv_sha,
            "candidate_root": str(AP_ROOT),
        }
        self.ap_sha = self._shared("ap-build.json", self.ap_record)
        self.native = {
            "candidate": json.loads(json.dumps(self.ap_record)),
            "binary": {
                "path": str(AP_ROOT / "build/sitl/bin/arducopter"),
                "sha256": _digest_text("native binary"),
            },
            "source_files": 24593,
            "source_repositories": 22,
            "source_manifest_sha256": self.mixed_source_sha,
            "baseline_verification": {"baseline_manifest_sha256": self.baseline_pv_sha},
            "status": "verified-built-not-admitted",
            "production_admitted": False,
            "flown": False,
        }
        self.sources = {
            name: self._shared(
                "source__" + name.replace("/", "__") + ".txt",
                "synthetic executed source " + name,
            )
            for name in SOURCE_FILES
        }
        self.triple = {
            "ap": self.ap_sha,
            "control": self.control_sha,
            "message": self.message_sha,
        }
        self.identity = dict(self.triple, px4=self.catalog["manifests"]["px4"]["sha256"])
        self.px4_pin = json.loads(json.dumps(self.catalog["manifests"]["px4"]))
        self.ap_path = str(AP_ROOT / "mixed-build.json")
        self.control_path = str(CONTROL_ROOT / "build.json")
        self._apply(combo)
        self.packets = [self._one(task) for task in joint.MIXED_TASKS]

    def _shared(self, name, payload):
        raw = (
            payload.encode("utf-8")
            if isinstance(payload, str)
            else json.dumps(payload, sort_keys=True).encode("utf-8")
        )
        for run in self.runs.values():
            (run / name).write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def _apply(self, combo):
        if combo == "final":
            return
        if combo == "legacy":
            row = self.legacy["manifests"]
            self.identity.update(
                ap=row["ap"]["sha256"], control=row["control"]["sha256"], message="0" * 64
            )
            self.ap_path, self.control_path = row["ap"]["path"], row["control"]["path"]
        elif combo == "catalog":
            row = self.catalog["manifests"]
            self.identity.update(
                ap=row["ap"]["sha256"], control=row["control"]["sha256"], message="0" * 64
            )
            self.ap_path, self.control_path = row["ap"]["path"], row["control"]["path"]
        elif combo == "historical_mixed":
            self.identity.update(control=LEGACY_MIXED_CONTROL, message="0" * 64)
            self.control_path = "/root/wksim-joint-control-OEvS3W/build.json"
        elif combo == "wrong":
            self.identity.update(ap="e" * 64, control="f" * 64, message="1" * 64)
            self.ap_path = "/root/wksim-ap-other/mixed-build.json"
            self.control_path = "/root/wksim-joint-control-other/build.json"
        else:
            raise AssertionError(combo)

    def _one(self, task):
        run = self.runs[task]
        baseline = {
            "px4": json.loads(json.dumps(self.px4_pin)),
            "model": {
                "library": self.catalog["model_library"],
                "library_sha256": _digest_text("model library"),
            },
            "message_packages": {},
            "arducopter_agent": {"path": "ap-agent", "sha256": _digest_text("ap-agent")},
            "px4_agent": {"path": "px4-agent", "sha256": _digest_text("px4-agent")},
            "manifests": json.loads(json.dumps(self.catalog["manifests"])),
        }
        admission = {
            "task_profile": task,
            "ok": True,
            "experimental": True,
            "production_admitted": False,
            "flown": False,
            "children_created": 0,
            "reasons": [],
            "capability": _capability(task),
            "manifest_sha256": self.identity["ap"],
            "control_manifest_sha256": self.identity["control"],
            "manifest_path": self.ap_path,
            "control_manifest_path": self.control_path,
            "candidate": json.loads(json.dumps(self.ap_record)),
            "control_candidate": json.loads(json.dumps(self.control_record)),
            "candidate_verification": json.loads(json.dumps(self.native)),
            "message_candidate": json.loads(json.dumps(self.candidate)),
            "message_manifest_path": self.control_record["message_manifest_path"],
            "message_manifest_sha256": self.identity["message"],
            "identities": {
                "ap_mixed": json.loads(json.dumps(self.native)),
                "baseline": baseline,
                "source_sha256": dict(self.sources),
                "message_candidate": json.loads(json.dumps(self.candidate)),
            },
        }
        flight = {
            "status": "pass",
            "flight_completed": True,
            "source_unchanged": True,
            "control_shutdown_clean": True,
            "cleanup_errors": [],
            "task_profile": task,
            "run_id": "run-" + task,
            "scene_epoch": "epoch-" + task,
            "mixed_admission": json.loads(json.dumps(admission)),
            "manifest_sha256": {
                "ap": self.identity["ap"],
                "control": self.identity["control"],
                "message": self.identity["message"],
            },
            "control_candidate": json.loads(json.dumps(self.control_record)),
            "message_candidate": json.loads(json.dumps(self.candidate)),
            "model_build": json.loads(json.dumps(baseline["model"])),
            "source_sha256": dict(self.sources),
            "children": {
                "arducopter-control": {
                    "argv": [
                        "control",
                        "-p",
                        "arducopter_pv_profile:=" + joint.MIXED_TASKS[0],
                        "-p",
                        "arducopter_mixed_profile:=" + joint.MIXED_TASKS[1],
                    ]
                }
            },
        }
        audit = {
            "status": "pass",
            "outstanding_checks": [],
            "task_profile": task,
            "run_id": flight["run_id"],
            "scene_epoch": flight["scene_epoch"],
            "identity": {
                "control_profiles": {
                    "arducopter_pv_profile": joint.MIXED_TASKS[0],
                    "arducopter_mixed_profile": joint.MIXED_TASKS[1],
                }
            },
            "evidence_sha256": {
                "ap-build.json": self.identity["ap"],
                "control-build.json": self.identity["control"],
                "message-build.json": self.identity["message"],
                "mixed-source.json": self.native["source_manifest_sha256"],
                "baseline-pv-build.json": self.ap_record["baseline_manifest_sha256"],
                **{
                    "source__" + name.replace("/", "__") + ".txt": value
                    for name, value in self.sources.items()
                },
            },
        }
        return run, admission, flight, audit

    def seal(self, packets=None):
        pins = []
        for run, admission, flight, audit in packets or self.packets:
            admission_sha = _write(run / "experimental-admission.json", admission)
            result_sha = _write(run / "result.json", flight)
            audit["result_sha256"] = result_sha
            audit["evidence_sha256"]["experimental-admission.json"] = admission_sha
            audit_sha = _write(run / "audit.json", audit)
            pins.append(
                {
                    "task_profile": flight["task_profile"],
                    "result": {"path": str(run / "result.json"), "sha256": result_sha},
                    "audit": {"path": str(run / "audit.json"), "sha256": audit_sha},
                    "admission": {
                        "path": str(run / "experimental-admission.json"),
                        "sha256": admission_sha,
                    },
                }
            )
        return pins


class FinalCase:
    """Patch the tool's FINAL_* literals to the fixture's self-written digests."""

    def __init__(self, root, *, combo="final"):
        self.builder = PacketBuilder(root, combo=combo)
        self._patch = mock.patch.multiple(
            tool,
            FINAL_AP_SHA=self.builder.triple["ap"],
            FINAL_CONTROL_SHA=self.builder.triple["control"],
            FINAL_MESSAGE_SHA=self.builder.triple["message"],
        )

    def __enter__(self):
        self._patch.start()
        return self.builder

    def __exit__(self, *exc):
        self._patch.stop()
        return False


def _admitted(builder):
    """The admission file and its mirrored copy inside the flown result."""
    for _, admission, flight, _ in builder.packets:
        yield admission, flight["mixed_admission"]


def _set_identity(builder, *, ap=None, control=None, message=None, ap_path=None, control_path=None):
    for _, admission, flight, _ in builder.packets:
        for target in (admission, flight["mixed_admission"]):
            if ap is not None:
                target["manifest_sha256"] = ap
            if control is not None:
                target["control_manifest_sha256"] = control
            if message is not None:
                target["message_manifest_sha256"] = message
            if ap_path is not None:
                target["manifest_path"] = ap_path
            if control_path is not None:
                target["control_manifest_path"] = control_path
        if ap is not None:
            flight["manifest_sha256"]["ap"] = ap
        if control is not None:
            flight["manifest_sha256"]["control"] = control
        if message is not None:
            flight["manifest_sha256"]["message"] = message
    return builder


def _set_px4(builder, sha, path):
    for admission, mirrored in _admitted(builder):
        for target in (admission, mirrored):
            baseline = target["identities"]["baseline"]
            baseline["manifests"]["px4"].update(sha256=sha, path=path)
            baseline["px4"].update(sha256=sha, path=path)
    return builder


def _set_control_fields(builder, **fields):
    for _, admission, flight, _ in builder.packets:
        for target in (admission, flight["mixed_admission"]):
            target["control_candidate"].update(json.loads(json.dumps(fields)))
        flight["control_candidate"].update(json.loads(json.dumps(fields)))
    return builder


def _set_argv(builder, argv):
    for _, _, flight, _ in builder.packets:
        flight["children"]["arducopter-control"]["argv"] = list(argv)
    return builder


def _repin(pins, index, key, mutate):
    path = Path(pins[index][key]["path"])
    obj = json.loads(path.read_text(encoding="utf-8"))
    mutate(obj)
    raw = json.dumps(obj, sort_keys=True).encode("utf-8")
    path.write_bytes(raw)
    pins[index][key]["sha256"] = hashlib.sha256(raw).hexdigest()
    return pins


def _splice_json(path, suffix):
    raw = Path(path).read_bytes()
    if not raw.endswith(b"}"):
        raise AssertionError("fixture JSON does not end with }")
    Path(path).write_bytes(raw[:-1] + suffix)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _deep_json(depth, leaf="0"):
    """A syntactically valid JSON document nested ``depth`` objects deep.

    Built by string repetition so the fixture itself never recurses.
    """
    return '{"n":' * depth + leaf + "}" * depth


class ContractBindingTests(unittest.TestCase):
    def test_classifier_reuses_live_catalog_and_final_literals(self):
        mixed = joint.select_profile(joint.MIXED_PROFILE)
        legacy = joint.select_profile(joint.LEGACY_PROFILE)
        self.assertEqual(mixed["id"], joint.MIXED_PROFILE)
        self.assertEqual(mixed["evidence"], [])
        self.assertEqual(mixed["manifests"]["ap"]["sha256"], FINAL_AP)
        self.assertNotEqual(mixed["manifests"]["control"]["sha256"], FINAL_CONTROL)
        self.assertEqual(legacy["control_source"], "sealed_legacy")
        self.assertEqual(tool.FINAL_AP_SHA, FINAL_AP)
        self.assertEqual(tool.FINAL_CONTROL_SHA, FINAL_CONTROL)
        self.assertEqual(tool.FINAL_MESSAGE_SHA, FINAL_MESSAGE)

    def test_diagnostic_markers_come_from_the_committed_contract_tuple(self):
        """The marker guard must read a real tuple literal, not a comment."""
        tree = ast.parse(
            (ROOT / "Simulator/wksim_runtime/joint_profile.py").read_text(encoding="utf-8")
        )
        tuples = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Tuple) and node.elts and all(
                isinstance(item, ast.Constant) and isinstance(item.value, str)
                for item in node.elts
            ):
                tuples.add(tuple(item.value for item in node.elts))
        self.assertIn(DIAGNOSTIC_MARKERS, tuples)
        self.assertEqual(
            DIAGNOSTIC_MARKERS,
            ("rate_timing_probe", "group_work_timing", "perf_switch_capture"),
        )

    def test_schema_and_exit_codes_never_name_acceptance(self):
        self.assertEqual(SCHEMA, "wksim.33-mixed-packet-classification.v2")
        self.assertNotIn("accepted", SCHEMA)
        self.assertEqual((EXIT_CLASSIFIED, EXIT_REJECTED), (0, 2))


class SyntheticFinalTests(unittest.TestCase):
    def test_current_two_task_packet_is_classified_but_never_accepted(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            report = classify({"evidence": builder.seal()})
            self.assertEqual(report["classification"], CLASSIFIED)
            self.assertEqual(report["status"], "classified_not_accepted")
            self.assertEqual(report["exit_code"], EXIT_CLASSIFIED)
            self.assertTrue(_never_accepted(report))
            self.assertEqual(report["schema"], SCHEMA)
            self.assertEqual(report["combo"]["ap"], builder.ap_sha)
            self.assertEqual(report["combo"]["control"], builder.control_sha)
            self.assertEqual(report["combo"]["message"], builder.message_sha)
            self.assertEqual(report["combo"]["px4"], builder.px4_pin["sha256"])
            self.assertTrue(report["reasons"])
            self.assertIn("unaccepted", " ".join(report["reasons"]))
            self.assertFalse(report["verification"]["catalog_candidates_verified"])

    def test_real_literals_reject_the_synthetic_retained_chain(self):
        """FINAL-shaped identity alone is not enough without matching evidence."""
        with tempfile.TemporaryDirectory() as directory:
            builder = PacketBuilder(directory)
            _set_identity(builder, ap=FINAL_AP, control=FINAL_CONTROL, message=FINAL_MESSAGE)
            report = classify({"evidence": builder.seal()})
            self.assertEqual(report["classification"], "incomplete_evidence")
            self.assertEqual(report["exit_code"], EXIT_REJECTED)
            self.assertTrue(_never_accepted(report))

    def test_single_task_pin_is_incomplete_evidence(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for pin in builder.seal():
                with self.subTest(task=pin["task_profile"]):
                    report = classify(pin)
                    self.assertEqual(report["classification"], "incomplete_evidence")
                    self.assertIn("both", " ".join(report["reasons"]).lower())
                    self.assertEqual(report["exit_code"], EXIT_REJECTED)

    def test_catalog_row_truth_is_reported_separately_from_packet_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog_packet = classify(
                {"evidence": PacketBuilder(directory, combo="catalog").seal()}
            )
        self.assertEqual(catalog_packet["classification"], "historical_combo")
        self.assertEqual(
            catalog_packet["packet_catalog_binding"],
            {
                "ap_matches_catalog": True,
                "control_matches_catalog": True,
                "px4_matches_catalog": True,
            },
        )
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            packet = classify({"evidence": builder.seal()})
        self.assertEqual(packet["classification"], CLASSIFIED)
        self.assertEqual(
            packet["packet_catalog_binding"],
            {
                "ap_matches_catalog": False,
                "control_matches_catalog": False,
                "px4_matches_catalog": True,
            },
        )
        # A catalog-row property must be identical for both packets.
        self.assertEqual(
            packet["catalog_has_evidence_rows"],
            catalog_packet["catalog_has_evidence_rows"],
        )
        self.assertEqual(
            packet["catalog_has_evidence_rows"],
            len(joint.select_profile(joint.MIXED_PROFILE)["evidence"]) == 2,
        )


class EvidenceChainTests(unittest.TestCase):
    """D2/D3/D4: every binding required before the strongest classification."""

    def _rejected(self, builder, expected=None):
        report = classify({"evidence": builder.seal()})
        self.assertIn(
            report["classification"],
            expected or ("incomplete_evidence", "malformed_identity", "missing_identity"),
        )
        self.assertNotEqual(report["classification"], CLASSIFIED)
        self.assertEqual(report["exit_code"], EXIT_REJECTED)
        self.assertTrue(_never_accepted(report))
        return report

    def test_retained_raw_evidence_map_is_required(self):
        # D2 probe: a single fabricated entry must not reach the strongest label.
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for _, _, _, audit in builder.packets:
                audit["evidence_sha256"] = {"ap-build.json": "0" * 64}
            report = self._rejected(builder)
            self.assertIn("Raw flight evidence differs", " ".join(report["reasons"]))
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            pins = builder.seal()
            _repin(pins, 0, "audit", lambda audit: audit.update(evidence_sha256={}))
            report = classify({"evidence": pins})
            self.assertEqual(report["classification"], "incomplete_evidence")
            self.assertIn("Missing raw flight evidence", " ".join(report["reasons"]))

    def test_retained_evidence_file_must_exist(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            pins = builder.seal()
            (Path(pins[0]["result"]["path"]).parent / "mixed-source.json").unlink()
            report = classify({"evidence": pins})
            self.assertEqual(report["classification"], "incomplete_evidence")
            self.assertEqual(report["exit_code"], EXIT_REJECTED)

    def test_audit_result_sha256_must_match_the_pinned_result(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            pins = builder.seal()
            _repin(pins, 0, "audit", lambda audit: audit.update(result_sha256="f" * 64))
            report = classify({"evidence": pins})
            self.assertEqual(report["classification"], "incomplete_evidence")
            self.assertIn("raw audit did not pass", " ".join(report["reasons"]))

    def test_flight_mixed_admission_must_equal_retained_admission(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for _, _, flight, _ in builder.packets:
                flight["mixed_admission"]["manifest_sha256"] = "0" * 64
            report = self._rejected(builder)
            self.assertIn("retained admission identity differs", " ".join(report["reasons"]))

    def test_cross_directory_pin_mix_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            first = PacketBuilder(Path(directory) / "a")
            second = PacketBuilder(Path(directory) / "b")
            with mock.patch.multiple(
                tool,
                FINAL_AP_SHA=first.triple["ap"],
                FINAL_CONTROL_SHA=first.triple["control"],
                FINAL_MESSAGE_SHA=first.triple["message"],
            ):
                pa, pb = first.seal(), second.seal()
                pin = {
                    "task_profile": pa[0]["task_profile"],
                    "result": pa[0]["result"],
                    "audit": pa[0]["audit"],
                    "admission": pb[0]["admission"],
                }
                report = classify({"evidence": [pin, pb[1]]})
            self.assertEqual(report["classification"], "incomplete_evidence")
            self.assertEqual(report["exit_code"], EXIT_REJECTED)

    def test_admission_must_live_in_the_result_root(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            pins = builder.seal()
            original = Path(pins[0]["admission"]["path"])
            moved = original.parent / "moved-admission.json"
            moved.write_bytes(original.read_bytes())
            original.unlink()
            pins[0]["admission"]["path"] = str(moved)
            report = classify({"evidence": pins})
            self.assertEqual(report["classification"], "incomplete_evidence")

    def test_candidate_record_must_match_its_retained_pv_baseline(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for admission, mirrored in _admitted(builder):
                for target in (admission, mirrored):
                    target["candidate"]["baseline_manifest_sha256"] = "9" * 64
            report = self._rejected(builder)
            self.assertIn("sealed source proof", " ".join(report["reasons"]))

    def test_flight_control_candidate_must_equal_the_admitted_control(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for _, _, flight, _ in builder.packets:
                flight["control_candidate"]["root"] = "/root/wksim-joint-control-other"
            report = self._rejected(builder)
            self.assertIn("AP/control pins", " ".join(report["reasons"]))

    def test_explicit_message_proof_is_required(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            _set_control_fields(
                builder, message_manifest_path=str(MESSAGE_ROOT / "other-message-build.json")
            )
            report = self._rejected(builder)
            self.assertIn("message proof", " ".join(report["reasons"]))

    def test_message_manifest_absence_is_missing_identity(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for _, admission, flight, _ in builder.packets:
                flight["manifest_sha256"].pop("message")
                admission.pop("message_manifest_sha256")
            report = self._rejected(builder, expected=("missing_identity",))
            self.assertIn("message", " ".join(report["reasons"]))

    def test_executed_source_must_be_sealed(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            name = "source__tools__run_joint_flight.py.txt"
            for _, _, _, audit in builder.packets:
                audit["evidence_sha256"].pop(name)
            report = self._rejected(builder)
            self.assertIn("not sealed", " ".join(report["reasons"]))

    def test_admission_and_execution_sources_must_agree(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for admission, mirrored in _admitted(builder):
                for target in (admission, mirrored):
                    target["identities"]["source_sha256"]["tools/run_joint_flight.py"] = "9" * 64
            report = self._rejected(builder)
            self.assertIn("Admission/execution source differs", " ".join(report["reasons"]))

    def test_argv_must_execute_both_capabilities(self):
        variants = {
            "missing -p": [
                "control",
                "arducopter_pv_profile:=" + joint.MIXED_TASKS[0],
                "-p",
                "arducopter_mixed_profile:=" + joint.MIXED_TASKS[1],
            ],
            "flag at index 0": [
                "arducopter_pv_profile:=" + joint.MIXED_TASKS[0],
                "-p",
                "arducopter_mixed_profile:=" + joint.MIXED_TASKS[1],
            ],
            "duplicate flag": [
                "control",
                "-p",
                "arducopter_pv_profile:=" + joint.MIXED_TASKS[0],
                "-p",
                "arducopter_pv_profile:=" + joint.MIXED_TASKS[0],
                "-p",
                "arducopter_mixed_profile:=" + joint.MIXED_TASKS[1],
            ],
            "non-str element": [
                "control",
                "-p",
                "arducopter_pv_profile:=" + joint.MIXED_TASKS[0],
                123,
                "-p",
                "arducopter_mixed_profile:=" + joint.MIXED_TASKS[1],
            ],
            "prefix trick": [
                "control",
                "-p",
                "arducopter_pv_profile:=" + joint.MIXED_TASKS[0] + "X",
                "-p",
                "arducopter_mixed_profile:=" + joint.MIXED_TASKS[1],
            ],
        }
        for label, argv in variants.items():
            with self.subTest(argv=label), tempfile.TemporaryDirectory() as directory:
                with FinalCase(directory) as builder:
                    _set_argv(builder, argv)
                    report = self._rejected(builder)
                    self.assertTrue(
                        "capability parameters" in " ".join(report["reasons"])
                        or "startswith" in " ".join(report["reasons"])
                    )

    def test_control_profile_binding_is_required(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for _, _, _, audit in builder.packets:
                audit["identity"]["control_profiles"] = {"arducopter_pv_profile": "other"}
            report = self._rejected(builder)
            self.assertIn("capability parameters", " ".join(report["reasons"]))

    def test_declared_task_must_equal_the_flown_task(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            pins = builder.seal()
            pins[0]["task_profile"] = joint.MIXED_TASKS[1]
            report = classify({"evidence": pins})
            self.assertIn(
                report["classification"],
                ("incomplete_evidence", "wrong_combo", "malformed_identity"),
            )
            self.assertNotEqual(report["classification"], CLASSIFIED)

    def test_manifest_paths_must_keep_the_committed_names(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            _set_identity(builder, control_path="/root/wksim-joint-control-other/not-a-build.json")
            report = self._rejected(builder)
            self.assertIn("control_manifest_path", " ".join(report["reasons"]))

    def test_committed_ap_manifest_path_must_match_its_pinned_descriptor(self):
        with tempfile.TemporaryDirectory() as directory:
            builder = PacketBuilder(directory)
            _set_identity(
                builder,
                ap=FINAL_AP,
                control=FINAL_CONTROL,
                message=FINAL_MESSAGE,
                ap_path="/root/wksim-ap-other/mixed-build.json",
            )
            report = self._rejected(builder)
            self.assertIn("Committed mixed AP manifest path", " ".join(report["reasons"]))

    def test_absent_run_id_and_scene_epoch_are_rejected(self):
        # D3 probe: absence in both objects must never compare as a match.
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for _, _, flight, audit in builder.packets:
                flight.pop("run_id")
                audit.pop("run_id")
                flight.pop("scene_epoch")
                audit.pop("scene_epoch")
            report = self._rejected(builder, expected=("missing_identity",))
            self.assertIn("run_id/scene_epoch is absent", " ".join(report["reasons"]))

    def test_empty_run_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for _, _, flight, audit in builder.packets:
                flight["run_id"] = ""
                audit["run_id"] = ""
            report = self._rejected(builder, expected=("missing_identity",))
            self.assertIn("run_id/scene_epoch is absent", " ".join(report["reasons"]))

    def test_empty_scene_epoch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for _, _, flight, audit in builder.packets:
                flight["scene_epoch"] = ""
                audit["scene_epoch"] = ""
            report = self._rejected(builder, expected=("missing_identity",))
            self.assertIn("run_id/scene_epoch is absent", " ".join(report["reasons"]))

    def test_run_id_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for _, _, _, audit in builder.packets:
                audit["run_id"] = "other-run"
            report = self._rejected(builder, expected=("malformed_identity",))
            self.assertIn("audit run identity differs", " ".join(report["reasons"]))

    def test_absent_px4_is_rejected(self):
        # D3 probe: the committed contract reads baseline.manifests.px4 directly.
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for admission, mirrored in _admitted(builder):
                for target in (admission, mirrored):
                    target["identities"]["baseline"]["manifests"].pop("px4")
            report = self._rejected(builder, expected=("missing_identity",))
            self.assertIn("px4 is absent", " ".join(report["reasons"]))

    def test_px4_identity_outside_the_catalog_pin_is_wrong_combo(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            _set_px4(builder, "a" * 64, "/root/wksim-px4-other/wksim-build.json")
            report = self._rejected(builder, expected=("wrong_combo",))
            self.assertFalse(report["packet_catalog_binding"]["px4_matches_catalog"])

    def test_px4_contradiction_with_its_manifest_descriptor_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for admission, mirrored in _admitted(builder):
                for target in (admission, mirrored):
                    target["identities"]["baseline"]["px4"]["sha256"] = "a" * 64
            report = self._rejected(builder, expected=("malformed_identity",))
            self.assertIn("PX4 identity contradicts", " ".join(report["reasons"]))

    def test_task_resource_mismatch_between_proofs_is_wrong_combo(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for _, admission, _, _ in builder.packets[1:]:
                baseline = admission["identities"]["baseline"]
                baseline["px4"]["sha256"] = "a" * 64
                baseline["manifests"]["px4"]["sha256"] = "a" * 64
            report = self._rejected(builder, expected=("wrong_combo",))
            self.assertIn("different resources", " ".join(report["reasons"]))

    def test_flight_diagnostic_markers_reject_any_value(self):
        for marker in DIAGNOSTIC_MARKERS:
            for value in (None, False, 0, "", "enabled", {"diagnostic": True}, []):
                with self.subTest(marker=marker, value=value):
                    with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
                        for _, _, flight, _ in builder.packets:
                            flight[marker] = value
                        report = classify({"evidence": builder.seal()})
                        self.assertEqual(report["classification"], "diagnostic_marker")
                        self.assertTrue(any(marker in reason for reason in report["reasons"]))
                        self.assertEqual(report["exit_code"], EXIT_REJECTED)
                        self.assertTrue(_never_accepted(report))

    def test_marker_near_miss_keys_are_not_markers(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for _, _, flight, _ in builder.packets:
                flight["rate_timing_probe "] = True
                flight["Rate_Timing_Probe"] = True
            report = classify({"evidence": builder.seal()})
            self.assertEqual(report["classification"], CLASSIFIED)

    def test_audit_and_admission_markers_follow_the_committed_contract(self):
        """The committed contract scans the flown result only (review I2)."""
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for _, _, _, audit in builder.packets:
                audit["group_work_timing"] = True
            report = classify({"evidence": builder.seal()})
            self.assertEqual(report["classification"], CLASSIFIED)
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for _, admission, flight, _ in builder.packets:
                admission["perf_switch_capture"] = True
                flight["mixed_admission"]["perf_switch_capture"] = True
            report = classify({"evidence": builder.seal()})
            self.assertEqual(report["classification"], CLASSIFIED)


class FailClosedShapeTests(unittest.TestCase):
    def test_malformed_json_duplicate_keys_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for label, text in (
                ("duplicate-key", '{"task_profile":"x","task_profile":"y"}'),
                ("NaN", '{"task_profile": NaN}'),
                ("Infinity", '{"task_profile": Infinity}'),
                ("-Infinity", '{"task_profile": -Infinity}'),
                ("overflow", '{"task_profile": 1e999}'),
                ("negative-overflow", '{"manifest_sha256": -1e999}'),
            ):
                with self.subTest(case=label):
                    path = root / (label + ".json")
                    path.write_text(text, encoding="utf-8")
                    report = classify_path(path)
                    self.assertEqual(report["classification"], "malformed_identity")
                    self.assertTrue(_never_accepted(report))
            self.assertEqual(classify("[]")["classification"], "malformed_identity")
            self.assertEqual(classify(1)["classification"], "malformed_identity")

    def test_duplicate_keys_inside_pinned_files_are_rejected(self):
        for key in ("result", "admission"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                with FinalCase(directory) as builder:
                    pins = builder.seal()
                    path = Path(pins[0][key]["path"])
                    raw = path.read_text(encoding="utf-8")
                    duplicate = sorted(json.loads(raw))[0]
                    path.write_text(
                        raw[:-1] + ', "%s": null}' % duplicate, encoding="utf-8"
                    )
                    pins[0][key]["sha256"] = _sha(path)
                    report = classify({"evidence": pins})
                    self.assertEqual(report["classification"], "malformed_identity")
                    self.assertEqual(report["exit_code"], EXIT_REJECTED)

    def test_nonfinite_inside_a_pinned_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            pins = builder.seal()
            path = Path(pins[0]["result"]["path"])
            path.write_text('{"status":"pass","x": NaN}', encoding="utf-8")
            pins[0]["result"]["sha256"] = _sha(path)
            report = classify({"evidence": pins})
            self.assertEqual(report["classification"], "malformed_identity")
            self.assertEqual(report["exit_code"], EXIT_REJECTED)

    def test_inline_shapes_and_evidence_forms_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            pins = builder.seal()
            inline = {
                "task_profile": joint.MIXED_TASKS[0],
                "result": {"status": "pass"},
                "audit": {"status": "pass"},
                "admission": {"ok": True},
            }
            self.assertEqual(classify(inline)["classification"], "missing_identity")
            self.assertEqual(
                classify({"evidence": [builder.packets[0][2], builder.packets[1][2]]})[
                    "classification"
                ],
                "malformed_identity",
            )
            self.assertEqual(
                classify(
                    {
                        "evidence": [
                            pins[0],
                            {
                                "task_profile": joint.MIXED_TASKS[1],
                                "result": {"status": "pass"},
                                "audit": {"status": "pass"},
                                "admission": {"ok": True},
                            },
                        ]
                    }
                )["classification"],
                "malformed_identity",
            )
            sibling = dict(pins[0])
            sibling["result_inline"] = {"status": "pass"}
            self.assertEqual(
                classify({"evidence": [sibling, pins[1]]})["classification"],
                "malformed_identity",
            )
        for label, value in (
            ("empty-list", []),
            ("string", "x"),
            ("dict", {}),
            ("null", None),
            ("int", 3),
        ):
            with self.subTest(evidence=label):
                report = classify({"evidence": value})
                self.assertIn(
                    report["classification"], ("malformed_identity", "incomplete_evidence")
                )
                self.assertTrue(_never_accepted(report))

    def test_pin_schema_tamper_and_extra_keys_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            pins = builder.seal()
            missing = [dict(pin) for pin in pins]
            missing[0].pop("task_profile")
            self.assertEqual(
                classify({"evidence": missing})["classification"], "malformed_identity"
            )
            bad_sha = [dict(pin) for pin in pins]
            bad_sha[0]["result"] = dict(bad_sha[0]["result"], sha256="not-a-sha")
            self.assertEqual(
                classify({"evidence": bad_sha})["classification"], "malformed_identity"
            )
            extra = [dict(pin) for pin in pins]
            extra[0]["extra"] = True
            self.assertEqual(
                classify({"evidence": extra})["classification"], "malformed_identity"
            )
            tampered = builder.seal()
            Path(tampered[0]["result"]["path"]).write_text('{"tampered":true}', encoding="utf-8")
            self.assertEqual(
                classify({"evidence": tampered})["classification"], "malformed_identity"
            )

    def test_task_set_must_match_the_committed_mixed_tasks(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            pins = builder.seal()
            pins[1]["task_profile"] = joint.MIXED_TASKS[0]
            report = classify({"evidence": pins})
            self.assertEqual(report["classification"], "incomplete_evidence")
            self.assertIn("MIXED_TASKS", " ".join(report["reasons"]))

    def test_path_escape_and_nonexistent_pins_fail_closed(self):
        target = ROOT / "tools/audit_33_mixed_packet.py"
        relative = {
            "task_profile": joint.MIXED_TASKS[0],
            "result": {"path": "validation/../tools/audit_33_mixed_packet.py",
                       "sha256": _sha(target)},
            "audit": {"path": "validation/../tools/audit_33_mixed_packet.py",
                      "sha256": _sha(target)},
            "admission": {"path": "validation/../tools/audit_33_mixed_packet.py",
                          "sha256": _sha(target)},
        }
        self.assertEqual(classify(relative)["classification"], "malformed_identity")
        escape = json.loads(json.dumps(relative))
        for key in ("result", "audit", "admission"):
            escape[key] = {"path": "../../../../Windows/System32/drivers/etc/hosts",
                           "sha256": "0" * 64}
        self.assertEqual(classify(escape)["classification"], "malformed_identity")
        absent = json.loads(json.dumps(relative))
        for key in ("result", "audit", "admission"):
            absent[key] = {"path": "/root/none/admission.json", "sha256": "0" * 64}
        self.assertEqual(classify(absent)["classification"], "malformed_identity")

    def test_symlinked_pin_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            pins = builder.seal()
            link = Path(directory) / "result-link.json"
            try:
                link.symlink_to(Path(pins[0]["result"]["path"]))
            except (OSError, NotImplementedError) as error:
                self.skipTest("symlinks unavailable: " + str(error))
            pins[0]["result"]["path"] = str(link)
            report = classify({"evidence": pins})
            self.assertEqual(report["classification"], "malformed_identity")
            self.assertEqual(report["exit_code"], EXIT_REJECTED)


class StrictPinnedJsonTests(unittest.TestCase):
    """N1: otherwise-valid resealed pins cannot carry non-finite extras."""

    RUN_FILES = {
        "result": "result.json",
        "audit": "audit.json",
        "admission": "experimental-admission.json",
    }

    def _rejected(self, report):
        self.assertEqual(report["classification"], "malformed_identity")
        self.assertEqual(report["exit_code"], EXIT_REJECTED)
        self.assertTrue(_never_accepted(report))
        return report

    def test_resealed_nonfinite_extras_reject_packet_and_directory(self):
        cases = (
            ("result", b', "unused_metric": NaN}'),
            ("audit", b', "unused_metric": Infinity}'),
            ("admission", b', "unused_metric": -Infinity}'),
        )
        for key, suffix in cases:
            with self.subTest(flow="packet", key=key):
                with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
                    pins = builder.seal()
                    pins[0][key]["sha256"] = _splice_json(Path(pins[0][key]["path"]), suffix)
                    report = classify({"evidence": pins})
                    self._rejected(report)
                    packet = Path(directory) / "packet.json"
                    packet.write_text(json.dumps({"evidence": pins}), encoding="utf-8")
                    self.assertEqual(_silent_main(["--packet", str(packet)]), EXIT_REJECTED)
            with self.subTest(flow="directory", key=key):
                with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
                    builder.seal()
                    _splice_json(builder.runs[joint.MIXED_TASKS[0]] / self.RUN_FILES[key], suffix)
                    report = classify_directory(builder.root)
                    self._rejected(report)
                    self.assertEqual(_silent_main(["--directory", str(builder.root)]), EXIT_REJECTED)

    def test_resealed_overflow_extra_is_rejected_on_both_flows(self):
        suffix = b', "unused_metric": 1e999}'
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            pins = builder.seal()
            pins[0]["audit"]["sha256"] = _splice_json(Path(pins[0]["audit"]["path"]), suffix)
            report = classify({"evidence": pins})
            self._rejected(report)
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            builder.seal()
            _splice_json(builder.runs[joint.MIXED_TASKS[0]] / "audit.json", suffix)
            report = classify_directory(builder.root)
            self._rejected(report)
            self.assertEqual(_silent_main(["--directory", str(builder.root)]), EXIT_REJECTED)


class DegenerateArgumentTests(unittest.TestCase):
    """F1/F3: an empty source argument is a rejection report, never the CWD."""

    def _assert_rejected_report(self, text):
        report = json.loads(text)
        self.assertEqual(report["classification"], "malformed_identity")
        self.assertEqual(report["status"], "rejected")
        self.assertEqual(report["exit_code"], EXIT_REJECTED)
        self.assertTrue(_never_accepted(report))
        return report

    def test_empty_packet_argument_is_a_malformed_identity_report(self):
        buffer = io.StringIO()
        with mock.patch("sys.stdout", buffer):
            self.assertEqual(main(["--packet", ""]), EXIT_REJECTED)
        report = self._assert_rejected_report(buffer.getvalue())
        self.assertIn("empty", " ".join(report["reasons"]))
        self.assertEqual(classify_path("")["classification"], "malformed_identity")
        self.assertEqual(classify_path("")["exit_code"], EXIT_REJECTED)

    def test_empty_directory_never_classifies_the_working_directory(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            builder.seal()
            previous = os.getcwd()
            os.chdir(builder.root)
            try:
                report = classify_directory("")
                self.assertEqual(report["classification"], "malformed_identity")
                self.assertEqual(report["exit_code"], EXIT_REJECTED)
                buffer = io.StringIO()
                with mock.patch("sys.stdout", buffer):
                    self.assertEqual(main(["--directory", ""]), EXIT_REJECTED)
                self._assert_rejected_report(buffer.getvalue())
            finally:
                os.chdir(previous)
            # The same directory *is* classified when named explicitly: the empty
            # argument suppressed a real classification instead of masking a
            # broken fixture.
            self.assertEqual(classify_directory(builder.root)["classification"], CLASSIFIED)

    def test_empty_arguments_exit_two_via_the_script_entry_point(self):
        for argv in (["--packet", ""], ["--directory", ""]):
            with self.subTest(argv=argv):
                done = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(ROOT / "tools/audit_33_mixed_packet.py"),
                        *argv,
                    ],
                    capture_output=True,
                    cwd=ROOT,
                    timeout=180,
                )
                self.assertEqual(done.returncode, EXIT_REJECTED, done.stderr.decode("utf-8"))
                self.assertNotIn(b"Traceback", done.stderr)
                self._assert_rejected_report(done.stdout.decode("utf-8"))


class DeepNestingTests(unittest.TestCase):
    """F2: deep JSON and deep non-finite traversal stay fail-closed at exit 2."""

    # Larger than CPython's default recursion limit, so both json.loads and a
    # naive recursive walk would raise RecursionError on this host.
    DEPTH = 1400

    def _assert_malformed(self, report):
        self.assertEqual(report["classification"], "malformed_identity")
        self.assertEqual(report["exit_code"], EXIT_REJECTED)
        self.assertTrue(_never_accepted(report))
        return report

    def test_deeply_nested_packet_is_rejected_on_every_entry_point(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "deep.json"
            path.write_text(_deep_json(self.DEPTH), encoding="utf-8")
            self._assert_malformed(classify_path(path))
            buffer = io.StringIO()
            with mock.patch("sys.stdout", buffer):
                self.assertEqual(main(["--packet", str(path)]), EXIT_REJECTED)
            self._assert_malformed(json.loads(buffer.getvalue()))
            done = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "tools/audit_33_mixed_packet.py"),
                    "--packet",
                    str(path),
                ],
                capture_output=True,
                cwd=ROOT,
                timeout=180,
            )
            self.assertEqual(done.returncode, EXIT_REJECTED, done.stderr.decode("utf-8"))
            self.assertNotIn(b"Traceback", done.stderr)
            self._assert_malformed(json.loads(done.stdout.decode("utf-8")))

    def test_nonfinite_leaf_is_found_by_the_iterative_depth_walk(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "deep-nonfinite.json"
            path.write_text(_deep_json(200, "1e999"), encoding="utf-8")
            report = self._assert_malformed(classify_path(path))
            self.assertIn("non-finite", " ".join(report["reasons"]))

    def test_deeply_nested_pinned_result_is_malformed_identity(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            pins = builder.seal()
            path = Path(pins[0]["result"]["path"])
            path.write_text(_deep_json(self.DEPTH), encoding="utf-8")
            pins[0]["result"]["sha256"] = _sha(path)
            self._assert_malformed(classify({"evidence": pins}))

    def test_deeply_nested_run_result_is_malformed_identity_on_directory_flow(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            builder.seal()
            (builder.runs[joint.MIXED_TASKS[0]] / "result.json").write_text(
                _deep_json(self.DEPTH), encoding="utf-8"
            )
            self._assert_malformed(classify_directory(builder.root))
            buffer = io.StringIO()
            with mock.patch("sys.stdout", buffer):
                self.assertEqual(main(["--directory", str(builder.root)]), EXIT_REJECTED)
            self._assert_malformed(json.loads(buffer.getvalue()))


class SecondReadVerificationTests(unittest.TestCase):
    """F4: the bytes actually parsed must still match the pin digest."""

    def test_production_pinned_json_and_mixed_proofs_stay_on_the_decisive_path(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            pins = builder.seal()
            real = joint._pinned_json
            seen = []

            def recording(pin):
                seen.append(dict(pin))
                return real(pin)

            with mock.patch.object(joint, "_pinned_json", side_effect=recording):
                with mock.patch.object(
                    joint, "_mixed_proofs", wraps=joint._mixed_proofs
                ) as proofs:
                    report = classify({"evidence": pins})
            self.assertEqual(report["classification"], CLASSIFIED)
            for pin in pins:
                for key in ("result", "audit", "admission"):
                    self.assertIn(pin[key], seen)
            self.assertEqual(proofs.call_count, 1)

    def test_second_read_bytes_must_match_the_pin_digest(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            pins = builder.seal()
            target = Path(pins[0]["result"]["path"])
            real = joint._pinned_json

            def racing(pin):
                parsed = real(pin)
                if Path(pin["path"]) == target:
                    # The production read verified the original bytes; the bytes
                    # the tool is about to classify are now different.
                    target.write_text('{"tampered": true}', encoding="utf-8")
                return parsed

            with mock.patch.object(joint, "_pinned_json", side_effect=racing):
                report = classify({"evidence": pins})
            self.assertEqual(report["classification"], "malformed_identity")
            self.assertEqual(report["exit_code"], EXIT_REJECTED)
            self.assertTrue(_never_accepted(report))
            self.assertIn("Pinned SHA256 differs", " ".join(report["reasons"]))


class ComboSeparationTests(unittest.TestCase):
    def test_historical_legacy_old_mixed_and_catalog_combos(self):
        for combo in ("legacy", "historical_mixed", "catalog"):
            with self.subTest(combo=combo), tempfile.TemporaryDirectory() as directory:
                report = classify({"evidence": PacketBuilder(directory, combo=combo).seal()})
                self.assertEqual(report["classification"], "historical_combo")
                self.assertEqual(report["exit_code"], EXIT_REJECTED)
                self.assertTrue(_never_accepted(report))

    def test_historical_pv_firmware_and_previous_control(self):
        with tempfile.TemporaryDirectory() as directory:
            builder = PacketBuilder(directory)
            _set_identity(builder, ap=PV_FIRMWARE, control=HISTORICAL_PV_CONTROL)
            report = classify({"evidence": builder.seal()})
            self.assertEqual(report["classification"], "historical_combo")
        with tempfile.TemporaryDirectory() as directory:
            builder = PacketBuilder(directory)
            _set_identity(builder, ap=FINAL_AP, control=PREVIOUS_PV_CONTROL)
            report = classify({"evidence": builder.seal()})
            self.assertEqual(report["classification"], "historical_combo")

    def test_wrong_combo_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            report = classify({"evidence": PacketBuilder(directory, combo="wrong").seal()})
            self.assertEqual(report["classification"], "wrong_combo")
            self.assertEqual(report["exit_code"], EXIT_REJECTED)
            self.assertTrue(_never_accepted(report))

    def test_final_identity_with_wrong_message_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            _set_identity(builder, message="7" * 64)
            report = classify({"evidence": builder.seal()})
            self.assertEqual(report["classification"], "wrong_combo")
            self.assertEqual(report["exit_code"], EXIT_REJECTED)

    def test_never_upgrade_across_the_matrix(self):
        for combo in ("legacy", "historical_mixed", "catalog", "wrong"):
            with self.subTest(combo=combo), tempfile.TemporaryDirectory() as directory:
                report = classify({"evidence": PacketBuilder(directory, combo=combo).seal()})
                self.assertTrue(_never_accepted(report))
                text = json.dumps(report, sort_keys=True)
                for token in (
                    '"issue_33_accepted": true',
                    '"issue_84_accepted": true',
                    '"acceptance_eligible": true',
                    '"issues_accepted": true',
                ):
                    self.assertNotIn(token, text)
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            report = classify({"evidence": builder.seal()})
            self.assertEqual(report["classification"], CLASSIFIED)
            self.assertTrue(_never_accepted(report))
            text = json.dumps(report, sort_keys=True)
            self.assertNotIn('"issue_33_accepted": true', text)
            self.assertNotIn('"issue_84_accepted": true', text)
            self.assertNotIn('"acceptance_eligible": true', text)


class DirectoryContractTests(unittest.TestCase):
    def test_single_run_directory_is_genuinely_incomplete(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            for pin in builder.seal():
                with self.subTest(task=pin["task_profile"]):
                    report = classify_directory(Path(pin["result"]["path"]).parent)
                    self.assertEqual(report["classification"], "incomplete_evidence")
                    self.assertIn("both", " ".join(report["reasons"]).lower())
                    self.assertEqual(report["exit_code"], EXIT_REJECTED)

    def test_two_run_directory_classifies_the_current_packet(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            builder.seal()
            report = classify_directory(builder.root)
            self.assertEqual(report["classification"], CLASSIFIED)
            self.assertEqual(report["exit_code"], EXIT_CLASSIFIED)
            self.assertTrue(_never_accepted(report))

    def test_two_run_directory_separates_wrong_and_legacy(self):
        for combo, expected in (("wrong", "wrong_combo"), ("legacy", "historical_combo")):
            with self.subTest(combo=combo), tempfile.TemporaryDirectory() as directory:
                builder = PacketBuilder(directory, combo=combo)
                builder.seal()
                report = classify_directory(builder.root)
                self.assertEqual(report["classification"], expected)
                self.assertEqual(report["exit_code"], EXIT_REJECTED)

    def test_directory_without_run_files_is_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            report = classify_directory(directory)
            self.assertEqual(report["classification"], "incomplete_evidence")
            self.assertIn("no run directory", " ".join(report["reasons"]))
        self.assertEqual(
            classify_directory("/nonexistent/packet")["classification"], "malformed_identity"
        )

    def test_duplicate_run_directories_for_one_task_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            builder.seal()
            duplicate = builder.root / "duplicate"
            duplicate.mkdir()
            for name in ("result.json", "audit.json", "experimental-admission.json"):
                (duplicate / name).write_bytes(
                    (builder.runs[joint.MIXED_TASKS[0]] / name).read_bytes()
                )
            report = classify_directory(builder.root)
            self.assertEqual(report["classification"], "incomplete_evidence")
            self.assertIn("duplicate run directories", " ".join(report["reasons"]))

    def test_symlinked_run_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            # The run files must exist, otherwise the alias is not a run directory
            # at all and the case would degrade to incomplete_evidence (this only
            # shows up on hosts where symlinks are available).
            builder.seal()
            alias = builder.root / "alias"
            try:
                alias.symlink_to(builder.runs[joint.MIXED_TASKS[0]], target_is_directory=True)
            except (OSError, NotImplementedError) as error:
                self.skipTest("symlinks unavailable: " + str(error))
            report = classify_directory(builder.root)
            self.assertEqual(report["classification"], "malformed_identity")
            self.assertIn("symlink", " ".join(report["reasons"]))


class CliExitTests(unittest.TestCase):
    def test_classified_packet_exits_zero_and_rejections_exit_two(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            packet = Path(directory) / "final.json"
            packet.write_text(json.dumps({"evidence": builder.seal()}), encoding="utf-8")
            self.assertEqual(_silent_main(["--packet", str(packet)]), EXIT_CLASSIFIED)
        with tempfile.TemporaryDirectory() as directory:
            packet = Path(directory) / "wrong.json"
            packet.write_text(
                json.dumps({"evidence": PacketBuilder(directory, combo="wrong").seal()}),
                encoding="utf-8",
            )
            self.assertEqual(_silent_main(["--packet", str(packet)]), EXIT_REJECTED)
            self.assertEqual(
                _silent_main(["--packet", str(Path(directory) / "absent.json")]), EXIT_REJECTED
            )
            malformed = Path(directory) / "malformed.json"
            malformed.write_text("{", encoding="utf-8")
            self.assertEqual(_silent_main(["--packet", str(malformed)]), EXIT_REJECTED)

    def test_directory_exit_follows_the_classification(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            builder.seal()
            self.assertEqual(_silent_main(["--directory", str(builder.root)]), EXIT_CLASSIFIED)
            single = Path(builder.seal()[0]["result"]["path"]).parent
            self.assertEqual(_silent_main(["--directory", str(single)]), EXIT_REJECTED)
        with tempfile.TemporaryDirectory() as directory:
            builder = PacketBuilder(directory, combo="wrong")
            builder.seal()
            self.assertEqual(_silent_main(["--directory", str(builder.root)]), EXIT_REJECTED)

    def test_cli_usage_errors_exit_two(self):
        with tempfile.TemporaryDirectory() as directory:
            packet = Path(directory) / "wrong.json"
            packet.write_text(
                json.dumps({"evidence": PacketBuilder(directory, combo="wrong").seal()}),
                encoding="utf-8",
            )
            for argv in ([], ["--packet", str(packet), "--directory", directory]):
                with self.subTest(argv=argv), mock.patch("sys.stderr", io.StringIO()):
                    with self.assertRaises(SystemExit) as caught:
                        main(argv)
                    self.assertEqual(caught.exception.code, 2)

    def test_output_report_is_lf_only_and_never_claims_acceptance(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            packet = Path(directory) / "final.json"
            packet.write_text(json.dumps({"evidence": builder.seal()}), encoding="utf-8")
            out = Path(directory) / "report.json"
            self.assertEqual(main(["--packet", str(packet), "--output", str(out)]), 0)
            raw = out.read_bytes()
            self.assertNotIn(b"\r\n", raw)
            saved = json.loads(raw.decode("utf-8"))
            self.assertEqual(saved["classification"], CLASSIFIED)
            self.assertTrue(_never_accepted(saved))

    def test_stdout_report_never_claims_acceptance(self):
        with tempfile.TemporaryDirectory() as directory, FinalCase(directory) as builder:
            packet = Path(directory) / "final.json"
            packet.write_text(json.dumps({"evidence": builder.seal()}), encoding="utf-8")
            buffer = io.StringIO()
            with mock.patch("sys.stdout", buffer):
                self.assertEqual(main(["--packet", str(packet)]), 0)
            text = buffer.getvalue()
            self.assertIn(CLASSIFIED, text)
            self.assertNotRegex(text, r'"issue_33_accepted": true')
            self.assertNotRegex(text, r'"issue_84_accepted": true')
            self.assertNotRegex(text, r'"acceptance_eligible": true')

    def test_script_entry_point_is_runnable_and_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            packet = Path(directory) / "wrong.json"
            packet.write_text(
                json.dumps({"evidence": PacketBuilder(directory, combo="wrong").seal()}),
                encoding="utf-8",
            )
            done = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "tools/audit_33_mixed_packet.py"),
                    "--packet",
                    str(packet),
                ],
                capture_output=True,
                cwd=ROOT,
                timeout=180,
            )
            self.assertEqual(done.returncode, EXIT_REJECTED, done.stderr.decode("utf-8"))
            report = json.loads(done.stdout.decode("utf-8"))
            self.assertEqual(report["classification"], "wrong_combo")
            self.assertFalse(report["acceptance_eligible"])


if __name__ == "__main__":
    unittest.main()
