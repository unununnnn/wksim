import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / "docs/plan/full-contracts/ops-13.json").read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == "OPS-13")
    followup_row = next(row for row in followups["entries"] if row.get("id") == "OPS-13")
    assert contract["issue"] == 164
    assert contract["source"]["line"] == 81
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [164]
    assert len(contract["atoms"]) == 6
    assert len({atom["id"] for atom in contract["atoms"]}) == 6
    assert {atom["status"] for atom in contract["atoms"]} == {"partial", "blocked"}
    assert len(contract["errors"]) == len(set(contract["errors"]))
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    rate = (ROOT / "Simulator/wksim_runtime/joint_rate.py").read_text(encoding="utf-8")
    clock = (ROOT / "Simulator/wksim_runtime/scene_clock.py").read_text(encoding="utf-8")
    report = (ROOT / "validation/rate-syscall-scheduler-plan-20260909/report.md").read_text(encoding="utf-8")
    collector_doc = (ROOT / "validation/rate-syscall-scheduler-plan-20260909/COLLECTOR.md").read_text(encoding="utf-8")
    collector = (ROOT / "validation/rate-syscall-scheduler-plan-20260909/collect_tracefs.py").read_text(encoding="utf-8")
    assert "| 性能与规模 |" in scope
    assert "class RateUnmet" in rate and "requested_rate must be 0.5 or 1" in rate
    assert "MACRO_TICKS" in clock and "recoverable" in clock
    assert "tracefs" in report and "perf_event_paranoid" in report
    assert len(collector_doc) > 0 and len(collector) > 0
    assert contract["preserved"]["rate_unmet"].startswith("#20/#33")
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 25, "skipped": 0,
                      "atoms": 6, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
