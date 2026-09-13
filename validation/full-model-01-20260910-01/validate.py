import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / 'docs/plan/full-contracts/model-01.json').read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == 'MODEL-01')
    followup_row = next(row for row in followups["entries"] if row.get("id") == 'MODEL-01')
    assert contract["issue"] == 135
    assert contract["source"]["line"] == 46
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [135, 59]
    assert len(contract["atoms"]) == 6
    assert len({atom["id"] for atom in contract["atoms"]}) == 6
    assert sorted({atom["status"] for atom in contract["atoms"]}) == ['blocked', 'partial']
    assert len(contract["errors"]) == len(set(contract["errors"]))
    text0 = (ROOT / 'Simulator/wksim_core/model_parameters.py').read_text(encoding="utf-8")
    assert 'COMPONENTS' in text0, 'COMPONENTS'
    assert 'fixed Quad X' in text0, 'fixed Quad X'
    assert 'def make_config' in text0, 'def make_config'
    assert 'def validate' in text0, 'def validate'
    assert 'def load_config' in text0, 'def load_config'
    text1 = (ROOT / 'Simulator/wksim_runtime/parameter_protocol.py').read_text(encoding="utf-8")
    assert 'class ParameterContext' in text1, 'class ParameterContext'
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    assert '| 四旋翼 |' in scope
    assert contract["preserved"]["r1"].startswith("numerical_failed")
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 24, "skipped": 0,
                      "atoms": 6, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
