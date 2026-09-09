import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / 'docs/plan/full-contracts/sim-02.json').read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == 'SIM-02')
    followup_row = next(row for row in followups["entries"] if row.get("id") == 'SIM-02')
    assert contract["issue"] == 122
    assert contract["source"]["line"] == 14
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [122]
    assert len(contract["atoms"]) == 5
    assert len({atom["id"] for atom in contract["atoms"]}) == 5
    assert sorted({atom["status"] for atom in contract["atoms"]}) == ['blocked', 'partial']
    assert len(contract["errors"]) == len(set(contract["errors"]))
    text0 = (ROOT / 'tools/validate_sitl_physics.py').read_text(encoding="utf-8")
    assert 'px4' in text0, 'px4'
    text1 = (ROOT / 'Simulator/wksim_core/px4_mavlink.py').read_text(encoding="utf-8")
    assert 'HIL' in text1, 'HIL'
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    assert '| 1 | PX4_SITL |' in scope

    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 18, "skipped": 0,
                      "atoms": 5, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
