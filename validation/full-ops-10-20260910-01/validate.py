import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / "docs/plan/full-contracts/ops-10.json").read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == "OPS-10")
    followup_row = next(row for row in followups["entries"] if row.get("id") == "OPS-10")
    assert contract["issue"] == 161
    assert contract["source"]["line"] == 78
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [161]
    assert len(contract["atoms"]) == 6
    assert len({atom["id"] for atom in contract["atoms"]}) == 6
    assert {atom["status"] for atom in contract["atoms"]} == {"partial", "blocked"}
    assert len(contract["errors"]) == len(set(contract["errors"]))
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    rc_doc = (ROOT / "docs/plan/38-rc-integration.md").read_text(encoding="utf-8")
    command = (ROOT / "ros2/src/prometheus_control/prometheus_control/command.py").read_text(encoding="utf-8")
    rc_input = (ROOT / "Simulator/wksim_control/rc_input.py").read_text(encoding="utf-8")
    mission = (ROOT / "Simulator/wksim_runtime/mission_plan.py").read_text(encoding="utf-8")
    velocity = (ROOT / "Simulator/wksim_runtime/velocity_evidence.py").read_text(encoding="utf-8")
    ude_cfg = (ROOT / "Simulator/wksim_runtime/ude-flight-v1.json").read_text(encoding="utf-8")
    ne_cfg = (ROOT / "Simulator/wksim_runtime/ne-flight-v1.json").read_text(encoding="utf-8")
    for module in ("position_pid.py", "position_ude.py", "position_ne.py"):
        assert (ROOT / "Simulator/wksim_control" / module).is_file(), module
    assert "| 控制/任务/算法 |" in scope
    assert "not RC product acceptance" in rc_doc
    assert "class CommandProcessor" in command and "RC_POS_CONTROL" in command
    assert "class RCError" in rc_input
    assert len(mission) > 0 and "def verify_velocity_windows" in velocity
    assert "ude" in ude_cfg and '"ne"' in ne_cfg
    assert contract["preserved"]["issue_35"].startswith("open")
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 28, "skipped": 0,
                      "atoms": 6, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
