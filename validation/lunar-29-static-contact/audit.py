"""Independent auditor for the frozen slope/box contact fixture (#80).

Recomputes every expected result from the frozen scene configuration with
its own geometry math (does not import wksim_core.static_contact), then
compares raw results.jsonl field by field. Prints one JSON verdict.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASE_DIR = Path(__file__).resolve().parent
EPOCH = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
TICK_NS = 1_000_000
FACE_ORDER = ("x-", "x+", "y-", "y+", "z-", "z+")


def scene_hash(cfg):
    geometry = {"origin_enu_m": cfg["origin_enu_m"], "plane": cfg["plane"], "box": cfg["box"]}
    return hashlib.sha256(json.dumps(geometry, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("utf-8")).hexdigest()


def expect_query(cfg, point):
    px, py, pz = point
    cx, cy, cz = cfg["box"]["center_enu_m"]
    sx, sy, sz = (v / 2.0 for v in cfg["box"]["size_m"])
    dx, dy, dz = px - cx, py - cy, pz - cz
    if abs(dx) <= sx and abs(dy) <= sy and abs(dz) <= sz:
        candidates = (
            ("x-", sx + dx, [cx - sx, py, pz], [-1.0, 0.0, 0.0]),
            ("x+", sx - dx, [cx + sx, py, pz], [1.0, 0.0, 0.0]),
            ("y-", sy + dy, [px, cy - sy, pz], [0.0, -1.0, 0.0]),
            ("y+", sy - dy, [px, cy + sy, pz], [0.0, 1.0, 0.0]),
            ("z-", sz + dz, [px, py, cz - sz], [0.0, 0.0, -1.0]),
            ("z+", sz - dz, [px, py, cz + sz], [0.0, 0.0, 1.0]),
        )
        _, depth, cp, normal = min(candidates, key=lambda c: (c[1], FACE_ORDER.index(c[0])))
        return cfg["box"]["geometry_id"], cp, normal, depth
    if pz <= cfg["plane"]["z_m"]:
        return cfg["plane"]["geometry_id"], [px, py, cfg["plane"]["z_m"]], [0.0, 0.0, 1.0], cfg["plane"]["z_m"] - pz
    return None


def main():
    cfg = json.loads((ROOT / "Simulator/wksim_runtime/static-scene-v1.json").read_text(encoding="utf-8"))
    expected_hash = scene_hash(cfg)
    assert expected_hash == cfg["scene_sha256"], "scene hash mismatch in frozen config"
    cases = {c["case"]: c for c in json.loads((CASE_DIR / "cases.json").read_text(encoding="utf-8"))}
    results = [json.loads(line) for line in
               (CASE_DIR / "results.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(results) == len(cases), "result count mismatch"
    checked = 0
    for record in results:
        case = cases[record["case"]]
        assert record["expect"] == case["expect"], "expectation drift"
        assert record["actual"] == case["expect"], (record["case"], record["actual"], case["expect"])
        checked += 1
        if "envelope" not in record:
            continue
        env = record["envelope"]
        geometry_id, cp, normal, depth = expect_query(cfg, case["point"])
        assert env["schema"] == "wksim.contact.v1"
        assert env["scene_id"] == cfg["scene_id"] and env["scene_hash"] == expected_hash
        assert env["epoch"] == EPOCH and env["step"] == case["step"]
        assert env["sim_time_ns"] == case["step"] * TICK_NS
        assert env["valid_from_step"] == case["step"] and env["valid_until_step"] == case["step"]
        assert env["body_id"] == "fixture_body" and env["geometry_id"] == geometry_id
        assert env["contact_point_enu_m"] == cp, (env["contact_point_enu_m"], cp)
        assert env["normal_enu"] == normal
        assert abs(env["penetration_m"] - depth) < 1e-12
        assert env["source_identity"] == "Simulator/wksim_core/static_contact.py"
        checked += 12
    print(json.dumps({"status": "pass", "cases": len(results), "assertions": checked,
                      "skipped": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
