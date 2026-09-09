import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / 'docs/plan/full-contracts/model-16-exp1.json').read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == 'MODEL-16')
    followup_row = next(row for row in followups["entries"] if row.get("id") == 'MODEL-16')
    assert contract["issue"] == 150
    assert contract["source"]["line"] == 61
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [150, 151]
    assert len(contract["atoms"]) == 5
    assert len({atom["id"] for atom in contract["atoms"]}) == 5
    assert sorted({atom["status"] for atom in contract["atoms"]}) == ['blocked', 'partial']
    assert len(contract["errors"]) == len(set(contract["errors"]))
    text0 = (ROOT / 'tools/probe_model_reference_readiness.py').read_text(encoding="utf-8")
    assert 'Exp1_MinModelTemp.slx' in text0, 'Exp1_MinModelTemp.slx'
    assert 'c232e2e9f71a195ba77af628370a0b0f977104870673c91955e51c528a9a3392' in text0, 'c232e2e9f71a195ba77af628370a0b0f977104870673c91955e51c528a9a3392'
    text1 = (ROOT / 'Simulator/wksim_core/README.md').read_text(encoding="utf-8")
    assert 'MulticopterModel.zip' in text1, 'MulticopterModel.zip'
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    assert '| Exp1_MinModelTemp、Exp2_MaxModelTemp |' in scope
    assert contract["preserved"]["material"].startswith("pinned local-only")
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 19, "skipped": 0,
                      "atoms": 5, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
