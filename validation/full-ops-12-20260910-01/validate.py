import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / "docs/plan/full-contracts/ops-12.json").read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == "OPS-12")
    followup_row = next(row for row in followups["entries"] if row.get("id") == "OPS-12")
    assert contract["issue"] == 163
    assert contract["source"]["line"] == 80
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [163]
    assert len(contract["atoms"]) == 6
    assert len({atom["id"] for atom in contract["atoms"]}) == 6
    assert {atom["status"] for atom in contract["atoms"]} == {"partial", "blocked"}
    assert len(contract["errors"]) == len(set(contract["errors"]))
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    isolation = (ROOT / "docs/project-isolation.md").read_text(encoding="utf-8")
    provenance = (ROOT / "docs/prometheus-p450-asset-provenance.md").read_text(encoding="utf-8")
    readme = (ROOT / "Simulator/wksim_core/README.md").read_text(encoding="utf-8")
    gitmodules_ref = (ROOT / "docs/Prometheus.gitmodules.reference").read_text(encoding="utf-8")
    assert "| 资源自主交付 |" in scope
    assert "d6f12ad1c4f70ad3230afd7d86e971421e02fef4" in isolation
    assert "1511f27194f1dcc3728270883047bdf022b3fd53" in isolation
    assert "5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce" in provenance
    assert "MulticopterModel.zip" in readme and "完整自举" in readme
    assert len(gitmodules_ref) > 0
    assert contract["preserved"]["vendor_zip"].startswith("local-only")
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 25, "skipped": 0,
                      "atoms": 6, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
