"""Pure-data scene-frontier regression for the retained #29/#102 identities.

This test covers one boundary that no existing test asserted: the real
generated-model probe scene identity (``static-plane-box-v1-real-tick0`` /
``4889e2ea...``) and the frozen visual fixture identity (``.../60ae5097...``)
versus the planner ego binding identity (``40ee9281...``), plus the timeliness
behaviour of an injected ``TerrainFeedback`` observer whose epoch disagrees with
the running epoch.

Inputs are the retained on-disk evidence manifest and the real module
identities only.  Nothing here invents a runtime API, edits shared runtime,
messages, physics, or an existing validator, and nothing starts a model,
worker, build, UE, SITL, FC, ROS, or MATLAB process.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from Simulator.wksim_runtime.contact_observer import (
    FROZEN_SCENE_SHA256,
    ContactObserver,
)
from Simulator.wksim_runtime.planner_scene_binding import (
    EGO_SINGLE_BOX_BINDING,
    EXPECTED_SCENE_HASH,
    LEGACY_SCENE_HASH,
    LEGACY_SCENE_ID,
    PlannerSceneBindingError,
    PlannerSceneIdentityError,
)
from Simulator.wksim_runtime.terrain_feedback import TerrainFeedback

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_MANIFEST = ROOT / "docs/plan/29-terrain-evidence-manifest.json"

# Retained real generated-model probe identity (evidence manifest, real_terrain_scene).
PROBE_SCENE_ID = "static-plane-box-v1-real-tick0"
PROBE_SCENE_HASH = "4889e2ea32146b734a816281915842da1da27c0df78c588d688cd2656f2bb300"
PROBE_BOX_CENTER_ENU_M = [0.0, 0.0, 0.5]

EPOCH_RUN = "0123456789abcdef0123456789abcdef"
EPOCH_FOREIGN = "fedcba9876543210fedcba9876543210"
STACKS = ("arducopter", "px4")


def _load_manifest():
    """Load the retained manifest, rejecting duplicate JSON keys."""

    def reject_duplicates(pairs):
        seen = set()
        for key, _ in pairs:
            if key in seen:
                raise ValueError(f"duplicate key {key!r}")
            seen.add(key)
        return dict(pairs)

    text = EVIDENCE_MANIFEST.read_text(encoding="utf-8")
    return json.loads(text, object_pairs_hook=reject_duplicates)


class SceneIdentityFrontierTests(unittest.TestCase):
    """The three retained scene identities must stay separate and fail closed."""

    def setUp(self):
        manifest = _load_manifest()
        self.visual = manifest["scene_identities"]["visual_static_scene"]
        self.real = manifest["scene_identities"]["real_terrain_scene"]

    def test_three_identity_layers_are_pairwise_distinct(self):
        self.assertEqual(self.visual["scene_id"], LEGACY_SCENE_ID)
        self.assertEqual(self.visual["scene_sha256"], LEGACY_SCENE_HASH)
        self.assertEqual(self.real["scene_id"], PROBE_SCENE_ID)
        self.assertEqual(self.real["scene_sha256"], PROBE_SCENE_HASH)

        # The planner binding layer is a third identity, not either #29 layer.
        self.assertNotEqual(EXPECTED_SCENE_HASH, LEGACY_SCENE_HASH)
        self.assertNotEqual(EXPECTED_SCENE_HASH, PROBE_SCENE_HASH)
        self.assertNotEqual(LEGACY_SCENE_HASH, PROBE_SCENE_HASH)

        # The probe scene is not the frozen fixture and is not the same scene.
        self.assertNotEqual(PROBE_SCENE_ID, LEGACY_SCENE_ID)
        self.assertEqual(list(self.real["box_center_enu_m"]), PROBE_BOX_CENTER_ENU_M)
        self.assertNotEqual(list(self.real["box_center_enu_m"]),
                            list(self.visual["box_center_enu_m"]))

    def test_runtime_terrain_seam_binds_the_frozen_fixture_not_the_probe(self):
        # The accepted runtime seam (contact observer / terrain feedback) must
        # stay on the frozen visual fixture identity, never the probe identity.
        self.assertEqual(FROZEN_SCENE_SHA256, LEGACY_SCENE_HASH)
        self.assertEqual(self.visual["scene_sha256"], FROZEN_SCENE_SHA256)
        self.assertNotEqual(FROZEN_SCENE_SHA256, self.real["scene_sha256"])

    def test_probe_identity_is_never_accepted_as_planner_identity(self):
        manifest = EGO_SINGLE_BOX_BINDING.manifest
        for key, value in (("scene_id", PROBE_SCENE_ID),
                           ("scene_hash", PROBE_SCENE_HASH)):
            with self.subTest(key=key):
                invalid = deepcopy(manifest)
                invalid[key] = value
                with self.assertRaises(PlannerSceneIdentityError):
                    EGO_SINGLE_BOX_BINDING.validate_manifest(invalid)

        with self.assertRaises(PlannerSceneBindingError):
            substituted = deepcopy(manifest)
            substituted["scene_id"] = PROBE_SCENE_ID
            substituted["scene_hash"] = PROBE_SCENE_HASH
            EGO_SINGLE_BOX_BINDING.validate_manifest(substituted)

        # The genuine manifest is unaffected by the rejected substitutions.
        self.assertEqual(EGO_SINGLE_BOX_BINDING.validate_manifest(manifest), manifest)
        self.assertEqual(manifest["scene_hash"], EXPECTED_SCENE_HASH)


class InjectedObserverTimelinessTests(unittest.TestCase):
    """Injected observers must not silently reuse feedback from another epoch."""

    def test_foreign_epoch_observer_fails_closed_at_the_real_seam(self):
        observers = {stack: ContactObserver(run_epoch=EPOCH_FOREIGN) for stack in STACKS}
        feedback = TerrainFeedback(EPOCH_RUN, observers=observers)

        self.assertEqual(feedback.observers["arducopter"].epoch, EPOCH_FOREIGN)
        with self.assertRaises(RuntimeError) as ctx:
            feedback.query_terrain("arducopter", 1, [0.0] * 120)
        self.assertIn("froze", str(ctx.exception))

        # Frozen, and no terrain value is produced for later authoritative steps.
        self.assertTrue(feedback.observers["arducopter"].frozen)
        self.assertEqual(feedback.observers["arducopter"].freeze_reason, "foreign_epoch")
        with self.assertRaises(RuntimeError):
            feedback.query_terrain("arducopter", 2, [0.0] * 120)
        self.assertIsNone(feedback.observers["arducopter"].last_step)
        self.assertFalse(feedback.observers["px4"].frozen)

    def test_observer_set_must_exactly_match_supported_stacks(self):
        observers = {stack: ContactObserver(run_epoch=EPOCH_RUN) for stack in STACKS}
        with self.assertRaises(ValueError):
            TerrainFeedback(EPOCH_RUN, observers={"arducopter": observers["arducopter"]})
        with self.assertRaises(ValueError):
            TerrainFeedback(EPOCH_RUN, observers=dict(observers, extra=observers["px4"]))

    def test_matched_epoch_injection_still_binds_the_frozen_fixture(self):
        observers = {stack: ContactObserver(run_epoch=EPOCH_RUN) for stack in STACKS}
        feedback = TerrainFeedback(EPOCH_RUN, observers=observers)
        terrain = feedback.query_terrain("px4", 1, [0.0] * 120)
        self.assertEqual(len(terrain), 15)
        self.assertEqual(terrain, [0.0] * 15)
        self.assertEqual(feedback.manifest()["scene_hash"], FROZEN_SCENE_SHA256)
        self.assertEqual(feedback.manifest()["epoch"], EPOCH_RUN)


if __name__ == "__main__":
    unittest.main()
