import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / "docs/plan/full-contracts/ops-05.json").read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == "OPS-05")
    followup_row = next(row for row in followups["entries"] if row.get("id") == "OPS-05")
    assert contract["issue"] == 156
    assert contract["source"]["line"] == 73
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [156]
    assert len(contract["atoms"]) == 7
    assert len({atom["id"] for atom in contract["atoms"]}) == 7
    assert {atom["status"] for atom in contract["atoms"]} == {"partial", "blocked"}
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    isolation = (ROOT / "Simulator/wksim_runtime/isolation.py").read_text(encoding="utf-8")
    profile = (ROOT / "Simulator/wksim_runtime/independent_profile.py").read_text(encoding="utf-8")
    config = (ROOT / "Simulator/wksim_runtime/config.py").read_text(encoding="utf-8")
    cli = (ROOT / "tools/run-wksim.sh").read_text(encoding="utf-8")
    joint = (ROOT / "Simulator/wksim_core/joint.py").read_text(encoding="utf-8")
    assert "| 网络与远程 |" in scope
    assert "network_namespace" in isolation and "ports" in isolation and "check_isolation" in isolation
    assert "current admission code is not flight evidence" in profile
    assert "gcs_udp_forward" in config and "127.0.0.1" in config
    assert "unshare --net --ipc --mount" in cli
    assert "def __init__(self, stack, clock, workers, health, record)" in joint
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert " " not in expected and sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 20, "skipped": 0,
                      "atoms": 7, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
