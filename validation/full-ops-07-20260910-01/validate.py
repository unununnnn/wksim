import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / "docs/plan/full-contracts/ops-07.json").read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == "OPS-07")
    followup_row = next(row for row in followups["entries"] if row.get("id") == "OPS-07")
    assert contract["issue"] == 158
    assert contract["source"]["line"] == 75
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [158]
    assert len(contract["atoms"]) == 6
    assert len({atom["id"] for atom in contract["atoms"]}) == 6
    assert {atom["status"] for atom in contract["atoms"]} == {"partial", "blocked"}
    assert len(contract["errors"]) == len(set(contract["errors"]))
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    decision = (ROOT / "docs/2026-09-07_environment-contract-accepted.md").read_text(encoding="utf-8")
    proposal = (ROOT / "docs/plan/remaining-gates-proposal.md").read_text(encoding="utf-8")
    clock = (ROOT / "Simulator/wksim_runtime/scene_clock.py").read_text(encoding="utf-8")
    p450 = (ROOT / "Simulator/ue55/p450-visual-manifest.json").read_text(encoding="utf-8")
    hex_config = (ROOT / "Simulator/wksim_runtime/hex-flight-v1.json").read_text(encoding="utf-8")
    assert "| 环境反馈 |" in scope
    assert "已批准的环境与视觉反馈合同" in decision and "采用此环境与视觉合同" in decision
    assert "ENU" in decision and "不热改配置" in decision and "显式恢复" in decision
    assert "平面/坡面及一个静态盒障碍" in proposal
    assert "class SceneClock" in clock and "recoverable" in clock
    assert "physics_scope" in p450 and "prometheus_p450_visual_v1" in p450
    assert "model_identity" in hex_config and "hex_x" in hex_config
    assert contract["decision"]["accepted_file"] == "docs/2026-09-07_environment-contract-accepted.md"
    assert contract["preserved"]["parent_29"].startswith("open")
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 24, "skipped": 0,
                      "atoms": 6, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
