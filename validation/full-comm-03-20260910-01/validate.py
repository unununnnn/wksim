import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / 'docs/plan/full-contracts/comm-03.json').read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == 'COMM-03')
    followup_row = next(row for row in followups["entries"] if row.get("id") == 'COMM-03')
    assert contract["issue"] == 130
    assert contract["source"]["line"] == 34
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [130]
    assert len(contract["atoms"]) == 6
    assert len({atom["id"] for atom in contract["atoms"]}) == 6
    assert sorted({atom["status"] for atom in contract["atoms"]}) == ['blocked', 'partial']
    assert len(contract["errors"]) == len(set(contract["errors"]))
    text0 = (ROOT / 'Simulator/wksim_runtime/telemetry.py').read_text(encoding="utf-8")
    assert 'class Observer' in text0, 'class Observer'
    assert 'def decode_datagram' in text0, 'def decode_datagram'
    assert 'def forward' in text0, 'def forward'
    text1 = (ROOT / 'Simulator/wksim_runtime/parameter_protocol.py').read_text(encoding="utf-8")
    assert 'class ParameterContext' in text1, 'class ParameterContext'
    assert 'PARAM_VALUE has no request ID' in text1, 'PARAM_VALUE has no request ID'
    text2 = (ROOT / 'Simulator/wksim_runtime/telemetry-dialects.json').read_text(encoding="utf-8")
    assert 'build_manifest_sha256' in text2, 'build_manifest_sha256'
    assert 'dialects' in text2, 'dialects'
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    assert '| 2 | Mavlink_Full |' in scope
    assert contract["preserved"]["issue_42"].startswith("verified")
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 25, "skipped": 0,
                      "atoms": 6, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
