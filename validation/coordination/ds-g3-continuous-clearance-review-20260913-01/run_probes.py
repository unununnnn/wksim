"""Run every adversarial probe in this directory and write run_summary.json.

Usage (from the repository root):

    python validation/coordination/ds-g3-continuous-clearance-review-20260913-01/run_probes.py

Pure Python, no native/ROS/SITL/UE/MATLAB, no wall clock, no network.  A probe's
non-zero exit code means it DETECTED something (the count of failed checks); it is
only a crash when stderr contains a Python traceback.  The runner exits 0 when all
probes ran to completion, 1 when any probe crashed.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
PROBE_NAMES = ("probe_1_cover_index.py", "probe_2_clearance_accounting.py",
               "probe_3_threshold_and_labels.py", "probe_4_knot_boundaries.py",
               "probe_5_atomicity_pump_outcomes.py")


def read_summary(name):
    stem = name[:-3]
    path = HERE / f"{stem.replace('probe_', 'probe_')}.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return {
        "json": path.name,
        "probe": payload.get("probe"),
        "checks_total": payload.get("checks_total"),
        "checks_passed": payload.get("checks_passed"),
        "checks_failed": payload.get("checks_failed"),
        "failed_checks": [item["check"] for item in payload.get("checks", []) if not item["ok"]],
    }


def main():
    results = []
    crashed = 0
    for name in PROBE_NAMES:
        path = HERE / name
        completed = subprocess.run(
            [sys.executable, "-B", str(path)],
            cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8")
        crashed_here = "Traceback (most recent call last)" in (completed.stderr or "")
        crashed += int(crashed_here)
        summary = read_summary(name)
        results.append({
            "probe_file": name,
            "exit_code": completed.returncode,
            "crashed": crashed_here,
            "summary": summary,
            "stdout": (completed.stdout or "").strip().splitlines()[-6:],
            "stderr_tail": (completed.stderr or "").strip().splitlines()[-6:],
        })
        state = "CRASH" if crashed_here else (
            "DETECTED" if summary and summary.get("checks_failed") else "CLEAN")
        print(f"{name}: exit={completed.returncode} {state} "
              f"{'' if not summary else summary['checks_passed']}/"
              f"{'' if not summary else summary['checks_total']}")
    payload = {
        "runner": "run_probes.py",
        "python": sys.version.split()[0],
        "probe_count": len(PROBE_NAMES),
        "crashes": crashed,
        "probes": results,
    }
    out = HERE / "run_summary.json"
    with out.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"run_summary.json written; crashes={crashed}")
    return 1 if crashed else 0


if __name__ == "__main__":
    raise SystemExit(main())
