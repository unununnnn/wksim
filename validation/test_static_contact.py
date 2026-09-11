import hashlib
import json
import unittest
from pathlib import Path

from Simulator.wksim_core.static_contact import (
    CONFIG_SCHEMA, SCHEMA, ContactError, StaticScene, load_scene,
)


ROOT = Path(__file__).resolve().parents[1]
EPOCH = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
GEOMETRY = {
    "origin_enu_m": [0.0, 0.0, 0.0],
    "plane": {"geometry_id": "plane_z0", "z_m": 0.0},
    "box": {"geometry_id": "box_0", "center_enu_m": [2.0, 0.0, 0.5], "size_m": [1.0, 1.0, 1.0]},
}
HASH = "60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514"


def make_config(origin=(0.0, 0.0, 0.0), plane_z=0.0, box_center=(2.0, 0.0, 0.5), box_size=(1.0, 1.0, 1.0)):
    geometry = {
        "origin_enu_m": list(origin),
        "plane": {"geometry_id": "plane_z0", "z_m": float(plane_z)},
        "box": {"geometry_id": "box_0", "center_enu_m": list(box_center), "size_m": list(box_size)},
    }
    canonical = json.dumps(geometry, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    expected_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "schema": CONFIG_SCHEMA,
        "scene_id": "static-plane-box-v1",
        "coordinate_frame": "ENU",
        "unit": "metre",
        "origin_enu_m": list(origin),
        "plane": {"geometry_id": "plane_z0", "z_m": float(plane_z)},
        "box": {"geometry_id": "box_0", "center_enu_m": list(box_center), "size_m": list(box_size)},
        "scene_sha256": expected_hash,
    }


def config():
    return {
        "schema": CONFIG_SCHEMA,
        "scene_id": "static-plane-box-v1",
        "coordinate_frame": "ENU",
        "unit": "metre",
        "origin_enu_m": [0.0, 0.0, 0.0],
        "plane": {"geometry_id": "plane_z0", "z_m": 0.0},
        "box": {"geometry_id": "box_0", "center_enu_m": [2.0, 0.0, 0.5], "size_m": [1.0, 1.0, 1.0]},
        "scene_sha256": HASH,
    }


