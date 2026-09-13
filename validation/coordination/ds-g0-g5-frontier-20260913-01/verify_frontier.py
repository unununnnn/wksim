"""Read-only G0-G5 frontier verifier (ds-g0-g5-frontier-20260913-01).

Every check in this file is read-only with respect to the repository: it opens
files, hashes bytes, parses JSON and re-runs the repository's own interval
analyzer by direct module import.  Its only writes are inside this deliverable
directory (``checks/``).  It never runs native, ROS, a flight controller, a
model, UE or MATLAB, and it never modifies an issue, the shared ledger or any
existing file.

Usage: python -B validation/coordination/ds-g0-g5-frontier-20260913-01/verify_frontier.py
"""

import gzip
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CHECKS = HERE / "checks"

ARCHITECTURE_ANCESTOR = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"
AUDIT_START_HEAD = "7e1e137879a779f2b051b384c044e6e936878d53"

# Retained originals this audit cites, grouped by gate.  Every entry is a path
# that this audit actually opened; a missing path is reported, never assumed.
PINNED = {
    "G0": [
        "docs/plan/goal-objective.md",
        "docs/plan/full-migration-spec.md",
        "docs/plan/full-scope-expansion.md",
        "docs/plan/full-remaining-ledger.json",
        "docs/plan/full-remaining-ledger.md",
        "docs/plan/lunar-issued.json",
        "docs/plan/published-issues.json",
        "Simulator/wksim_runtime/capability-index.json",
        "docs/coordination/acceptance-frontier.json",
        "docs/plan/full-acceptance-report.md",
    ],
    "G1": [
        "docs/2026-09-07_joint-product-entry-report.md",
        "docs/2026-09-06_joint-public-flight-report.md",
        "docs/2026-09-07_accelerated-integration-report.md",
        "docs/2026-09-13-final-combo-pv-pass.md",
    ],
    "G2": [
        "docs/plan/tickets/10-joint-step-reset.md",
        "docs/2026-09-07_joint-rate-contract-accepted.md",
        "docs/2026-09-09-final-combo-pv-plan.md",
        "docs/2026-09-09-mixed-flight-plan.md",
        "docs/coordination/short-cycle-goal.md",
        "docs/coordination/ds-architecture-mixed-migration-20260913.md",
        "validation/coordination/manager99-unprobed-20260913-01/decision.json",
        "validation/coordination/manager99-unprobed-20260913-01/rollback.json",
        "validation/coordination/manager99-unprobed-20260913-01/terminal-cleanup.json",
        "validation/33-final-combo-luna/pv-settle-1w6dru32/bundle-manifest.json",
    ],
    "G3": [
        "docs/plan/29-terrain-closure-report.md",
        "docs/plan/102-trajectory-scene-admission-contract.md",
        "docs/coordination/next-acceptance-goal.md",
    ],
    "G4": [
        "docs/plan/26-closure-readiness-manifest.json",
        "docs/plan/26-generation-contract.md",
        "docs/plan/26-current-wrapper-recheck-plan.md",
        "docs/2026-09-09-numerical-conformance-report.md",
        "validation/codegen-e0-lifecycle-01/audit.json",
        "docs/coordination/ds-full-frontier-20260912.json",
        "validation/coordination/three-deepseek-main-acceptance-20260913-01/main-verdict.json",
        "docs/2026-09-13-three-deepseek-delivery.md",
    ],
    "G5": [
        "docs/matlab-bridge.md",
        "docs/plan/tickets/31-matlab-bridge.md",
        "validation/matlab-bridge-20260907-run1/report.json",
        "validation/matlab-bridge-20260907-isolated/report.json",
        "validation/migration-resume-20260907/matlab-flight-audit-verified.json",
    ],
    "EXCLUDED": [
        "docs/plan/10-g6-remediation-contract.md",
        "docs/plan/59-e0-dynamic-budget-source-map.md",
        "validation/coordination/ds-perf-mixed-hook-audit-20260913-01/audit.json",
        "validation/coordination/architecture-candidate-sync-20260913-02/receipt.json",
    ],
}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args):
    done = subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True, text=True, check=False,
    )
    return done.returncode, done.stdout.strip(), done.stderr.strip()


