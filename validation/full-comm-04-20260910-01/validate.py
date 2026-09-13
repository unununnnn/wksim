import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / 'docs/plan/full-contracts/comm-04.json').read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == 'COMM-04')
    followup_row = next(row for row in followups["entries"] if row.get("id") == 'COMM-04')
    assert contract["issue"] == 131
    assert contract["source"]["line"] == 35
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [131]
    assert len(contract["atoms"]) == 4
    assert len({atom["id"] for atom in contract["atoms"]}) == 4
    assert sorted({atom["status"] for atom in contract["atoms"]}) == ['blocked', 'partial']
    assert len(contract["errors"]) == len(set(contract["errors"]))
    text0 = (ROOT / 'Simulator/wksim_runtime/telemetry.py').read_text(encoding="utf-8")
    assert 'class Observer' in text0, 'class Observer'
    assert 'def decode_datagram' in text0, 'def decode_datagram'
    text1 = (ROOT / 'Simulator/wksim_runtime/telemetry-dialects.json').read_text(encoding="utf-8")
    assert 'build_manifest_sha256' in text1, 'build_manifest_sha256'
    assert 'dialects' in text1, 'dialects'
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    assert '| 3 | Mavlink_Simple |' in scope
    assert contract["preserved"]["depends_on_full"].startswith("reduction")
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 20, "skipped": 0,
                      "atoms": 4, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