class ConfigTests(unittest.TestCase):
    def test_valid_config(self):
        scene = StaticScene(config())
        self.assertEqual(scene.scene_id, "static-plane-box-v1")
        self.assertEqual(scene.scene_sha256, HASH)
        self.assertEqual(scene.box_center, (2.0, 0.0, 0.5))

    def test_frozen_file_matches(self):
        scene = load_scene(ROOT / "Simulator/wksim_runtime/static-scene-v1.json")
        self.assertEqual(scene.scene_sha256, HASH)

    def test_hash_mismatch_rejected(self):
        bad = config()
        bad["scene_sha256"] = "0" * 64
        with self.assertRaises(ContactError) as ctx:
            StaticScene(bad)
        self.assertEqual(ctx.exception.reason, "scene_hash_mismatch")

    def test_invalid_configs_rejected(self):
        for mutate in (
            lambda c: c.update(schema="other"),
            lambda c: c.update(coordinate_frame="NED"),
            lambda c: c.update(unit="cm"),
            lambda c: c.update(extra=1),
            lambda c: c.pop("plane"),
            lambda c: c.update(box={"geometry_id": "box_0", "center_enu_m": [2, 0, 0.5], "size_m": [1, 0, 1]}),
            lambda c: c.update(origin_enu_m=[0, 0, float("nan")]),
            lambda c: c.update(plane={"geometry_id": True, "z_m": 0.0}),
        ):
            bad = config()
            mutate(bad)
            with self.assertRaises(ContactError):
                StaticScene(bad)


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.scene = StaticScene(config())

    def test_plane_contact_below(self):
        out = self.scene.query(EPOCH, 10, "quad_1", [0.3, -0.2, -0.4])
        self.assertEqual(out["result"], "contact")
        env = out["envelope"]
        self.assertEqual(env["geometry_id"], "plane_z0")
        self.assertEqual(env["contact_point_enu_m"], [0.3, -0.2, 0.0])
        self.assertEqual(env["normal_enu"], [0.0, 0.0, 1.0])
        self.assertAlmostEqual(env["penetration_m"], 0.4)

    def test_plane_touching_is_contact_with_zero_depth(self):
        out = self.scene.query(EPOCH, 10, "quad_1", [1.0, 1.0, 0.0])
        self.assertEqual(out["result"], "contact")
        self.assertEqual(out["envelope"]["penetration_m"], 0.0)

    def test_no_contact_is_valid_observation(self):
        out = self.scene.query(EPOCH, 10, "quad_1", [0.0, 0.0, 0.5])
        self.assertEqual(out["result"], "no_contact")
        self.assertEqual(out["observation"], "valid")
        self.assertIsNone(out["envelope"])

    def test_box_contact_nearest_face(self):
        out = self.scene.query(EPOCH, 10, "quad_1", [2.0, 0.0, 0.9])
        env = out["envelope"]
        self.assertEqual(env["geometry_id"], "box_0")
        self.assertEqual(env["contact_point_enu_m"], [2.0, 0.0, 1.0])
        self.assertEqual(env["normal_enu"], [0.0, 0.0, 1.0])
        self.assertAlmostEqual(env["penetration_m"], 0.1)

    def test_box_contact_side_face(self):
        out = self.scene.query(EPOCH, 10, "quad_1", [1.6, 0.0, 0.5])
        env = out["envelope"]
        self.assertEqual(env["contact_point_enu_m"], [1.5, 0.0, 0.5])
        self.assertEqual(env["normal_enu"], [-1.0, 0.0, 0.0])

    def test_box_center_tie_is_deterministic(self):
        out = self.scene.query(EPOCH, 10, "quad_1", [2.0, 0.0, 0.5])
        env = out["envelope"]
        self.assertEqual(env["contact_point_enu_m"], [1.5, 0.0, 0.5])
        self.assertEqual(env["normal_enu"], [-1.0, 0.0, 0.0])
        self.assertAlmostEqual(env["penetration_m"], 0.5)

    def test_box_surface_inclusive(self):
        out = self.scene.query(EPOCH, 10, "quad_1", [2.0, 0.0, 1.0])
        self.assertEqual(out["envelope"]["penetration_m"], 0.0)
        self.assertEqual(out["envelope"]["geometry_id"], "box_0")

    def test_box_outside_above_plane_is_no_contact(self):
        out = self.scene.query(EPOCH, 10, "quad_1", [5.0, 5.0, 2.0])
        self.assertEqual(out["result"], "no_contact")

    def test_envelope_identity_and_one_step_validity(self):
        out = self.scene.query(EPOCH, 42, "quad_1", [0.0, 0.0, -0.1])
        env = out["envelope"]
        self.assertEqual(env["schema"], SCHEMA)
        self.assertEqual(env["scene_hash"], HASH)
        self.assertEqual(env["epoch"], EPOCH)
        self.assertEqual(env["step"], 42)
        self.assertEqual(env["sim_time_ns"], 42_000_000)
        self.assertEqual(env["valid_from_step"], 42)
        self.assertEqual(env["valid_until_step"], 42)
        self.assertEqual(env["body_id"], "quad_1")

    def test_malformed_epoch_rejected(self):
        for bad in ("b" * 31, "B" * 32, "g" * 32, 42):
            with self.assertRaises(ContactError) as ctx:
                self.scene.query(bad, 10, "quad_1", [0.0, 0.0, -1.0])
            self.assertEqual(ctx.exception.reason, "contact_invalid")

    def test_bad_inputs_rejected(self):
        for point in ([0, 0], [0, 0, float("inf")], "xyz"):
            with self.assertRaises(ContactError):
                self.scene.query(EPOCH, 10, "quad_1", point)
        with self.assertRaises(ContactError):
            self.scene.query(EPOCH, True, "quad_1", [0, 0, -1])
        with self.assertRaises(ContactError):
            self.scene.query(EPOCH, 10, "", [0, 0, -1])


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.scene = StaticScene(config())
        self.env = self.scene.query(EPOCH, 42, "quad_1", [0.0, 0.0, -0.1])["envelope"]

    def test_fresh_on_declared_step(self):
        self.assertTrue(self.scene.require_fresh(self.env, 42, EPOCH))

    def test_stale_after_declared_step(self):
        with self.assertRaises(ContactError) as ctx:
            self.scene.require_fresh(self.env, 43, EPOCH)
        self.assertEqual(ctx.exception.reason, "stale_feedback")

    def test_future_before_declared_step(self):
        with self.assertRaises(ContactError) as ctx:
            self.scene.require_fresh(self.env, 41, EPOCH)
        self.assertEqual(ctx.exception.reason, "future_feedback")

    def test_foreign_epoch_rejected(self):
        with self.assertRaises(ContactError) as ctx:
            self.scene.require_fresh(self.env, 42, "b" * 32)
        self.assertEqual(ctx.exception.reason, "foreign_epoch")

    def test_wrong_scene_hash_rejected(self):
        other = dict(self.env, scene_hash="0" * 64)
        with self.assertRaises(ContactError) as ctx:
            self.scene.require_fresh(other, 42, EPOCH)
        self.assertEqual(ctx.exception.reason, "scene_hash_mismatch")

    def test_malformed_envelope_rejected(self):
        for bad in (None, {}, {"schema": "other"}, dict(self.env, valid_from_step=-1)):
            with self.assertRaises(ContactError):
                self.scene.require_fresh(bad, 42, EPOCH)


