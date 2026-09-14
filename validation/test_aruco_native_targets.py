# SPDX-License-Identifier: Apache-2.0
"""Pure offline tests for the #29 ArUco/physical admission inspector.

Temporary fixtures stay in tempfile. These tests do not start UE, native,
ROS, DDS, SITL, firmware, MATLAB, or a build, and a correlated pack does
not unlock #29/#79/#80/#81 while #9 is OPEN.
"""

from __future__ import annotations

import importlib
import json
import math
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from tools.inspect_aruco_native_targets import (
    ARUCO_TARGET_SCHEMA,
    CONTACT_SCHEMA,
    EVIDENCE_MANIFEST_PATH,
    ISSUE_9_OPEN,
    PACK_SCHEMA,
    PARENT_TICKETS,
    PLANNER_SCENE_HASH,
    PROBE_SCENE_HASH,
    PROBE_SCENE_ID,
    STATIC_SCENE_PATH,
    VISUAL_STATIC_SCENE_HASH,
    VISUAL_STATIC_SCENE_ID,
    InspectError,
    inspect_pack,
    inspect_path,
    inspect_retained_paths,
    main,
    write_report,
)

REPO = Path(__file__).resolve().parents[1]
EPOCH = "e0f1a2b3c4d5e6f708192a3b4c5d6e7f"


def _scene(**overrides):
    value = {
        "scene_id": VISUAL_STATIC_SCENE_ID,
        "scene_hash": VISUAL_STATIC_SCENE_HASH,
        "coordinate_frame": "ENU",
        "unit": "metre",
        "source_identity": "Simulator/wksim_runtime/static-scene-v1.json",
        "epoch": EPOCH,
    }
    value.update(overrides)
    return value


def _visual(**overrides):
    value = {
        "schema": ARUCO_TARGET_SCHEMA,
        "scene_id": VISUAL_STATIC_SCENE_ID,
        "scene_hash": VISUAL_STATIC_SCENE_HASH,
        "coordinate_frame": "ENU",
        "source_identity": "Simulator/wksim_perception/aruco.py",
        "epoch": EPOCH,
        "step": 10,
        "valid_from_step": 10,
        "valid_until_step": 10,
        "position_world_ue_m": [4.0, 1.0, 2.0],
        "position_body_flu_m": [1.5, 0.0, 0.2],
    }
    value.update(overrides)
    return value


def _physical(**overrides):
    value = {
        "schema": CONTACT_SCHEMA,
        "scene_id": VISUAL_STATIC_SCENE_ID,
        "scene_hash": VISUAL_STATIC_SCENE_HASH,
        "epoch": EPOCH,
        "step": 10,
        "sim_time_ns": 10_000_000,
        "valid_from_step": 10,
        "valid_until_step": 10,
        "body_id": "uav1",
        "geometry_id": "plane_z0",
        "contact_point_enu_m": [0.0, 0.0, 0.0],
        "normal_enu": [0.0, 0.0, 1.0],
        "penetration_m": 0.0,
        "source_identity": "Simulator/wksim_core/static_contact.py",
    }
    value.update(overrides)
    return value


def _semantics(**overrides):
    value = {
        "stale_feedback": "freeze",
        "disconnect": "display_stale_does_not_advance_physics",
        "render_frame_advances_physics": False,
    }
    value.update(overrides)
    return value


def _pack(**overrides):
    value = {
        "schema": PACK_SCHEMA,
        "issue_9_state": ISSUE_9_OPEN,
        "current_step": 10,
        "epoch": EPOCH,
        "scene": _scene(),
        "visual_target": _visual(),
        "physical_target": _physical(),
        "feedback_semantics": _semantics(),
    }
    value.update(overrides)
    return value


