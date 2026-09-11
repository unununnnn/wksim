"""Pure tests for the offline planner geometry binding.

The tests intentionally stop at canonical geometry and point-versus-AABB
observation.  They do not import a planner, JointPhysics, ROS, SITL, UE, or a
terrain/force path.  The mutation cases cover the supported ordinary
consistency guards; they are not a security proof against arbitrary Python
reflection or code execution in the test process.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import Simulator.wksim_runtime.planner_scene_binding as binding_module
from Simulator.wksim_runtime.planner_scene_binding import (
    BINDING_SOURCE_IDENTITY,
    EGO_SINGLE_BOX_BINDING,
    EXPECTED_POINT_CLOUD_HASH,
    EXPECTED_SCENE_HASH,
    GEOMETRY_ID,
    LEGACY_SCENE_HASH,
    LEGACY_SCENE_ID,
    PlannerSceneBinding,
    PlannerSceneBindingError,
    PlannerSceneIdentityError,
    PROFILE_SOURCE_IDENTITY,
    QUERY_VERSION,
    canonical_manifest_bytes,
)
from Simulator.wksim_planning.scene_profile import EGO_SINGLE_BOX_V1, SceneProfile


class PlannerSceneManifestTests(unittest.TestCase):
    binding = EGO_SINGLE_BOX_BINDING

    def test_manifest_identity_and_hashes_are_frozen(self):
        manifest = self.binding.manifest
        self.assertEqual(manifest["scene_id"], EGO_SINGLE_BOX_V1.profile_id)
        self.assertEqual(manifest["scene_hash"], EXPECTED_SCENE_HASH)
        self.assertEqual(manifest["profile_hash"], EGO_SINGLE_BOX_V1.profile_hash)
        self.assertEqual(manifest["collision_hash"], EGO_SINGLE_BOX_V1.collision_hash)
        self.assertEqual(manifest["voxel_hash"], EGO_SINGLE_BOX_V1.voxel_hash)
        self.assertEqual(manifest["point_cloud_hash"], EXPECTED_POINT_CLOUD_HASH)
        self.assertEqual(manifest["geometry_source_identity"], PROFILE_SOURCE_IDENTITY)
        self.assertEqual(manifest["binding_source_identity"], BINDING_SOURCE_IDENTITY)
        self.assertEqual(manifest["physics_authority"], "WSL")
        self.assertEqual(manifest["capabilities"], {
            "contact_geometry": True,
            "forces": False,
            "impulses": False,
            "terrain_response": False,
        })
        self.assertEqual(manifest["visual_mirror"], {
            "system": "UE",
            "binding_status": "not_bound",
        })
        self.assertEqual(self.binding.validate_manifest(manifest), manifest)

    def test_aabb_and_point_cloud_are_same_profile_source(self):
        self.assertEqual(self.binding.aabb, EGO_SINGLE_BOX_V1.aabb)
        self.assertEqual(self.binding.aabb, EGO_SINGLE_BOX_V1.obstacle)
        self.assertEqual(len(self.binding.point_cloud), 11000)
        self.assertEqual(self.binding.point_cloud[0], EGO_SINGLE_BOX_V1.point_cloud()[0])
        self.assertEqual(self.binding.point_cloud[-1], EGO_SINGLE_BOX_V1.point_cloud()[-1])
        self.assertEqual(self.binding.manifest["point_cloud"]["count"],
                         len(EGO_SINGLE_BOX_V1.point_cloud()))
        self.assertEqual(self.binding.manifest["geometry"]["minimum_enu_m"],
                         list(EGO_SINGLE_BOX_V1.aabb.minimum))
        self.assertEqual(self.binding.manifest["geometry"]["maximum_enu_m"],
                         list(EGO_SINGLE_BOX_V1.aabb.maximum))

    def test_canonical_bytes_are_order_independent_and_reject_nonfinite(self):
        manifest = self.binding.manifest
        reordered = {key: manifest[key] for key in reversed(tuple(manifest))}
        self.assertEqual(canonical_manifest_bytes(reordered),
                         self.binding.canonical_manifest_bytes())

        invalid = deepcopy(manifest)
        invalid["origin_enu_m"][0] = float("nan")
        with self.assertRaises(PlannerSceneBindingError):
            canonical_manifest_bytes(invalid)

        invalid = deepcopy(manifest)
        invalid["unexpected"] = 1
        with self.assertRaises(PlannerSceneIdentityError):
            self.binding.validate_manifest(invalid)

    def test_manifest_hash_identity_units_frame_and_source_fail_closed(self):
        manifest = self.binding.manifest
        changes = (
            ("scene_hash", "0" * 64),
            ("profile_hash", "0" * 64),
            ("collision_hash", "0" * 64),
            ("voxel_hash", "0" * 64),
            ("point_cloud_hash", "0" * 64),
            ("frame", "world"),
            ("coordinate_frame", "NED"),
            ("units", {"length": "cm", "time": "s", "angle": "rad"}),
            ("geometry_source_identity", "C:\\elsewhere\\scene_profile.py"),
            ("binding_source_identity", "../planner_scene_binding.py"),
        )
        for key, value in changes:
            with self.subTest(key=key):
                invalid = deepcopy(manifest)
                invalid[key] = value
                with self.assertRaises(PlannerSceneBindingError):
                    self.binding.validate_manifest(invalid)

    def test_legacy_static_scene_is_never_an_alias(self):
        for key, value in (("scene_id", LEGACY_SCENE_ID),
                           ("scene_hash", LEGACY_SCENE_HASH)):
            with self.subTest(key=key):
                invalid = deepcopy(self.binding.manifest)
                invalid[key] = value
                with self.assertRaises(PlannerSceneIdentityError):
                    self.binding.validate_manifest(invalid)

    def test_profile_constructor_rejects_derived_geometry(self):
        other = EGO_SINGLE_BOX_V1.with_obstacle(EGO_SINGLE_BOX_V1.aabb,
                                                profile_id="other-scene-v1")
        with self.assertRaises(PlannerSceneIdentityError):
            PlannerSceneBinding(other)

    def test_profile_constructor_rejects_subclass_spoof(self):
        class SpoofProfile(SceneProfile):
            @property
            def profile_hash(self):
                return "0" * 64

        values = {field.name: getattr(EGO_SINGLE_BOX_V1, field.name)
                  for field in fields(SceneProfile)}
        with self.assertRaises(PlannerSceneIdentityError):
            PlannerSceneBinding(SpoofProfile(**values))

    def test_profile_constructor_rejects_injected_hash_or_point_cloud(self):
        spoof = deepcopy(EGO_SINGLE_BOX_V1)
        vars(spoof)["profile_hash"] = "0" * 64
        with self.assertRaises(PlannerSceneIdentityError):
            PlannerSceneBinding(spoof)

        spoof = deepcopy(EGO_SINGLE_BOX_V1)
        object.__setattr__(spoof, "point_cloud", lambda: ((999.0, 999.0, 999.0),))
        with self.assertRaises(PlannerSceneIdentityError):
            PlannerSceneBinding(spoof)

    def test_binding_freezes_profile_and_module_identity(self):
        binding = PlannerSceneBinding()
        original_manifest = binding.manifest
        original_point_cloud = binding.point_cloud
        original_aabb = binding.aabb
        other = EGO_SINGLE_BOX_V1.with_obstacle(EGO_SINGLE_BOX_V1.aabb,
                                                profile_id="other-scene-v1")
        with self.assertRaises(AttributeError):
            binding.profile = other

        with mock.patch.multiple(
            binding_module,
            GEOMETRY_ID="spoof:geometry",
            QUERY_VERSION="spoof-query",
            TICK_NS=1,
            PROFILE_SOURCE_IDENTITY="spoof-profile.py",
            BINDING_SOURCE_IDENTITY="spoof-binding.py",
            EXPECTED_POINT_CLOUD_HASH="0" * 64,
            EXPECTED_SCENE_HASH="0" * 64,
        ):
            self.assertEqual(binding.manifest, original_manifest)
            self.assertEqual(binding.point_cloud, original_point_cloud)
            self.assertEqual(binding.aabb, original_aabb)
            self.assertEqual(binding.validate_manifest(original_manifest), original_manifest)
            query_tests = PlannerSceneQueryTests()
            result = binding.query(query_tests.request())
            self.assertEqual(result["scene_hash"], EXPECTED_SCENE_HASH)

    def test_profile_methods_and_hashes_cannot_drift_after_construction(self):
        binding = PlannerSceneBinding()
        manifest = binding.manifest
        original_point_cloud = binding.point_cloud
        with mock.patch.object(SceneProfile, "profile_hash", new_callable=mock.PropertyMock,
                               return_value="0" * 64), \
             mock.patch.object(SceneProfile, "point_cloud",
                               return_value=((999.0, 999.0, 999.0),)):
            self.assertEqual(binding.manifest, manifest)
            self.assertEqual(binding.point_cloud_hash, EXPECTED_POINT_CLOUD_HASH)
            self.assertEqual(binding.point_cloud, original_point_cloud)

        with mock.patch.object(SceneProfile, "point_cloud",
                               return_value=((999.0, 999.0, 999.0),)):
            fresh = PlannerSceneBinding()
            self.assertEqual(fresh.manifest, manifest)
            self.assertEqual(fresh.point_cloud, original_point_cloud)
        with mock.patch.object(SceneProfile, "profile_hash", new_callable=mock.PropertyMock,
                               return_value="0" * 64):
            fresh = PlannerSceneBinding()
            self.assertEqual(fresh.manifest, manifest)

    def test_instances_have_no_storage_and_guard_ordinary_private_writes(self):
        binding = PlannerSceneBinding()
        original_manifest = binding.manifest
        original_aabb = binding.aabb
        original_cloud = binding.point_cloud

        self.assertEqual(PlannerSceneBinding.__slots__, ())
        with self.assertRaises(AttributeError):
            _ = binding.__dict__
        for name, value in (
            ("_payload", {"geometry": "spoofed"}),
            ("_aabb_minimum", (999.0, 999.0, 999.0)),
            ("__dict__", {}),
        ):
            with self.subTest(name=name):
                with self.assertRaises(AttributeError):
                    object.__setattr__(binding, name, value)

        with self.assertRaises(TypeError):
            class SpoofBinding(PlannerSceneBinding):
                pass

        self.assertEqual(binding.manifest, original_manifest)
        self.assertEqual(binding.aabb, original_aabb)
        self.assertEqual(binding.point_cloud, original_cloud)

    def test_binding_class_guard_rejects_ordinary_method_and_property_monkeypatch(self):
        binding = PlannerSceneBinding()
        original_manifest = binding.manifest
        original_query = binding.query

        with self.assertRaises(TypeError):
            PlannerSceneBinding.query = lambda self, request: {"spoofed": True}
        with self.assertRaises(TypeError):
            PlannerSceneBinding.manifest = property(lambda self: {"spoofed": True})
        with self.assertRaises(TypeError):
            del PlannerSceneBinding.query
        with self.assertRaises(TypeError):
            del PlannerSceneBinding.manifest

        # The class dictionary is a read-only mapping proxy, so the ordinary
        # class mutation guard has no second supported assignment route.
        with self.assertRaises(TypeError):
            PlannerSceneBinding.__dict__["query"] = lambda self, request: {"spoofed": True}
        with self.assertRaises(TypeError):
            PlannerSceneBinding.__dict__["manifest"] = property(
                lambda self: {"spoofed": True})

        fresh = PlannerSceneBinding()
        self.assertEqual(binding.manifest, original_manifest)
        self.assertEqual(fresh.manifest, original_manifest)
        self.assertEqual(binding.query, original_query)
        self.assertIs(type(binding), PlannerSceneBinding)

    def test_new_instances_ignore_monkeypatched_helper_and_module_constants(self):
        original_manifest = EGO_SINGLE_BOX_BINDING.manifest
        with mock.patch.object(
            binding_module,
            "_fixed_identities",
            side_effect=AssertionError("construction must not call the helper"),
        ), mock.patch.multiple(
            binding_module,
            GEOMETRY_ID="spoof:geometry",
            QUERY_VERSION="spoof-query",
            TICK_NS=1,
            PROFILE_SOURCE_IDENTITY="spoof-profile.py",
            BINDING_SOURCE_IDENTITY="spoof-binding.py",
            EXPECTED_POINT_CLOUD_HASH="0" * 64,
            EXPECTED_SCENE_HASH="0" * 64,
        ):
            fresh = PlannerSceneBinding()
            self.assertEqual(fresh.manifest, original_manifest)
            self.assertEqual(fresh.scene_hash, original_manifest["scene_hash"])
            self.assertEqual(fresh.point_cloud, EGO_SINGLE_BOX_BINDING.point_cloud)

    @staticmethod
    def _symlink_or_skip(link: Path, target: Path, *, directory: bool = False) -> None:
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as error:
            raise unittest.SkipTest(f"symlink creation unavailable: {error}") from error

    def test_manifest_file_path_is_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "planner-scene.json"
            path.write_text(json.dumps(self.binding.manifest), encoding="utf-8")
            self.assertEqual(self.binding.load_manifest(path), self.binding.manifest)

            with self.assertRaises(PlannerSceneBindingError):
                self.binding.load_manifest(Path(directory) / "missing.json")
            with self.assertRaises(PlannerSceneBindingError):
                self.binding.load_manifest(Path(directory))

            bad = Path(directory) / "bad.json"
            bad.write_text("{bad", encoding="utf-8")
            with self.assertRaises(PlannerSceneBindingError):
                self.binding.load_manifest(bad)

            duplicate = Path(directory) / "duplicate.json"
            duplicate.write_text('{"scene_id":"a", "scene_id":"b"}', encoding="utf-8")
            with self.assertRaises(PlannerSceneBindingError):
                self.binding.load_manifest(duplicate)

            symlink_file = Path(directory) / "manifest-file-link.json"
            self._symlink_or_skip(symlink_file, path)
            with self.assertRaises(PlannerSceneBindingError):
                self.binding.load_manifest(symlink_file)

            real_parent = Path(directory) / "real-parent"
            real_parent.mkdir()
            parent_manifest = real_parent / "planner-scene.json"
            parent_manifest.write_text(json.dumps(self.binding.manifest), encoding="utf-8")
            symlink_parent = Path(directory) / "parent-link"
            self._symlink_or_skip(symlink_parent, real_parent, directory=True)
            with self.assertRaises(PlannerSceneBindingError):
                self.binding.load_manifest(symlink_parent / parent_manifest.name)

        with self.assertRaises(PlannerSceneBindingError):
            self.binding.load_manifest("bad\x00path.json")


class PlannerSceneQueryTests(unittest.TestCase):
    binding = EGO_SINGLE_BOX_BINDING
    epoch = "a" * 32

    def request(self, **changes):
        manifest = self.binding.manifest
        request = {
            "scene_id": manifest["scene_id"],
            "scene_hash": manifest["scene_hash"],
            "profile_hash": manifest["profile_hash"],
            "collision_hash": manifest["collision_hash"],
            "voxel_hash": manifest["voxel_hash"],
            "point_cloud_hash": manifest["point_cloud_hash"],
            "query_version": QUERY_VERSION,
            "epoch": self.epoch,
            "step": 3,
            "sim_time_ns": 3 * 1_000_000,
            "body_id": "uav1",
            "geometry_id": GEOMETRY_ID,
            "point_enu_m": [0.0, 0.0, 2.5],
            "source_identity": BINDING_SOURCE_IDENTITY,
        }
        request.update(changes)
        return request

    def test_contact_query_is_geometry_only(self):
        result = self.binding.query(self.request())
        self.assertEqual(result["result"], "contact")
        self.assertEqual(result["observation"], "valid")
        envelope = result["envelope"]
        self.assertEqual(envelope["schema"], "wksim.planner-contact.v1")
        self.assertEqual(envelope["epoch"], self.epoch)
        self.assertEqual(envelope["step"], 3)
        self.assertEqual(envelope["sim_time_ns"], 3_000_000)
        self.assertEqual(envelope["valid_from_step"], 3)
        self.assertEqual(envelope["valid_until_step"], 3)
        self.assertEqual(envelope["body_id"], "uav1")
        self.assertEqual(envelope["geometry_id"], GEOMETRY_ID)
        self.assertEqual(envelope["normal_enu"], [-1.0, 0.0, 0.0])
        self.assertEqual(envelope["penetration_m"], 0.5)
        self.assertNotIn("force", envelope)
        self.assertNotIn("impulse", envelope)
        self.assertNotIn("terrain_height_enu_m", result)

    def test_boundary_and_outside_queries(self):
        lower = self.binding.aabb.minimum
        result = self.binding.query(self.request(point_enu_m=list(lower)))
        self.assertEqual(result["result"], "contact")
        self.assertEqual(result["envelope"]["penetration_m"], 0.0)

        outside = list(self.binding.aabb.maximum)
        outside[0] += 0.01
        result = self.binding.query(self.request(point_enu_m=outside))
        self.assertEqual(result["result"], "no_contact")
        self.assertIsNone(result["envelope"])

    def test_query_epoch_step_time_identity_and_nonfinite_inputs_fail_closed(self):
        changes = (
            ("epoch", "A" * 32),
            ("epoch", "a" * 31),
            ("step", True),
            ("step", -1),
            ("sim_time_ns", 4_000_000),
            ("sim_time_ns", True),
            ("body_id", ""),
            ("body_id", " uav1"),
            ("geometry_id", LEGACY_SCENE_ID),
            ("query_version", "other-query-v1"),
            ("source_identity", PROFILE_SOURCE_IDENTITY),
            ("point_enu_m", [float("nan"), 0.0, 0.0]),
            ("scene_hash", LEGACY_SCENE_HASH),
            ("profile_hash", "0" * 64),
        )
        for key, value in changes:
            with self.subTest(key=key, value=value):
                with self.assertRaises(PlannerSceneBindingError):
                    self.binding.query(self.request(**{key: value}))

        invalid = self.request(unexpected=1)
        with self.assertRaises(PlannerSceneBindingError):
            self.binding.query(invalid)


if __name__ == "__main__":
    unittest.main()