def check_checkout():
    code, head, _ = git("rev-parse", "HEAD")
    branch_code, branch, _ = git("branch", "--show-current")
    ancestor_code, _, _ = git(
        "merge-base", "--is-ancestor", ARCHITECTURE_ANCESTOR, "HEAD")
    start_code, _, _ = git(
        "merge-base", "--is-ancestor", ARCHITECTURE_ANCESTOR, AUDIT_START_HEAD)
    dirty = git("status", "--porcelain=v1")[1]
    dirty_lines = [line for line in dirty.splitlines() if line]
    tracked_modified = [line for line in dirty_lines if not line.startswith("??")]
    untracked = [line for line in dirty_lines if line.startswith("??")]
    return {
        "cwd": str(REPO),
        "branch": branch if branch_code == 0 else None,
        "head_at_audit_start": AUDIT_START_HEAD,
        "head_observed_now": head if code == 0 else None,
        "architecture_ancestor": ARCHITECTURE_ANCESTOR,
        "ancestor_exit_at_audit_start_head": start_code,
        "ancestor_exit_at_current_head": ancestor_code,
        "worktree_dirty_entries": len(dirty_lines),
        "worktree_tracked_modified": len(tracked_modified),
        "worktree_untracked": len(untracked),
        "worktree_entries": dirty_lines,
        "note": "The worktree entries are other agents' concurrent work; this audit preserves them and writes only inside its own directory.",
    }


def check_pinned():
    result = {}
    for gate, paths in PINNED.items():
        entries = []
        for rel in paths:
            path = REPO / rel
            if path.is_file():
                entries.append({
                    "path": rel,
                    "exists": True,
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                })
            else:
                entries.append({"path": rel, "exists": False, "sha256": None})
        result[gate] = entries
    return result


def check_ledger():
    ledger = json.loads(
        (REPO / "docs/plan/full-remaining-ledger.json").read_text(encoding="utf-8"))
    rows = ledger["entries"]
    ids = [row.get("id") for row in rows]
    boundaries = ledger.get("preserved_boundaries", {})
    gates = boundaries.get("goals", [])
    hardware = boundaries.get("hardware")
    categories = {}
    for row in rows:
        key = row.get("category")
        categories[key] = categories.get(key, 0) + 1
    source_ids = set()
    for name, block in ledger.get("source_sets", {}).items():
        if isinstance(block, dict):
            for item in block.get("ids", []):
                source_ids.add(item)
        elif isinstance(block, list):
            for item in block:
                source_ids.add(item if isinstance(item, str) else item.get("id"))
    return {
        "ledger_path": "docs/plan/full-remaining-ledger.json",
        "schema_version": ledger.get("schema_version"),
        "generated_on": ledger.get("generated_on"),
        "row_count": len(rows),
        "unique_id_count": len(set(ids)),
        "duplicate_ids": sorted({i for i in ids if ids.count(i) > 1}),
        "source_id_count": len(source_ids) or None,
        "source_ids_equal_ledger_ids": (source_ids == set(ids)) if source_ids else None,
        "gate_rows": [{"id": g["id"], "status": g.get("status"),
                       "name": g.get("name")} for g in gates],
        "hardware_boundary_row": hardware is not None,
        "hardware_boundary_status": None if hardware is None else hardware.get("status"),
        "category_counts": categories,
        "all_entries_remain_gaps": ledger.get("scope", {}).get("all_entries_remain_gaps"),
        "validation_block": ledger.get("validation"),
    }


def check_capability_index():
    data = json.loads(
        (REPO / "Simulator/wksim_runtime/capability-index.json").read_text(encoding="utf-8"))
    if isinstance(data, dict):
        keys = sorted(data.keys())
        entries = data.get("capabilities") or data.get("entries") or []
        count = len(entries) if isinstance(entries, list) else None
    else:
        keys, count = None, len(data)
    return {"top_level_keys": keys, "entry_count": count,
            "path": "Simulator/wksim_runtime/capability-index.json"}


def check_issues_snapshot():
    path = HERE / "issues-snapshot.json"
    issues = json.loads(path.read_text(encoding="utf-8"))
    by_number = {issue["number"]: issue for issue in issues}
    open_numbers = sorted(n for n, i in by_number.items() if i["state"] == "OPEN")
    closed_numbers = sorted(n for n, i in by_number.items() if i["state"] == "CLOSED")
    members = {
        "G0": [1, 10, 60],
        "G2": [20, 62, 63, 64, 33],
        "G3": [39, 102, 33],
        "G4": [26, 29, 46, 60, 25],
        "G5": [41, 42, 43, 5],
        "EXCLUDED": [83, 84, 9],
    }
    gates = {}
    for gate, numbers in members.items():
        live = {}
        for number in numbers:
            issue = by_number.get(number)
            live[str(number)] = None if issue is None else {
                "state": issue["state"],
                "closedAt": issue.get("closedAt"),
                "updatedAt": issue.get("updatedAt"),
                "labels": sorted(l["name"] for l in issue.get("labels", [])),
            }
        gates[gate] = live
    abi_branch = [73, 74, 76, 77, 78, 27, 28]
    return {
        "snapshot_path": "issues-snapshot.json",
        "snapshot_sha256": sha256(path),
        "total_issues": len(issues),
        "open_count": len(open_numbers),
        "closed_count": len(closed_numbers),
        "open_numbers": open_numbers,
        "gates": gates,
        "abi_branch_states": {str(n): by_number[n]["state"] for n in abi_branch if n in by_number},
    }


