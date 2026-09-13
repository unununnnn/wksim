import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / 'docs/plan/full-contracts/model-14.json').read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == 'MODEL-14')
    followup_row = next(row for row in followups["entries"] if row.get("id") == 'MODEL-14')
    assert contract["issue"] == 148
    assert contract["source"]["line"] == 59
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [148]
    assert len(contract["atoms"]) == 4
    assert len({atom["id"] for atom in contract["atoms"]}) == 4
    assert sorted({atom["status"] for atom in contract["atoms"]}) == ['blocked', 'partial']
    assert len(contract["errors"]) == len(set(contract["errors"]))
    text0 = (ROOT / 'Simulator/wksim_control/position_pid.py').read_text(encoding="utf-8")
    assert 'class ' in text0, 'class '
    text1 = (ROOT / 'Simulator/wksim_control/position_ude.py').read_text(encoding="utf-8")
    assert 'class ' in text1, 'class '
    text2 = (ROOT / 'Simulator/wksim_control/position_ne.py').read_text(encoding="utf-8")
    assert 'class ' in text2, 'class '
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    assert '| CopterSILVelCtrl |' in scope

    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 19, "skipped": 0,
                      "atoms": 4, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
