import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / "docs/plan/full-contracts/ops-08.json").read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == "OPS-08")
    followup_row = next(row for row in followups["entries"] if row.get("id") == "OPS-08")
    assert contract["issue"] == 159
    assert contract["source"]["line"] == 76
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [159]
    assert len(contract["atoms"]) == 6
    assert len({atom["id"] for atom in contract["atoms"]}) == 6
    assert {atom["status"] for atom in contract["atoms"]} == {"partial", "blocked"}
    assert len(contract["errors"]) == len(set(contract["errors"]))
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    rgb_doc = (ROOT / "docs/rgb-capture-component.md").read_text(encoding="utf-8")
    rgb_fixture = (ROOT / "docs/rgb-geometry-fixture.md").read_text(encoding="utf-8")
    aruco_report = (ROOT / "docs/2026-09-09-aruco-consumer-report.md").read_text(encoding="utf-8")
    rgb = (ROOT / "Simulator/ue55/rgb.py").read_text(encoding="utf-8")
    depth = (ROOT / "Simulator/ue55/depth.py").read_text(encoding="utf-8")
    aruco = (ROOT / "Simulator/wksim_perception/aruco.py").read_text(encoding="utf-8")
    core_sources = "".join(p.read_text(encoding="utf-8", errors="ignore")
                           for p in (ROOT / "Simulator/wksim_core").glob("*.py"))
    assert "| 传感器 |" in scope
    for term in ("noise", "bias", "calibrat"):
        assert term not in core_sources.lower(), term
    assert len(rgb_fixture) > 0
    assert "ArUco" in aruco_report and "不是 #40 的真实传感器到双栈飞行闭环验收" in aruco_report
    assert "class Reader" in rgb and "set_epoch" in rgb
    assert "max_depth_meters" in depth and "ENU" in depth
    assert "class Consumer" in aruco and "DICT_" in aruco and "max_age_steps" in aruco
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 28, "skipped": 0,
                      "atoms": 6, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
