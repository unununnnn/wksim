"""Run the frozen slope/box contact fixture once (#80 / 29-static-contact).

Executes the #79-delivered query seam against cases.json and writes raw
results.jsonl. No UE, FC, model, ROS or hardware process is started.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from Simulator.wksim_core.static_contact import ContactError, load_scene  # noqa: E402

CASE_DIR = Path(__file__).resolve().parent
EPOCH = "a1b2c3d4e5f60718293a4b5c6d7e8f90"


def main():
    scene = load_scene(ROOT / "Simulator/wksim_runtime/static-scene-v1.json")
    cases = json.loads((CASE_DIR / "cases.json").read_text(encoding="utf-8"))
    results = []
    envelopes = {}
    for case in cases:
        record = {"case": case["case"], "expect": case["expect"]}
        if "point" in case:
            try:
                out = scene.query(EPOCH, case["step"], "fixture_body", case["point"])
                record["actual"] = out["result"]
                if out["envelope"] is not None:
                    record["envelope"] = out["envelope"]
                    envelopes[case["case"]] = out["envelope"]
                    record["actual"] += ":" + out["envelope"]["geometry_id"]
            except ContactError as exc:
                record["actual"] = "error:" + exc.reason
        else:
            source = dict(envelopes[case["from_case"]])
            if case.get("tamper_hash"):
                source["scene_hash"] = "0" * 64
            try:
                fresh = scene.require_fresh(source, case["current_step"], case["run_epoch"])
                record["actual"] = "fresh:" + str(fresh).lower()
            except ContactError as exc:
                record["actual"] = "error:" + exc.reason
        results.append(record)
    out_path = CASE_DIR / "results.jsonl"
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        for record in results:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    print(json.dumps({"cases": len(results), "output": str(out_path)}))


if __name__ == "__main__":
    main()
