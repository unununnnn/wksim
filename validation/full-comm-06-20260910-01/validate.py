import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / 'docs/plan/full-contracts/comm-06.json').read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == 'COMM-06')
    followup_row = next(row for row in followups["entries"] if row.get("id") == 'COMM-06')
    assert contract["issue"] == 133
    assert contract["source"]["line"] == 37
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [133]
    assert len(contract["atoms"]) == 5
    assert len({atom["id"] for atom in contract["atoms"]}) == 5
    assert sorted({atom["status"] for atom in contract["atoms"]}) == ['blocked', 'partial']
    assert len(contract["errors"]) == len(set(contract["errors"]))
    text0 = (ROOT / 'Simulator/wksim_core/gnss_event.py').read_text(encoding="utf-8")
    assert 'class GnssEventController' in text0, 'class GnssEventController'
    assert 'signal_loss' in text0, 'signal_loss'
    assert 'def reset' in text0, 'def reset'
    text1 = (ROOT / 'docs/2026-09-09-gnss-event-report.md').read_text(encoding="utf-8")
    assert 'GNSS 事件离线包' in text1, 'GNSS 事件离线包'
    assert '没有通用故障框架' in text1, '没有通用故障框架'
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    assert '| 5 | Mavlink_NoGPS |' in scope
    assert contract["preserved"]["issue_45"].startswith("open")
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 21, "skipped": 0,
                      "atoms": 5, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
