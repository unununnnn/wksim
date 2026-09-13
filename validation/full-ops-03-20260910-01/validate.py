import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / "docs/plan/full-contracts/ops-03.json").read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == "OPS-03")
    followup_row = next(row for row in followups["entries"] if row.get("id") == "OPS-03")
    assert contract["issue"] == 154
    assert contract["source"]["line"] == 71
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [154]
    assert len(contract["atoms"]) == 5
    assert len({atom["id"] for atom in contract["atoms"]}) == 5
    assert {atom["status"] for atom in contract["atoms"]} == {"partial", "blocked"}
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    abi = (ROOT / "docs/plan/9-abi-environment-evidence.md").read_text(encoding="utf-8")
    params = (ROOT / "Simulator/wksim_core/model_parameters.py").read_text(encoding="utf-8")
    assert "| XML/模型元数据 |" in scope
    assert "ModelInfo" in abi and "HoverInfo" in abi and "FrameInfo" in abi
    assert "ClassID=-1" in abi
    assert "def make_config" in params and "fixed_parameters" in params
    assert contract["record_contract"]["class_id_rule"] == "ClassID=-1 is not an asset binding"
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 18, "skipped": 0,
                      "atoms": 5, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
