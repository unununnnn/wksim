import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / 'docs/plan/full-contracts/sim-04.json').read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == 'SIM-04')
    followup_row = next(row for row in followups["entries"] if row.get("id") == 'SIM-04')
    assert contract["issue"] == 124
    assert contract["source"]["line"] == 16
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [124]
    assert len(contract["atoms"]) == 6
    assert len({atom["id"] for atom in contract["atoms"]}) == 6
    assert sorted({atom["status"] for atom in contract["atoms"]}) == ['blocked', 'partial']
    assert len(contract["errors"]) == len(set(contract["errors"]))
    text0 = (ROOT / 'Simulator/wksim_core/README.md').read_text(encoding="utf-8")
    assert 'MulticopterModel.zip' in text0, 'MulticopterModel.zip'
    assert 'MATLAB' in text0, 'MATLAB'
    text1 = (ROOT / 'tools/probe_simulink_sampling.py').read_text(encoding="utf-8")
    assert 'def ' in text1, 'def '
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    assert '| 3 | Simulink&DLL_SIL |' in scope
    assert (ROOT / 'tools/probe_generated_model.py').is_file()
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 20, "skipped": 0,
                      "atoms": 6, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
