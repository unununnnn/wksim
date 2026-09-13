import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads((ROOT / "docs/plan/full-contracts/ops-06.json").read_text(encoding="utf-8"))
    ledger = json.loads((ROOT / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    followups = json.loads((ROOT / "docs/plan/full-followup-tickets.json").read_text(encoding="utf-8"))
    ledger_row = next(row for row in ledger["entries"] if row.get("id") == "OPS-06")
    followup_row = next(row for row in followups["entries"] if row.get("id") == "OPS-06")
    assert contract["issue"] == 157
    assert contract["source"]["line"] == 74
    assert contract["full_complete"] is False
    assert ledger_row["gap"] is True
    assert followup_row["followup_ids"] == [157]
    assert len(contract["atoms"]) == 6
    assert len({atom["id"] for atom in contract["atoms"]}) == 6
    assert {atom["status"] for atom in contract["atoms"]} == {"partial", "blocked"}
    scope = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
    p450 = (ROOT / "Simulator/ue55/p450-visual-manifest.json").read_text(encoding="utf-8")
    readme = (ROOT / "Simulator/ue55/README.md").read_text(encoding="utf-8")
    hex_config = (ROOT / "Simulator/wksim_runtime/hex-flight-v1.json").read_text(encoding="utf-8")
    params = (ROOT / "Simulator/wksim_core/model_parameters.py").read_text(encoding="utf-8")
    assert "| 载具与场景资产 |" in scope
    assert "physics_scope" in p450 and "prometheus_p450_visual_v1" in p450
    assert "接入验证模型" in readme and "不是完成的 Prometheus 机体资产" in readme
    assert "model_identity" in hex_config and "hex_x" in hex_config
    assert "motor_count" in params and "source_rotation_sign" in params
    assert contract["class_id_rule"] == "ClassID=-1 is not an asset binding"
    hashes = json.loads((CASE / "hashes.json").read_text(encoding="utf-8"))["inputs"]
    for relative, expected in hashes.items():
        assert sha256(ROOT / relative) == expected, relative
    print(json.dumps({"status": "pass", "assertions": 22, "skipped": 0,
                      "atoms": 6, "full_complete": False}, sort_keys=True))


if __name__ == "__main__":
    main()
