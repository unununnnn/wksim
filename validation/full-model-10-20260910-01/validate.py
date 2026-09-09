import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / 'docs/plan/full-contracts/model-10.json').read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == 'MODEL-10')
    followup_row = next(row for row in followups["entries"] if row.get("id") == 'MODEL-10')
    assert contract["issue"] == 144
    assert contract["source"]["line"] == 55
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [144]
    assert len(contract["atoms"]) == 4
    assert len({atom["id"] for atom in contract["atoms"]}) == 4
    assert sorted({atom["status"] for atom in contract["atoms"]}) == ['blocked', 'partial']
    assert len(contract["errors"]) == len(set(contract["errors"]))
    text0 = (ROOT / 'Simulator/wksim_core/model_parameters.py').read_text(encoding="utf-8")
    assert 'fixed Quad X' in text0, 'fixed Quad X'
    text1 = (ROOT / 'docs/plan/full-contracts/ops-07.md').read_text(encoding="utf-8")
    assert 'Environment feedback contract' in text1, 'Environment feedback contract'
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    assert '| CarNoCtrl |' in scope

    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 17, "skipped": 0,
                      "atoms": 4, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