def check_rate_trace():
    """Re-run the repository interval analyzer on the retained #83 trace."""
    trace_gz = REPO / "validation/33-final-combo-luna/pv-settle-1w6dru32/rate.jsonl.gz"
    if not trace_gz.is_file():
        return {"status": "trace_absent", "path": str(trace_gz)}
    CHECKS.mkdir(parents=True, exist_ok=True)
    raw = trace_gz.read_bytes()
    data = gzip.decompress(raw)
    handle = tempfile.NamedTemporaryFile(
        mode="wb", suffix=".jsonl", prefix="ds-g0g5-rate-", delete=False)
    try:
        handle.write(data)
        handle.close()
        plain = Path(handle.name)
        module_path = REPO / "tools/analyze_joint_rate_intervals.py"
        spec = importlib.util.spec_from_file_location("rate_intervals", module_path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            result = module.analyze(plain)
        except Exception as error:  # noqa: BLE001 - record the failure, do not hide it
            result = {"status": "failed", "error": f"{type(error).__name__}: {error}"}
    finally:
        Path(handle.name).unlink(missing_ok=True)
    out = CHECKS / "pv-settle-rate-intervals.json"
    out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    latch = result.get("latch_reconciliation", {})
    return {
        "status": result.get("status"),
        "trace_gz": str(trace_gz.relative_to(REPO)),
        "trace_gz_sha256": hashlib.sha256(raw).hexdigest(),
        "trace_plain_sha256": hashlib.sha256(data).hexdigest(),
        "trace_plain_bytes": len(data),
        "analyzer": "tools/analyze_joint_rate_intervals.py",
        "analyzer_sha256": sha256(module_path),
        "groups": result.get("groups"),
        "intervals": result.get("intervals"),
        "creep_total_ns": result.get("creep_total_ns"),
        "work_over_total_ns": result.get("work_over_total_ns"),
        "release_excess_total_ns": result.get("release_excess_total_ns"),
        "first_group_start_lateness_ns": result.get("first_group_start_lateness_ns"),
        "latch_status": latch.get("status"),
        "recorded_latch_lateness_ns": latch.get("recorded_latch_lateness_ns"),
        "result_sha256": sha256(out),
        "interpretation": (
            "This retained pack is the closed #83 PV compatibility run, not a G2 sustained-1x "
            "acceptance. Re-analysis here only re-derives the interval arithmetic and confirms "
            "whether a rate_unmet latch is present in the retained bytes; it transfers no PASS "
            "to the f333316 architecture candidate."
        ),
    }


def main():
    CHECKS.mkdir(parents=True, exist_ok=True)
    checks = {
        "schema": "wksim.ds-g0-g5-frontier-checks.v1",
        "scope": "read-only; no native, build, ROS, flight controller, model, UE or MATLAB execution",
        "checkout": check_checkout(),
        "pinned_artifacts": check_pinned(),
        "ledger_reconciliation": check_ledger(),
        "capability_index": check_capability_index(),
        "issues_snapshot": check_issues_snapshot(),
        "retained_rate_trace": check_rate_trace(),
    }
    out = CHECKS / "checks.json"
    out.write_text(json.dumps(checks, indent=1) + "\n", encoding="utf-8")
    summary = {
        "head": checks["checkout"]["head_observed_now"],
        "ancestor_exit": checks["checkout"]["ancestor_exit_at_current_head"],
        "ledger_rows": checks["ledger_reconciliation"]["row_count"],
        "ledger_unique_ids": checks["ledger_reconciliation"]["unique_id_count"],
        "open_issues": checks["issues_snapshot"]["open_count"],
        "rate_trace_status": checks["retained_rate_trace"].get("status"),
        "rate_trace_latch": checks["retained_rate_trace"].get("latch_status"),
        "checks_json_sha256": sha256(out),
    }
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
