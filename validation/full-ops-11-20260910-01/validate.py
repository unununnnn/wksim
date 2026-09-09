import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / "docs/plan/full-contracts/ops-11.json").read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == "OPS-11")
    followup_row = next(row for row in followups["entries"] if row.get("id") == "OPS-11")
    assert contract["issue"] == 162
    assert contract["source"]["line"] == 79
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [162]
    assert len(contract["atoms"]) == 6
    assert len({atom["id"] for atom in contract["atoms"]}) == 6
    assert {atom["status"] for atom in contract["atoms"]} == {"partial", "blocked"}
    assert len(contract["errors"]) == len(set(contract["errors"]))
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    replay_doc = (ROOT / "docs/wksim-offline-replay.md").read_text(encoding="utf-8")
    integrity = (ROOT / "docs/2026-09-08-replay-integrity-report.md").read_text(encoding="utf-8")
    replay = (ROOT / "Simulator/wksim_runtime/replay.py").read_text(encoding="utf-8")
    tests = (ROOT / "validation/test_wksim_replay.py").read_text(encoding="utf-8")
    result = json.loads((ROOT / "validation/offline-replay-20260905/result.json").read_text(encoding="utf-8"))
    assert "| 日志与复现 |" in scope
    assert "64MiB" in replay_doc and "确定性重新仿真" in replay_doc
    assert "identity_mismatch" in integrity and "nonfinite" in integrity
    assert "def load_evidence" in replay and "def source_time" in replay
    assert len(tests) > 0
    assert isinstance(result, dict) and result
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 25, "skipped": 0,
                      "atoms": 6, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
