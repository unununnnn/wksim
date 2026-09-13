"""Read-only pure-Python readiness probe for the G4 terrain interface (#29).

Verifies, without native builds, .so/.dll loading, ROS, flight controllers,
models, UE, MATLAB, or any process start/stop:

1. Interface shapes of the planner/runtime/terrain seam modules.
2. Configuration and message identity (frozen scene hashes, manifest
   schemas, committed binding hashes, three distinct identity layers).
3. Fail-closed semantics (hash mismatch, foreign epoch, stale/future
   feedback, freeze/recover discipline, no-force contract, query identity
   rejection).

Writes a JSON report to ``--output`` (default: ``probe-output.json`` next to
this file). Exit code 0 only if every check passes.
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CHECKS = []


def check(check_id, fn):
    """Run one probe check and record a structured pass/fail result."""
    try:
        detail = fn()
    except Exception as exc:  # noqa: BLE001 - the report must record any failure
        CHECKS.append({"id": check_id, "status": "fail",
                       "detail": f"{type(exc).__name__}: {exc}"})
        return
    CHECKS.append({"id": check_id, "status": "pass", "detail": detail})


def expect_raises(exc_types, fn, contains=None):
    try:
        fn()
    except exc_types as exc:
        if contains is not None and contains not in str(exc):
            raise AssertionError(f"expected {contains!r} in {exc!r}")
        return f"{type(exc).__name__}: {exc}"
    raise AssertionError(f"expected {exc_types}")


EPOCH_RUN = "a" * 32
EPOCH_FOREIGN = "b" * 32


# --- 1. Interface shapes -----------------------------------------------------

def shape_static_contact():
    from Simulator.wksim_core import static_contact as sc
    assert sc.SCHEMA == "wksim.contact.v1"
    assert sc.CONFIG_SCHEMA == "wksim.static-scene.v1"
    assert sc.TICK_NS == 1_000_000
    for name in ("query", "require_fresh", "support_height_enu_m"):
        assert callable(getattr(sc.StaticScene, name)), name
    err = sc.ContactError("contact_invalid")
    assert err.reason == "contact_invalid"
    return "schema/tick/class surface OK"


def shape_contact_observer():
    from Simulator.wksim_runtime import contact_observer as co
    assert co.FROZEN_SCENE_SHA256 == (
        "60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514")
    assert co.CONTACT_FIELDS == {
        "schema", "scene_id", "scene_hash", "epoch", "step", "sim_time_ns",
        "valid_from_step", "valid_until_step", "body_id", "geometry_id",
        "contact_point_enu_m", "normal_enu", "penetration_m",
        "source_identity",
    }
    forbidden = {"force", "force_n", "forces", "impulse", "impulses",
                 "stiffness", "damping", "friction", "wrench", "torque"}
    assert not (co.CONTACT_FIELDS & forbidden), "force fields must not exist"
    for name in ("observe_step", "validate_envelope", "recover",
                 "get_display_manifest"):
        assert callable(getattr(co.ContactObserver, name)), name
    return "observer surface OK; envelope carries no force/impulse fields"


def shape_terrain_feedback():
    from Simulator.wksim_runtime import terrain_feedback as tf
    assert tf.VEHICLE60_SIZE == 60 and tf.TERRAIN15_SIZE == 15
    assert tf.STATE120_SIZE == 120
    assert tf.STACK_BODIES == {"arducopter": "uav1", "px4": "uav2"}
    for name in ("query_terrain", "manifest"):
        assert callable(getattr(tf.TerrainFeedback, name)), name
    assert callable(tf.vehicle60_to_enu_query_point)
    assert callable(tf.support_height_to_terrain15d)
    return "terrain seam surface OK"


def shape_planner_scene_binding():
    from Simulator.wksim_runtime import planner_scene_binding as pb
    assert pb.MANIFEST_SCHEMA == "wksim.planner-scene-binding.v1"
    assert pb.CONTACT_SCHEMA == "wksim.planner-contact.v1"
    assert pb.QUERY_VERSION == "planner-aabb-point-contact-v1"
    assert pb.GEOMETRY_ID == "ego-single-box-v1:obstacle"
    binding = pb.EGO_SINGLE_BOX_BINDING
    for name in ("query", "canonical_manifest_bytes", "validate_manifest",
                 "load_manifest"):
        assert callable(getattr(binding, name)), name
    for name in ("manifest", "scene_id", "scene_hash", "geometry_id",
                 "profile", "aabb", "point_cloud", "point_cloud_hash"):
        getattr(binding, name)
    return "binding surface OK"


def shape_joint_wiring():
    """Statically verify the JointPhysics terrain seam wiring (read-only)."""
    joint = (REPO_ROOT / "Simulator/wksim_core/joint.py").read_text(encoding="utf-8")
    assert "terrain_feedback=None" in joint
    assert ("req['terrain'] = self.terrain_feedback.query_terrain(name, tick, "
            "self.states[name])") in joint
    assert "Missing prior state for" in joint
    runtime = (REPO_ROOT / "Simulator/wksim_runtime/joint_runtime.py").read_text(
        encoding="utf-8")
    assert "terrain_feedback=TerrainFeedback(epoch)" in runtime
    assert "terrain_feedback=terrain_feedback" in runtime
    assert "terrain_feedback.manifest()" in runtime
    return "joint.py:33,52,185-188 and joint_runtime.py:636-638,722 wiring present"


# --- 2. Configuration / message identity -------------------------------------

def identity_static_scene_config():
    import hashlib
    from Simulator.wksim_core import static_contact as sc
    path = REPO_ROOT / "Simulator/wksim_runtime/static-scene-v1.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    assert config["schema"] == "wksim.static-scene.v1"
    assert config["scene_id"] == "static-plane-box-v1"
    assert config["coordinate_frame"] == "ENU" and config["unit"] == "metre"
    geometry = {
        "origin_enu_m": config["origin_enu_m"],
        "plane": config["plane"],
        "box": config["box"],
    }
    recomputed = hashlib.sha256(
        sc._canonical_geometry(geometry).encode("utf-8")).hexdigest()
    frozen = ("60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514")
    assert recomputed == config["scene_sha256"] == frozen
    scene = sc.load_scene(path)
    assert scene.scene_sha256 == frozen
    assert scene.box_center == (2.0, 0.0, 0.5) and scene.box_size == (1.0, 1.0, 1.0)
    return f"fixture scene identity pinned: {frozen[:12]}..."


def identity_display_manifest():
    from Simulator.wksim_runtime.contact_observer import ContactObserver
    observer = ContactObserver(run_epoch=EPOCH_RUN)
    manifest = observer.get_display_manifest()
    assert manifest["schema"] == "wksim.display-manifest.v1"
    assert manifest["scene_id"] == "static-plane-box-v1"
    assert manifest["scene_hash"] == (
        "60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514")
    assert manifest["coordinate_frame"] == "ENU" and manifest["unit"] == "metre"
    return "display manifest bound to fixture identity"


def identity_terrain_manifest():
    from Simulator.wksim_runtime.terrain_feedback import TerrainFeedback
    feedback = TerrainFeedback(EPOCH_RUN)
    manifest = feedback.manifest()
    assert manifest["schema"] == "wksim.terrain-feedback-manifest.v1"
    assert manifest["scene_id"] == "static-plane-box-v1"
    assert manifest["scene_hash"] == (
        "60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514")
    assert manifest["epoch"] == EPOCH_RUN
    assert manifest["mapping"] == (
        "state[k-1].Vehicle60 -> world ENU support height -> terrain[k].Terrain15D")
    assert set(manifest["stacks"]) == {"arducopter", "px4"}
    return "terrain feedback manifest identity OK"


def identity_planner_binding_manifest():
    import hashlib
    from Simulator.wksim_runtime import planner_scene_binding as pb
    binding = pb.EGO_SINGLE_BOX_BINDING
    manifest = binding.manifest
    assert manifest["schema"] == "wksim.planner-scene-binding.v1"
    assert manifest["scene_id"] == "ego-single-box-v1"
    assert manifest["profile_hash"] == pb.EXPECTED_PROFILE_HASH
    assert manifest["collision_hash"] == pb.EXPECTED_COLLISION_HASH
    assert manifest["voxel_hash"] == pb.EXPECTED_VOXEL_HASH
    assert manifest["point_cloud_hash"] == pb.EXPECTED_POINT_CLOUD_HASH
    assert manifest["physics_authority"] == "WSL"
    assert manifest["capabilities"] == {
        "contact_geometry": True, "forces": False, "impulses": False,
        "terrain_response": False,
    }
    assert manifest["visual_mirror"] == {"system": "UE", "binding_status": "not_bound"}
    digest = hashlib.sha256(binding.canonical_manifest_bytes()).hexdigest()
    assert digest == manifest["scene_hash"] == pb.EXPECTED_SCENE_HASH
    assert binding.scene_hash == pb.EXPECTED_SCENE_HASH
    assert len(binding.point_cloud) == 11000
    return (f"planner binding hashes pinned; canonical bytes hash to "
            f"{pb.EXPECTED_SCENE_HASH[:12]}...")


def identity_three_layers():
    manifest = json.loads((REPO_ROOT / "docs/plan/29-terrain-evidence-manifest.json")
                          .read_text(encoding="utf-8"))
    assert manifest["status"] == "partial_open"
    assert manifest["acceptance"] is False
    assert manifest["blocking_issue"] == 9
    visual = manifest["scene_identities"]["visual_static_scene"]
    real = manifest["scene_identities"]["real_terrain_scene"]
    assert visual["scene_sha256"].startswith("60ae5097")
    assert real["scene_sha256"].startswith("4889e2ea")
    from Simulator.wksim_runtime import planner_scene_binding as pb
    layers = {visual["scene_sha256"], real["scene_sha256"], pb.EXPECTED_SCENE_HASH}
    assert len(layers) == 3, "three identity layers must be pairwise distinct"
    assert set(manifest["unproven_boundaries"]) == {
        "missing_real_ue_physics_colocation",
        "missing_fc_closed_loop",
        "missing_slope_contact_force_dynamics",
    }
    return "evidence manifest still declares partial_open with 3 unproven boundaries"


# --- 3. Fail-closed semantics -------------------------------------------------

def failclosed_scene_hash_mismatch():
    from Simulator.wksim_core.static_contact import ContactError, StaticScene
    from Simulator.wksim_runtime.contact_observer import ContactObserver
    detail = expect_raises(
        ContactError,
        lambda: ContactObserver(run_epoch=EPOCH_RUN, expected_sha256="0" * 64),
        contains="scene_hash_mismatch")
    config = json.loads((REPO_ROOT / "Simulator/wksim_runtime/static-scene-v1.json")
                        .read_text(encoding="utf-8"))
    config["box"]["size_m"] = [1.0, 1.0, 2.0]
    expect_raises(ContactError, lambda: StaticScene(config),
                  contains="scene_hash_mismatch")
    return f"observer bind + tampered geometry both rejected ({detail})"


def failclosed_scene_not_found():
    from Simulator.wksim_core.static_contact import ContactError
    from Simulator.wksim_runtime.contact_observer import ContactObserver
    return expect_raises(
        ContactError,
        lambda: ContactObserver(scene_source=REPO_ROOT / "no-such-scene.json",
                                run_epoch=EPOCH_RUN),
        contains="scene_not_found")


def failclosed_foreign_epoch_and_frozen_block():
    from Simulator.wksim_runtime.contact_observer import ContactObserver
    from Simulator.wksim_runtime.terrain_feedback import TerrainFeedback
    observer = ContactObserver(run_epoch=EPOCH_RUN)
    result = observer.observe_step(1, "uav1", [20.0, 10.0, 5.0], epoch=EPOCH_FOREIGN)
    assert result["freeze"] is True and result["reason"] == "foreign_epoch"
    assert observer.frozen is True and observer.freeze_step == 1
    again = observer.observe_step(2, "uav1", [20.0, 10.0, 5.0])
    assert again["status"] == "frozen" and again["envelope"] is None
    feedback = TerrainFeedback(EPOCH_RUN)
    feedback.observers["px4"].observe_step(1, "uav2", [0.0, 0.0, 0.0],
                                           epoch=EPOCH_FOREIGN)
    detail = expect_raises(
        RuntimeError,
        lambda: feedback.query_terrain("px4", 2, [0.0] * 120),
        contains="frozen")
    return f"foreign epoch freezes; frozen seam blocks queries ({detail})"


def failclosed_stale_feedback():
    from Simulator.wksim_runtime.contact_observer import ContactObserver
    observer = ContactObserver(run_epoch=EPOCH_RUN)
    first = observer.observe_step(5, "uav1", [20.0, 10.0, 5.0])
    assert first["status"] == "ok" and first["result"] == "no_contact"
    stale = observer.observe_step(5, "uav1", [20.0, 10.0, 5.0])
    assert stale["freeze"] is True and stale["reason"] == "stale_feedback"
    return "repeated authority step frozen as stale_feedback"


def failclosed_recover_discipline():
    from Simulator.wksim_core.static_contact import ContactError
    from Simulator.wksim_runtime.contact_observer import ContactObserver
    fresh = ContactObserver(run_epoch=EPOCH_RUN)
    expect_raises(ContactError,
                  lambda: fresh.recover(1, "uav1", [0.0, 0.0, 0.0]),
                  contains="contact_invalid")
    observer = ContactObserver(run_epoch=EPOCH_RUN)
    observer.observe_step(5, "uav1", [20.0, 10.0, 5.0])
    observer.observe_step(5, "uav1", [20.0, 10.0, 5.0])  # stale freeze
    expect_raises(ContactError,
                  lambda: observer.recover(5, "uav1", [20.0, 10.0, 5.0]),
                  contains="stale_feedback")
    recovered = observer.recover(6, "uav1", [20.0, 10.0, 5.0])
    assert recovered["status"] == "recovered" and observer.frozen is False
    assert recovered["previous_reason"] == "stale_feedback"
    return "recover requires freeze, forward step, fresh evidence"


def failclosed_external_envelope_with_force_field():
    from Simulator.wksim_runtime.contact_observer import ContactObserver
    observer = ContactObserver(run_epoch=EPOCH_RUN)
    result = observer.observe_step(1, "uav1", [2.0, 0.0, 0.5])  # inside box
    assert result["result"] == "contact"
    envelope = dict(result["envelope"])
    assert envelope["schema"] == "wksim.contact.v1"
    poisoned = dict(envelope, force_n=1.0)
    verdict = observer.validate_envelope(poisoned, 1)
    assert verdict["freeze"] is True and verdict["reason"] == "contact_invalid"
    return "envelope carrying an extra force field freezes as contact_invalid"


def failclosed_vehicle60_mapping():
    from Simulator.wksim_runtime.terrain_feedback import vehicle60_to_enu_query_point
    state = [float(i) for i in range(60)]
    state[6], state[7], state[8] = 12.5, 34.0, -6.25  # N, E, D
    assert vehicle60_to_enu_query_point(state) == [34.0, 12.5, 6.25]
    expect_raises(ValueError, lambda: vehicle60_to_enu_query_point([0.0] * 59))
    bad = [0.0] * 60
    bad[7] = True
    expect_raises(ValueError, lambda: vehicle60_to_enu_query_point(bad))
    nan_state = [0.0] * 60
    nan_state[8] = float("nan")
    expect_raises(ValueError, lambda: vehicle60_to_enu_query_point(nan_state))
    return "Vehicle60 NED -> ENU mapping exact; length/bool/NaN rejected"


def failclosed_terrain15d_mapping():
    from Simulator.wksim_runtime.terrain_feedback import support_height_to_terrain15d
    flat = support_height_to_terrain15d(0.0)
    assert flat == [0.0] * 15 and not str(flat[0]).startswith("-")
    elevated = support_height_to_terrain15d(1.0)
    assert elevated == [-1.0] + [0.0] * 14
    expect_raises(ValueError, lambda: support_height_to_terrain15d(float("nan")))
    expect_raises(ValueError, lambda: support_height_to_terrain15d(True))
    return "support height -> Terrain15D exact; zero canonicalized; NaN/bool rejected"


def failclosed_observer_injection():
    from Simulator.wksim_runtime.contact_observer import ContactObserver
    from Simulator.wksim_runtime.terrain_feedback import TerrainFeedback
    observers = {stack: ContactObserver(run_epoch=EPOCH_FOREIGN)
                 for stack in ("arducopter", "px4")}
    feedback = TerrainFeedback(EPOCH_RUN, observers=observers)
    detail = expect_raises(
        RuntimeError,
        lambda: feedback.query_terrain("arducopter", 1, [0.0] * 120))
    expect_raises(
        ValueError,
        lambda: TerrainFeedback(EPOCH_RUN,
                                observers={"arducopter": observers["arducopter"]}))
    expect_raises(
        ValueError,
        lambda: TerrainFeedback(EPOCH_RUN,
                                observers=dict(observers, extra=observers["px4"])))
    return f"foreign-epoch injected observer fail-closed ({detail}); dict shape enforced"


def failclosed_query_terrain_inputs():
    from Simulator.wksim_runtime.terrain_feedback import TerrainFeedback
    feedback = TerrainFeedback(EPOCH_RUN)
    expect_raises(ValueError, lambda: feedback.query_terrain("hex", 1, [0.0] * 120))
    expect_raises(ValueError, lambda: feedback.query_terrain("px4", 1, [0.0] * 119))
    state = [0.0] * 120
    state[6] = float("inf")
    expect_raises(ValueError, lambda: feedback.query_terrain("px4", 1, state))
    return "unknown stack / wrong state size / non-finite state rejected"


def _planner_request(**overrides):
    from Simulator.wksim_runtime import planner_scene_binding as pb
    request = {
        "scene_id": "ego-single-box-v1",
        "scene_hash": pb.EXPECTED_SCENE_HASH,
        "profile_hash": pb.EXPECTED_PROFILE_HASH,
        "collision_hash": pb.EXPECTED_COLLISION_HASH,
        "voxel_hash": pb.EXPECTED_VOXEL_HASH,
        "point_cloud_hash": pb.EXPECTED_POINT_CLOUD_HASH,
        "query_version": pb.QUERY_VERSION,
        "epoch": EPOCH_RUN,
        "step": 3,
        "sim_time_ns": 3 * 1_000_000,
        "body_id": "uav1",
        "geometry_id": pb.GEOMETRY_ID,
        "point_enu_m": [0.0, 0.0, 1.0],
        "source_identity": pb.BINDING_SOURCE_IDENTITY,
    }
    request.update(overrides)
    return request


def failclosed_planner_query_identity():
    from Simulator.wksim_runtime import planner_scene_binding as pb
    binding = pb.EGO_SINGLE_BOX_BINDING
    contact = binding.query(_planner_request())
    assert contact["result"] == "contact"
    envelope = contact["envelope"]
    assert envelope["schema"] == "wksim.planner-contact.v1"
    assert envelope["valid_from_step"] == envelope["valid_until_step"] == 3
    assert envelope["penetration_m"] >= 0.0
    outside = binding.query(_planner_request(point_enu_m=[9.0, 5.0, 3.0]))
    assert outside["result"] == "no_contact" and outside["envelope"] is None
    expect_raises(pb.PlannerSceneIdentityError, lambda: binding.query(
        _planner_request(scene_id="static-plane-box-v1",
                         scene_hash=pb.LEGACY_SCENE_HASH)))
    probe_hash = "4889e2ea32146b734a816281915842da1da27c0df78c588d688cd2656f2bb300"
    expect_raises(pb.PlannerSceneIdentityError, lambda: binding.query(
        _planner_request(scene_hash=probe_hash)))
    expect_raises(pb.PlannerSceneIdentityError, lambda: binding.query(
        _planner_request(profile_hash="0" * 64)))
    unknown = _planner_request()
    unknown["unexpected"] = 1
    expect_raises(pb.PlannerSceneBindingError, lambda: binding.query(unknown))
    expect_raises(pb.PlannerSceneBindingError, lambda: binding.query(
        _planner_request(point_enu_m=[0.0, float("nan"), 1.0])))
    expect_raises(pb.PlannerSceneBindingError, lambda: binding.query(
        _planner_request(sim_time_ns=1)))
    return ("planner query: contact/no_contact valid; legacy and probe identities, "
            "wrong hash, unknown field, NaN, bad sim_time all rejected")


SECTIONS = (
    ("shape", (
        shape_static_contact,
        shape_contact_observer,
        shape_terrain_feedback,
        shape_planner_scene_binding,
        shape_joint_wiring,
    )),
    ("identity", (
        identity_static_scene_config,
        identity_display_manifest,
        identity_terrain_manifest,
        identity_planner_binding_manifest,
        identity_three_layers,
    )),
    ("failclosed", (
        failclosed_scene_hash_mismatch,
        failclosed_scene_not_found,
        failclosed_foreign_epoch_and_frozen_block,
        failclosed_stale_feedback,
        failclosed_recover_discipline,
        failclosed_external_envelope_with_force_field,
        failclosed_vehicle60_mapping,
        failclosed_terrain15d_mapping,
        failclosed_observer_injection,
        failclosed_query_terrain_inputs,
        failclosed_planner_query_identity,
    )),
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(Path(__file__).resolve().parent
                                                / "probe-output.json"))
    args = parser.parse_args(argv)

    for section, functions in SECTIONS:
        for fn in functions:
            check(f"{section}.{fn.__name__.split('_', 1)[1]}", fn)

    passed = sum(1 for item in CHECKS if item["status"] == "pass")
    report = {
        "schema": "omp.g4-terrain-probe.v1",
        "scope": ("G4 terrain interface (#29): read-only pure-Python probe of "
                  "interface shapes, config/message identity, and fail-closed "
                  "semantics; no native/.so/.dll, ROS, FC, model, UE, MATLAB, "
                  "or process control"),
        "repo_relative_root": True,
        "checks": CHECKS,
        "summary": {
            "total": len(CHECKS),
            "passed": passed,
            "failed": len(CHECKS) - passed,
            "status": "pass" if passed == len(CHECKS) else "fail",
        },
    }
    Path(args.output).write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8", newline="\n")
    print(json.dumps(report["summary"], sort_keys=True))
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