class SupportHeightTests(unittest.TestCase):
    def setUp(self):
        self.scene = StaticScene(config())

    def test_plane_support_height_outside_box(self):
        for pt in ((0.0, 0.0), (-5.0, 10.0), (1.49, 0.0), (2.51, 0.0), (2.0, 0.51), (2.0, -0.51)):
            with self.subTest(pt=pt):
                self.assertEqual(self.scene.support_height_enu_m(pt[0], pt[1]), 0.0)
                self.assertEqual(self.scene.support_height_enu_m(pt), 0.0)
                self.assertEqual(self.scene.support_height_enu_m([pt[0], pt[1], 10.0]), 0.0)

    def test_box_top_support_height(self):
        # Box center is (2.0, 0.0, 0.5), size (1.0, 1.0, 1.0) -> top is 0.5 + 0.5 = 1.0
        self.assertEqual(self.scene.support_height_enu_m(2.0, 0.0), 1.0)
        self.assertEqual(self.scene.support_height_enu_m((2.0, 0.0)), 1.0)
        self.assertEqual(self.scene.support_height_enu_m([2.0, 0.0, -0.5]), 1.0)
        self.assertEqual(self.scene.support_height_enu_m(2.2, -0.2), 1.0)

    def test_box_edge_inclusive(self):
        # Box footprint is [1.5, 2.5] x [-0.5, 0.5]
        edges = [
            (1.5, 0.0), (2.5, 0.0), (2.0, -0.5), (2.0, 0.5),
            (1.5, -0.5), (1.5, 0.5), (2.5, -0.5), (2.5, 0.5),
        ]
        for edge in edges:
            with self.subTest(edge=edge):
                self.assertEqual(self.scene.support_height_enu_m(edge[0], edge[1]), 1.0)
                self.assertEqual(self.scene.support_height_enu_m(edge), 1.0)

    def test_box_below_plane_takes_plane_height(self):
        # Box sunken below plane: plane_z = 0.0, box_center = (2.0, 0.0, -2.0), box_size = (1.0, 1.0, 1.0)
        # Box top is -2.0 + 0.5 = -1.5 < plane_z (0.0). Max must be plane_z (0.0).
        sunken = StaticScene(make_config(plane_z=0.0, box_center=(2.0, 0.0, -2.0), box_size=(1.0, 1.0, 1.0)))
        self.assertEqual(sunken.support_height_enu_m(2.0, 0.0), 0.0)
        self.assertEqual(sunken.support_height_enu_m(0.0, 0.0), 0.0)

    def test_nonzero_origin_enu_m(self):
        # Origin at (10.0, -5.0, 3.0), plane_z=0.0 (world ENU: 3.0)
        # Box center local (2.0, 0.0, 0.5) -> world ENU center (12.0, -5.0, 3.5), top world ENU 4.0
        # World footprint: [11.5, 12.5] x [-5.5, -4.5]
        shifted = StaticScene(make_config(origin=(10.0, -5.0, 3.0), plane_z=0.0, box_center=(2.0, 0.0, 0.5), box_size=(1.0, 1.0, 1.0)))
        # Outside footprint -> plane in world ENU: 3.0
        self.assertEqual(shifted.support_height_enu_m(0.0, 0.0), 3.0)
        self.assertEqual(shifted.support_height_enu_m(11.49, -5.0), 3.0)
        # Inside footprint -> box top in world ENU: 4.0
        self.assertEqual(shifted.support_height_enu_m(12.0, -5.0), 4.0)
        # Boundary -> box top in world ENU: 4.0
        self.assertEqual(shifted.support_height_enu_m(11.5, -5.5), 4.0)
        self.assertEqual(shifted.support_height_enu_m(12.5, -4.5), 4.0)

    def test_invalid_and_nonfinite_inputs_rejected(self):
        bads = [
            (True, 0.0),
            (0.0, False),
            (float("nan"), 0.0),
            (0.0, float("nan")),
            (float("inf"), 0.0),
            (0.0, float("-inf")),
            [0.0],
            [0.0, 0.0, 0.0, 0.0],
            [True, 0.0],
            [0.0, True],
            [float("nan"), 0.0],
            [0.0, float("nan")],
            [0.0, 0.0, float("nan")],
            "xy",
            123,
            None,
        ]
        for bad in bads:
            with self.subTest(bad=bad), self.assertRaises(ContactError):
                if isinstance(bad, tuple) and len(bad) == 2:
                    self.scene.support_height_enu_m(bad[0], bad[1])
                else:
                    self.scene.support_height_enu_m(bad)


if __name__ == "__main__":
    unittest.main()
