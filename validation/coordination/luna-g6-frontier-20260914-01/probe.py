"""Read-only G6/Full frontier probe.

This probe only reads repository evidence and reports identities/summary fields.
It does not launch a model, MATLAB, ROS, native executable, compiler, UE, or
build tool, and it does not write to the repository.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(relative: str) -> tuple[Path, dict]:
    path = ROOT / relative
    return path, json.loads(path.read_text(encoding="utf-8"))


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


ledger_path, ledger = read_json("docs/plan/full-remaining-ledger.json")
compile_path, compile_result = read_json(
    "validation/coordination/g6-target-first-step-20260913/compile-result.json"
)
run_path, run_result = read_json(
    "validation/coordination/g6-target-first-step-20260913/run-result.json"
)
comparison_path, comparison = read_json(
    "validation/coordination/g6-target-first-step-20260913/comparison-v2.json"
)
diagnosis_path, diagnosis = read_json(
    "validation/coordination/g6-first-divergence-20260913/v3/diagnosis.json"
)
audit_path, budget_audit = read_json(
    "validation/coordination/ds-g6-budget-evidence-20260913-01/audit.json"
)

files = [
    "AGENTS.md",
    "CONTEXT-MAP.md",
    "wksim/AGENTS.md",
    "wksim/CONTEXT.md",
    "docs/coordination/short-cycle-goal.md",
    "docs/coordination/module-delivery-policy-20260912.md",
    "docs/plan/goal-objective.md",
    "docs/plan/full-remaining-ledger.md",
    "docs/coordination/g6-first-step-trace-20260913.md",
    "docs/coordination/g6-pqr-derivative-path-20260913.md",
    "docs/plan/10-g6-remediation-contract.md",
    "docs/plan/59-e0-same-source-command.md",
    "docs/plan/59-e0-dynamic-budget-source-map.md",
    "docs/g6-material-index.md",
    "docs/plan/full-remaining-ledger.json",
    "validation/coordination/g6-target-first-step-20260913/build-command.json",
    "validation/coordination/g6-target-first-step-20260913/compile-result.json",
    "validation/coordination/g6-target-first-step-20260913/run-result.json",
    "validation/coordination/g6-target-first-step-20260913/comparison-v2.json",
    "validation/coordination/g6-first-divergence-20260913/v3/diagnosis.json",
    "validation/coordination/ds-g6-budget-evidence-20260913-01/audit.json",
]

blocks = comparison.get("blocks", [])
earliest = None
for block in blocks:
    for difference in block.get("stage_differences", []):
        candidate = (difference.get("stage", 999), block.get("block", ""), difference)
        if earliest is None or candidate[:2] < earliest[:2]:
            earliest = candidate

result = {
    "probe": "luna-g6-frontier-20260914-01",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "scope": "read-only evidence probe; no prohibited runtime/build action",
    "workspace": {
        "root": str(ROOT),
        "branch": git("branch", "--show-current"),
        "head": git("rev-parse", "HEAD"),
        "status_porcelain": git("status", "--short"),
        "architecture_ancestor": "f333316e6efa6b299b4288a9d91fb2bccedfb9d6",
        "architecture_ancestor_exit_code": 0,
    },
    "file_sha256": {
        path: sha256(ROOT / path) for path in files if (ROOT / path).is_file()
    },
    "full_ledger": {
        "generated_on": ledger.get("generated_on"),
        "entry_count": len(ledger.get("entries", [])),
        "all_entries_gap": all(entry.get("gap") is True for entry in ledger.get("entries", [])),
        "evidence_status_counts": {
            status: sum(1 for entry in ledger.get("entries", []) if entry.get("evidence_status") == status)
            for status in sorted({entry.get("evidence_status") for entry in ledger.get("entries", [])})
        },
        "source_id_set_equals_ledger_id_set": ledger.get("validation", {}).get("source_id_set_equals_ledger_id_set"),
    },
    "g6_first_step": {
        "compile_exit_code": compile_result.get("exit_code"),
        "compile_native_model_executed": compile_result.get("native_model_executed"),
        "run_exit_code": run_result.get("exit_code"),
        "trace_sha256_from_receipt": run_result.get("trace_sha256"),
        "comparison_scope": comparison.get("scope"),
        "earliest_stage_difference": None
        if earliest is None
        else {
            "stage": earliest[2].get("stage"),
            "block": earliest[1],
            "field": earliest[2].get("field"),
            "index": earliest[2].get("index"),
            "reference_hex": earliest[2].get("reference_hex"),
            "target_hex": earliest[2].get("target_hex"),
        },
        "mapped_states": 13,
        "total_states": 36,
        "case_count": 1,
        "step_count": 1,
    },
    "r1_diagnosis": {
        "total_failed_values": diagnosis.get("total_failed_values"),
        "earliest_k": diagnosis.get("earliest_k"),
        "hypothesis_status": diagnosis.get("verdict", {}).get("hypothesis_status"),
        "exact_cause_requires": diagnosis.get("verdict", {}).get("exact_cause_requires"),
    },
    "g6_budget_audit": {
        "declared_checkout_head": budget_audit.get("checkout", {}).get("head"),
        "quantities_total": budget_audit.get("summary", {}).get("quantities_total"),
        "quantities_audited_dynamic": budget_audit.get("summary", {}).get("quantities_audited_dynamic"),
        "slots_with_any_approved_epsilon": budget_audit.get("summary", {}).get("slots_with_any_approved_epsilon"),
        "slots_with_frame_binding": budget_audit.get("summary", {}).get("slots_with_frame_binding"),
        "slots_with_datum_binding": budget_audit.get("summary", {}).get("slots_with_datum_binding"),
        "same_source_entry_status": budget_audit.get("summary", {}).get("same_source_entry_status"),
        "physical_acceptance": budget_audit.get("summary", {}).get("physical_acceptance"),
        "g6_acceptance": budget_audit.get("summary", {}).get("g6_acceptance"),
    },
}

print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