class SufficientEvidenceTests(unittest.TestCase):
    def test_complete_pack_correlates_but_does_not_unlock_parent_tickets(self):
        report = inspect_pack(_pack())
        self.assertEqual(report["status"], "correlated")
        self.assertTrue(report["correlated"])
        self.assertEqual(report["rejection_reasons"], [])
        self.assertEqual(report["issue_9_state"], ISSUE_9_OPEN)
        self.assertEqual(report["parent_tickets_unlocked"], {ticket: False for ticket in PARENT_TICKETS})
        self.assertIn("#9 OPEN", report["unlock_blocked_by"])
        self.assertIn("offline_tool_is_not_ue_or_physics_acceptance", report["unlock_blocked_by"])
        self.assertFalse(report["contact_budget_invented"])
        self.assertFalse(report["visual_treated_as_collision"])
        self.assertFalse(report["render_frame_advances_physics"])
        self.assertNotIn("pass", report["status"])

    def test_claiming_issue_9_closed_is_rejected_and_still_locks_tickets(self):
        report = inspect_pack(_pack(issue_9_state="CLOSED"))
        self.assertEqual(report["status"], "rejected")
        self.assertIn("fabricated_issue_9_closure", report["rejection_reasons"])
        self.assertEqual(report["issue_9_state"], ISSUE_9_OPEN)
        self.assertTrue(all(unlocked is False for unlocked in report["parent_tickets_unlocked"].values()))


class RejectionBoundaryTests(unittest.TestCase):
    def test_missing_coordinate_frame_is_rejected(self):
        pack = _pack()
        del pack["scene"]["coordinate_frame"]
        del pack["visual_target"]["coordinate_frame"]
        report = inspect_pack(pack)
        self.assertEqual(report["status"], "rejected")
        self.assertIn("missing_coordinate_frame", report["rejection_reasons"])
        self.assertFalse(report["correlated"])

    def test_ned_or_ue_only_frame_is_rejected(self):
        pack = _pack()
        pack["scene"]["coordinate_frame"] = "NED"
        pack["visual_target"]["coordinate_frame"] = "UE"
        report = inspect_pack(pack)
        self.assertIn("missing_coordinate_frame", report["rejection_reasons"])

    def test_raw_aruco_world_ue_without_frame_is_rejected(self):
        visual = _visual()
        del visual["coordinate_frame"]
        report = inspect_pack(_pack(visual_target=visual))
        self.assertIn("missing_coordinate_frame", report["rejection_reasons"])

    def test_missing_feedback_valid_time_is_rejected(self):
        physical = _physical()
        del physical["valid_from_step"]
        del physical["valid_until_step"]
        visual = _visual()
        del visual["valid_from_step"]
        del visual["valid_until_step"]
        report = inspect_pack(_pack(physical_target=physical, visual_target=visual, current_step=None))
        self.assertIn("missing_feedback_valid_time", report["rejection_reasons"])
        self.assertFalse(report["correlated"])

    def test_missing_source_identity_is_rejected(self):
        visual = _visual()
        physical = _physical()
        del visual["source_identity"]
        del physical["source_identity"]
        report = inspect_pack(_pack(visual_target=visual, physical_target=physical))
        self.assertIn("missing_source_identity", report["rejection_reasons"])

    def test_missing_stale_or_disconnect_semantics_is_rejected(self):
        report = inspect_pack(_pack(feedback_semantics={}))
        self.assertIn("missing_stale_or_disconnect_semantics", report["rejection_reasons"])

    def test_reuse_old_feedback_is_rejected(self):
        report = inspect_pack(
            _pack(
                feedback_semantics=_semantics(
                    stale_feedback="reuse_old_feedback",
                    disconnect="reuse",
                )
            )
        )
        self.assertIn("missing_stale_or_disconnect_semantics", report["rejection_reasons"])

    def test_render_frame_advancing_physics_is_rejected(self):
        report = inspect_pack(
            _pack(feedback_semantics=_semantics(render_frame_advances_physics=True))
        )
        self.assertIn("render_frame_advances_physics", report["rejection_reasons"])
        self.assertTrue(report["render_frame_advances_physics"])
        self.assertFalse(report["correlated"])

    def test_visual_offset_only_is_rejected(self):
        visual_as_contact = {
            "schema": "visual-offset",
            "visual_ground_offset_m": -0.12,
            "contact_point_enu_m": [4.0, 1.0, 1.88],
        }
        report = inspect_pack(_pack(physical_target=visual_as_contact))
        self.assertIn("visual_offset_only", report["rejection_reasons"])
        self.assertFalse(report["visual_treated_as_collision"])
        self.assertFalse(report["correlated"])

    def test_copying_aruco_ue_pose_as_contact_is_visual_offset_only(self):
        physical = _physical(contact_point_enu_m=[4.0, 1.0, 2.0])
        report = inspect_pack(_pack(physical_target=physical))
        self.assertIn("visual_offset_only", report["rejection_reasons"])

    def test_unapproved_contact_budget_is_rejected_and_not_invented(self):
        physical = _physical(force=[0.0, 0.0, 9.81], stiffness=1200.0)
        report = inspect_pack(_pack(physical_target=physical))
        self.assertIn("unapproved_contact_budget", report["rejection_reasons"])
        self.assertFalse(report["contact_budget_invented"])
        self.assertNotIn("force", report)
        self.assertNotIn("stiffness", report)

    def test_stale_feedback_is_rejected(self):
        report = inspect_pack(_pack(current_step=11))
        self.assertIn("stale_feedback", report["rejection_reasons"])
        self.assertFalse(report["correlated"])

    def test_future_feedback_is_rejected(self):
        report = inspect_pack(_pack(current_step=9))
        self.assertIn("future_feedback", report["rejection_reasons"])

    def test_mixed_scene_identity_layers_are_rejected(self):
        scene = _scene(scene_id=VISUAL_STATIC_SCENE_ID, scene_hash=PROBE_SCENE_HASH)
        physical = _physical(scene_id=PROBE_SCENE_ID, scene_hash=PROBE_SCENE_HASH)
        report = inspect_pack(_pack(scene=scene, physical_target=physical))
        self.assertTrue(
            {"scene_identity_conflation", "scene_identity_mismatch"}
            & set(report["rejection_reasons"])
        )

    def test_planner_hash_is_not_a_display_or_contact_identity(self):
        report = inspect_pack(_pack(scene=_scene(scene_hash=PLANNER_SCENE_HASH)))
        self.assertIn("scene_identity_conflation", report["rejection_reasons"])


