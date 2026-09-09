import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / "docs/plan/full-contracts/ops-02.json").read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == "OPS-02")
    followup_row = next(row for row in followups["entries"] if row.get("id") == "OPS-02")
    assert contract["issue"] == 153
    assert contract["source"]["line"] == 70
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [153]
    assert len(contract["atoms"]) == 7
    assert len({atom["id"] for atom in contract["atoms"]}) == 7
    assert {atom["status"] for atom in contract["atoms"]} == {"partial", "blocked"}
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    assert "| 性能计算 |" in scope
    model = (ROOT / "Simulator/wksim_core/model.py").read_text(encoding="utf-8")
    params = (ROOT / "Simulator/wksim_core/model_parameters.py").read_text(encoding="utf-8")
    pid = (ROOT / "Simulator/wksim_runtime/pid_task.py").read_text(encoding="utf-8")
    assert "120" in model and "fixed 1 ms integration" in model
    assert "ModelParam_motorCr" in params and "ModelParam_rotorCt" in params
    assert "native_hover_entry" in pid and "hover_median" in pid
    assert "current_a" in contract["result_fields"] and "power_w" in contract["result_fields"]
    assert contract["missing_value_rule"].endswith("silently zero")
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 19, "skipped": 0,
                      "atoms": 7, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
