import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / "docs/plan/full-contracts/ops-09.json").read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == "OPS-09")
    followup_row = next(row for row in followups["entries"] if row.get("id") == "OPS-09")
    assert contract["issue"] == 160
    assert contract["source"]["line"] == 77
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [160]
    assert len(contract["atoms"]) == 6
    assert len({atom["id"] for atom in contract["atoms"]}) == 6
    assert {atom["status"] for atom in contract["atoms"]} == {"partial", "blocked"}
    assert len(contract["errors"]) == len(set(contract["errors"]))
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    report = (ROOT / "docs/2026-09-09-gnss-event-report.md").read_text(encoding="utf-8")
    gnss = (ROOT / "Simulator/wksim_core/gnss_event.py").read_text(encoding="utf-8")
    clock = (ROOT / "Simulator/wksim_runtime/scene_clock.py").read_text(encoding="utf-8")
    pid_cfg = (ROOT / "Simulator/wksim_runtime/pid-flight-v1.json").read_text(encoding="utf-8")
    tests = (ROOT / "validation/test_gnss_event.py").read_text(encoding="utf-8")
    core_sources = "".join(p.read_text(encoding="utf-8", errors="ignore")
                           for p in (ROOT / "Simulator/wksim_core").glob("*.py"))
    assert "| 故障 |" in scope
    assert "GNSS 事件离线包" in report and "没有通用故障框架" in report
    assert "class GnssEventController" in gnss and "signal_loss" in gnss and "def reset" in gnss
    assert "recoverable" in clock
    assert "effective_actuator_command_multiplier" in pid_cfg
    assert "GnssEventController" in tests
    assert not re.search(r"\bwind\b|\bgust\b", core_sources, re.IGNORECASE)
    assert contract["preserved"]["issue_44"].startswith("open")
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 27, "skipped": 0,
                      "atoms": 6, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