class TypeGateTests(unittest.TestCase):
    """Exact independent-review P2 counterexamples plus NaN/Inf/length gates."""

    def test_p2_empty_physical_source_identity_is_rejected(self):
        # Review neg4 / P2-1: physical source_identity="" still correlated.
        report = inspect_pack(_pack(physical_target=_physical(source_identity="")))
        self.assertEqual(report["status"], "rejected")
        self.assertFalse(report["correlated"])
        self.assertIn("missing_source_identity", report["rejection_reasons"])

    def test_p2_false_sim_time_ns_with_step_zero_is_rejected(self):
        # Review neg5 / P2-2: step=0 and sim_time_ns=False still correlated.
        physical = _physical(step=0, sim_time_ns=False, valid_from_step=0, valid_until_step=0)
        visual = _visual(step=0, valid_from_step=0, valid_until_step=0)
        report = inspect_pack(_pack(
            physical_target=physical,
            visual_target=visual,
            current_step=0,
        ))
        self.assertEqual(report["status"], "rejected")
        self.assertFalse(report["correlated"])
        self.assertIn("missing_feedback_valid_time", report["rejection_reasons"])

    def test_p2_string_contact_point_is_rejected(self):
        # Review neg6 / P2-3: contact_point_enu_m="not-a-vector" still correlated.
        report = inspect_pack(
            _pack(physical_target=_physical(contact_point_enu_m="not-a-vector"))
        )
        self.assertEqual(report["status"], "rejected")
        self.assertFalse(report["correlated"])
        self.assertIn("invalid_vector", report["rejection_reasons"])

    def test_source_identity_empty_object_and_bool_are_rejected(self):
        for identity in ({}, True, False, []):
            with self.subTest(identity=identity):
                report = inspect_pack(_pack(physical_target=_physical(source_identity=identity)))
                self.assertEqual(report["status"], "rejected")
                self.assertIn("missing_source_identity", report["rejection_reasons"])
        nested_empty = inspect_pack(
            _pack(physical_target=_physical(source_identity={"module": ""}))
        )
        self.assertIn("missing_source_identity", nested_empty["rejection_reasons"])

    def test_nan_infinity_and_wrong_length_vectors_are_rejected(self):
        cases = (
            ("contact_point_enu_m", [math.nan, 0.0, 0.0]),
            ("contact_point_enu_m", [math.inf, 0.0, 0.0]),
            ("contact_point_enu_m", [-math.inf, 0.0, 0.0]),
            ("normal_enu", [0.0, 0.0]),
            ("normal_enu", [0.0, 0.0, 1.0, 0.0]),
            ("normal_enu", [0.0, 0.0, True]),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                report = inspect_pack(_pack(physical_target=_physical(**{field: value})))
                self.assertEqual(report["status"], "rejected")
                self.assertIn("invalid_vector", report["rejection_reasons"])
        visual = _visual(position_world_ue_m=[1.0, math.nan, 2.0])
        report = inspect_pack(_pack(visual_target=visual))
        self.assertIn("invalid_vector", report["rejection_reasons"])
        report = inspect_pack(_pack(physical_target=_physical(penetration_m=True)))
        self.assertIn("invalid_scalar_type", report["rejection_reasons"])
        report = inspect_pack(_pack(physical_target=_physical(penetration_m=math.inf)))
        self.assertIn("invalid_scalar_type", report["rejection_reasons"])

    def test_integer_zero_step_with_matching_sim_time_still_correlates(self):
        physical = _physical(step=0, sim_time_ns=0, valid_from_step=0, valid_until_step=0)
        visual = _visual(step=0, valid_from_step=0, valid_until_step=0)
        report = inspect_pack(_pack(
            physical_target=physical,
            visual_target=visual,
            current_step=0,
        ))
        self.assertEqual(report["status"], "correlated")
        self.assertFalse(report["parent_tickets_unlocked"]["#29"])


class PathAndIoTests(unittest.TestCase):
    def test_static_scene_path_alone_is_insufficient(self):
        self.assertTrue(STATIC_SCENE_PATH.is_file())
        report = inspect_path(STATIC_SCENE_PATH)
        self.assertEqual(report["status"], "rejected")
        self.assertFalse(report["correlated"])
        self.assertIn("missing_visual_target", report["rejection_reasons"])
        self.assertIn("missing_physical_target", report["rejection_reasons"])
        self.assertIn("missing_stale_or_disconnect_semantics", report["rejection_reasons"])
        self.assertEqual(report["parent_tickets_unlocked"]["#29"], False)

    def test_evidence_manifest_keeps_issue_9_block_and_distinct_identities(self):
        self.assertTrue(EVIDENCE_MANIFEST_PATH.is_file())
        report = inspect_path(EVIDENCE_MANIFEST_PATH)
        self.assertEqual(report["status"], "rejected")
        self.assertFalse(report["correlated"])
        self.assertEqual(report["issue_9_state"], ISSUE_9_OPEN)
        self.assertIn("#9 OPEN", report["unlock_blocked_by"])
        self.assertIn("insufficient_offline_pair", report["rejection_reasons"])
        self.assertIn("missing_real_ue_physics_colocation", report["unproven_boundaries"])
        self.assertIn("missing_slope_contact_force_dynamics", report["unproven_boundaries"])
        self.assertEqual(report["scene"]["scene_hash"], VISUAL_STATIC_SCENE_HASH)
        self.assertNotEqual(report["scene"]["scene_hash"], PROBE_SCENE_HASH)

    def test_retained_paths_do_not_fabricate_missing_live_dirs(self):
        report = inspect_retained_paths(REPO)
        self.assertEqual(report["status"], "rejected")
        self.assertTrue(report["path_availability"]["static_scene"])
        self.assertTrue(report["path_availability"]["evidence_manifest"])
        live = REPO / "validation" / "lunar-29-live-contact"
        if live.is_dir():
            self.assertTrue(report["path_availability"]["lunar_29_live_contact"])
            self.assertNotIn("retained_live_evidence_unavailable", report["rejection_reasons"])
            self.assertIn("insufficient_offline_pair", report["rejection_reasons"])
            if (live / "display-manifest.json").is_file():
                self.assertTrue(report["path_availability"]["live_display_manifest"])
        else:
            self.assertFalse(report["path_availability"]["lunar_29_live_contact"])
            self.assertIn("retained_live_evidence_unavailable", report["rejection_reasons"])
        self.assertFalse(report["correlated"])
        self.assertEqual(report["issue_9_state"], ISSUE_9_OPEN)

    def test_missing_live_dirs_in_temp_repo_are_marked_unavailable(self):
        with tempfile.TemporaryDirectory() as tempdir:
            fake = Path(tempdir)
            (fake / "Simulator" / "wksim_runtime").mkdir(parents=True)
            (fake / "docs" / "plan").mkdir(parents=True)
            report = inspect_retained_paths(fake)
            self.assertFalse(report["path_availability"]["static_scene"])
            self.assertFalse(report["path_availability"]["lunar_29_live_contact"])
            self.assertIn("retained_live_evidence_unavailable", report["rejection_reasons"])
            self.assertFalse(report["correlated"])

    def test_display_manifest_is_not_a_physical_contact_pair(self):
        manifest = REPO / "validation" / "lunar-29-live-contact" / "display-manifest.json"
        if not manifest.is_file():
            self.skipTest("retained live display-manifest is not in this checkout")
        report = inspect_path(manifest)
        self.assertEqual(report["status"], "rejected")
        self.assertIn("missing_physical_target", report["rejection_reasons"])
        self.assertIn("visual_offset_only", report["rejection_reasons"])
        self.assertEqual(report["parent_tickets_unlocked"]["#81"], False)

    def test_pack_file_roundtrip_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            pack_path = root / "aruco-native-target-pack.json"
            pack_path.write_text(json.dumps(_pack()) + "\n", encoding="utf-8")
            report = inspect_path(root)
            self.assertEqual(report["status"], "correlated")
            self.assertEqual(report["parent_tickets_unlocked"]["#79"], False)

            out_path = root / "report.json"
            write_report(report, out_path)
            loaded = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["status"], "correlated")
            with self.assertRaises(FileExistsError):
                write_report(report, out_path)

    def test_corrupt_or_wrong_named_input_raises(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "public-dds.jsonl").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(InspectError):
                inspect_path(root)
            bad = root / "broken.json"
            bad.write_text('{"schema":', encoding="utf-8")
            with self.assertRaises(InspectError):
                inspect_path(bad)

    def test_cli_retained_paths_and_pack(self):
        with tempfile.TemporaryDirectory() as tempdir:
            pack_path = Path(tempdir) / "pack.json"
            pack_path.write_text(json.dumps(_pack()) + "\n", encoding="utf-8")
            self.assertEqual(main(["--evidence", str(pack_path)]), 0)
            self.assertEqual(main(["--retained-paths"]), 0)

    def test_module_does_not_import_ros_or_runtime_physics(self):
        module = importlib.import_module("tools.inspect_aruco_native_targets")
        imported = set(sys.modules)
        self.assertNotIn("rclpy", imported)
        self.assertNotIn("rosidl_runtime_py", imported)
        self.assertFalse(hasattr(module, "HAS_ROS"))
        self.assertFalse(hasattr(module, "deserialize_cdr_message"))
        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("deserialize_message", source)
        self.assertNotIn("JointPhysics", source)


class IsolationTests(unittest.TestCase):
    def test_pack_mutation_does_not_leak_into_report(self):
        pack = _pack()
        original = deepcopy(pack)
        inspect_pack(pack)
        self.assertEqual(pack, original)

    def test_correlated_report_has_no_boolean_pass_or_budget_fields(self):
        report = inspect_pack(_pack())
        dumped = json.dumps(report, allow_nan=False)
        self.assertNotIn('"pass"', dumped)
        self.assertNotIn("unique_match", dumped)
        self.assertNotIn("approved_contact_budget", dumped)
        self.assertNotIn("NaN", dumped)


if __name__ == "__main__":
    unittest.main()
