"""Independent auditor for the live physics-feedback contact run (#81).

Recomputes expectations from the recorded truth and frozen scene config
without importing wksim_core.static_contact, then checks every record,
the freeze/recovery sequence and the display manifest. Prints one JSON
verdict.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASE_DIR = Path(__file__).resolve().parent
TICK_NS = 1_000_000


def scene_hash(cfg):
    geometry = {"origin_enu_m": cfg["origin_enu_m"], "plane": cfg["plane"], "box": cfg["box"]}
    return hashlib.sha256(json.dumps(geometry, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("utf-8")).hexdigest()


def main():
    cfg = json.loads((ROOT / "Simulator/wksim_runtime/static-scene-v1.json").read_text(encoding="utf-8"))
    run_cfg = json.loads((CASE_DIR / "run-config.json").read_text(encoding="utf-8"))
    expected_hash = scene_hash(cfg)
    assert expected_hash == cfg["scene_sha256"]
    gap = run_cfg["feedback_gap"]
    truth_rows = [json.loads(line) for line in
                  (ROOT / run_cfg["truth_source"]).read_text(encoding="utf-8").splitlines()
                  if line.strip()]
    records = [json.loads(line) for line in
               (CASE_DIR / "records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records) == len(truth_rows), (len(records), len(truth_rows))
    events = json.loads((CASE_DIR / "events.json").read_text(encoding="utf-8"))
    manifest = json.loads((CASE_DIR / "display-manifest.json").read_text(encoding="utf-8"))
    checked = 0
    for row, record in zip(truth_rows, records):
        frame = row["frame"]
        z_ned = row["vehicle"][5]
        assert record["frame"] == frame
        if gap["after_frame"] < frame <= gap["resume_frame"]:
            assert record["result"] == "frozen", (frame, record["result"])
            checked += 1
            continue
        expected = "contact" if z_ned >= 0 else "no_contact"
        assert record["result"] == expected, (frame, record["result"], expected, z_ned)
        assert abs(record["z_ned_m"] - z_ned) < 1e-12
        checked += 2
        if expected == "contact":
            env = record["envelope"]
            assert env["schema"] == "wksim.contact.v1"
            assert env["scene_id"] == cfg["scene_id"] and env["scene_hash"] == expected_hash
            assert env["epoch"] == run_cfg["epoch"] and env["step"] == frame
            assert env["sim_time_ns"] == frame * TICK_NS
            assert env["valid_from_step"] == frame and env["valid_until_step"] == frame
            assert env["body_id"] == run_cfg["body_id"]
            if abs(row["vehicle"][3] - cfg["box"]["center_enu_m"][0]) <= 0.5 \
                    and abs(row["vehicle"][4] - cfg["box"]["center_enu_m"][1]) <= 0.5 \
                    and abs(-z_ned - cfg["box"]["center_enu_m"][2]) <= 0.5:
                assert env["geometry_id"] == cfg["box"]["geometry_id"]
            else:
                assert env["geometry_id"] == cfg["plane"]["geometry_id"]
                assert env["contact_point_enu_m"][2] == cfg["plane"]["z_m"]
                assert env["normal_enu"] == [0.0, 0.0, 1.0]
                assert abs(env["penetration_m"] - z_ned) < 1e-9, (env["penetration_m"], z_ned)
            checked += 9
    assert len(events) == 2, events
    freeze, recover = events
    assert freeze["event"] == "freeze" and freeze["reason"] == "stale_feedback"
    assert gap["after_frame"] < freeze["frame"] <= gap["resume_frame"]
    assert recover["event"] == "recover" and recover["frame"] > gap["resume_frame"]
    checked += 5
    assert manifest["scene_hash"] == expected_hash and manifest["scene_id"] == cfg["scene_id"]
    assert manifest["coordinate_frame"] == "ENU" and manifest["unit"] == "metre"
    kinds = {g["geometry_id"]: g["kind"] for g in manifest["display_geometries"]}
    assert kinds == {cfg["plane"]["geometry_id"]: "plane", cfg["box"]["geometry_id"]: "box"}
    checked += 4
    print(json.dumps({"status": "pass", "rows": len(records), "assertions": checked,
                      "skipped": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
