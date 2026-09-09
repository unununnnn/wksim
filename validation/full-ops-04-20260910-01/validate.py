import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / "docs/plan/full-contracts/ops-04.json").read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == "OPS-04")
    followup_row = next(row for row in followups["entries"] if row.get("id") == "OPS-04")
    assert contract["issue"] == 155
    assert contract["source"]["line"] == 72
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [155]
    assert len(contract["atoms"]) == 8
    assert len({atom["id"] for atom in contract["atoms"]}) == 8
    assert {atom["status"] for atom in contract["atoms"]} == {"partial", "blocked"}
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    config = (ROOT / "Simulator/wksim_runtime/config.py").read_text(encoding="utf-8")
    cli = (ROOT / "tools/run-wksim.sh").read_text(encoding="utf-8")
    preflight = (ROOT / "Simulator/wksim_console/preflight_entry.py").read_text(encoding="utf-8")
    server = (ROOT / "Simulator/wksim_console/server.py").read_text(encoding="utf-8")
    workspace = (ROOT / "Simulator/wksim_console/workspace.py").read_text(encoding="utf-8")
    report = (ROOT / "docs/2026-09-08-console-ui-closure-report.md").read_text(encoding="utf-8")
    assert "| CLI/NoUI/GUI一致性 |" in scope and "16" in scope
    assert "def validate_config" in config and "def checked_config" in workspace
    assert 'exec python3 -m Simulator.wksim_runtime.runtime' in cli
    assert "preflight" in preflight and "/api/start" in server
    assert "真实浏览器" in report and "Full" in report
    assert len(contract["surfaces"]) == 3
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 22, "skipped": 0,
                      "atoms": 8, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
