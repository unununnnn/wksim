import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / "docs/plan/full-contracts/ops-01.json").read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == "OPS-01")
    followup_row = next(row for row in followups["entries"] if row.get("id") == "OPS-01")
    assert contract["issue"] == 152
    assert contract["source"]["line"] == 69
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [152]
    assert len(contract["atoms"]) == 6
    assert len({atom["id"] for atom in contract["atoms"]}) == 6
    assert {atom["status"] for atom in contract["atoms"]} == {"partial", "blocked"}

    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    assert "| 模型数据库/组件库 |" in scope
    source = (ROOT / "Simulator/wksim_core/model_parameters.py").read_text(encoding="utf-8")
    tool = (ROOT / "tools/quad_model_parameters.py").read_text(encoding="utf-8")
    assert "def make_config" in source and "def validate" in source
    assert "def save_config" in source and "def load_config" in source
    assert 'sub.add_parser("export", aliases=["import"]' in tool
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 17, "skipped": 0,
                      "atoms": 6, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
