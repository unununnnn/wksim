import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / 'docs/plan/full-contracts/sim-03.json').read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == 'SIM-03')
    followup_row = next(row for row in followups["entries"] if row.get("id") == 'SIM-03')
    assert contract["issue"] == 123
    assert contract["source"]["line"] == 15
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [123]
    assert len(contract["atoms"]) == 4
    assert len({atom["id"] for atom in contract["atoms"]}) == 4
    assert sorted({atom["status"] for atom in contract["atoms"]}) == ['blocked', 'partial']
    assert len(contract["errors"]) == len(set(contract["errors"]))
    text0 = (ROOT / 'docs/project-isolation.md').read_text(encoding="utf-8")
    assert 'd6f12ad1c4f70ad3230afd7d86e971421e02fef4' in text0, 'd6f12ad1c4f70ad3230afd7d86e971421e02fef4'
    text1 = (ROOT / 'Simulator/wksim_core/px4_mavlink.py').read_text(encoding="utf-8")
    assert 'HIL' in text1, 'HIL'
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    assert '| 2 | PX4_SITL_RFLY |' in scope
    assert contract["preserved"]["standard_px4"].startswith("fixed PX4 d6f12ad1")
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 18, "skipped": 0,
                      "atoms": 4, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
