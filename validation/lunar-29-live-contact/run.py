"""Live physics-feedback contact run (#81 / 29-live-contact).

Consumes recorded real ArduCopter truth in frame order, queries the #79
static contact seam per authority step with strict one-step freshness,
and exercises the approved freeze/explicit-recovery rule across a declared
feedback gap. Also emits the display-side manifest bound to the same
scene hash. No UE, FC, model, ROS or hardware process is started.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from Simulator.wksim_core.static_contact import ContactError, load_scene  # noqa: E402

CASE_DIR = Path(__file__).resolve().parent


def main():
    cfg = json.loads((CASE_DIR / "run-config.json").read_text(encoding="utf-8"))
    scene = load_scene(ROOT / "Simulator/wksim_runtime/static-scene-v1.json")
    gap = cfg["feedback_gap"]
    records = []
    events = []
    frozen = False
    last_envelope = None
    with open(ROOT / cfg["truth_source"], "r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            frame = row["frame"]
            vehicle = row["vehicle"]
            z_ned = vehicle[5]
            point = [vehicle[3], vehicle[4], -z_ned]
            if gap["after_frame"] < frame <= gap["resume_frame"]:
                if not frozen:
                    try:
                        scene.require_fresh(last_envelope, frame, cfg["epoch"])
                        raise AssertionError("stale feedback was not rejected")
                    except ContactError as exc:
                        frozen = True
                        events.append({"event": "freeze", "frame": frame, "reason": exc.reason,
                                       "boundary_step": last_envelope["step"]})
                records.append({"frame": frame, "result": "frozen"})
                continue
            out = scene.query(cfg["epoch"], frame, cfg["body_id"], point)
            if out["result"] == "contact":
                scene.require_fresh(out["envelope"], frame, cfg["epoch"])
                last_envelope = out["envelope"]
            else:
                last_envelope = {"schema": "wksim.contact.v1", "scene_id": scene.scene_id,
                                 "scene_hash": scene.scene_sha256, "epoch": cfg["epoch"],
                                 "step": frame, "valid_from_step": frame, "valid_until_step": frame}
            if frozen:
                events.append({"event": "recover", "frame": frame,
                               "reason": "fresh valid feedback after freeze; explicit recovery"})
                frozen = False
            record = {"frame": frame, "z_ned_m": z_ned, "result": out["result"]}
            if out["envelope"] is not None:
                record["envelope"] = out["envelope"]
            records.append(record)
    manifest = {
        "schema": "wksim.display-manifest.v1",
        "scene_id": scene.scene_id,
        "scene_hash": scene.scene_sha256,
        "coordinate_frame": "ENU",
        "unit": "metre",
        "display_geometries": [
            {"geometry_id": scene.plane_id, "kind": "plane", "z_m": scene.plane_z},
            {"geometry_id": scene.box_id, "kind": "box",
             "center_enu_m": list(scene.box_center), "size_m": list(scene.box_size)},
        ],
        "authority": "physics is authoritative in WSL; this manifest is display-only and cannot alter physics",
    }
    with open(CASE_DIR / "display-manifest.json", "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    with open(CASE_DIR / "records.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    with open(CASE_DIR / "events.json", "w", encoding="utf-8", newline="\n") as handle:
        json.dump(events, handle, indent=2)
        handle.write("\n")
    print(json.dumps({"rows": len(records), "events": events}, sort_keys=True))


if __name__ == "__main__":
    main()
