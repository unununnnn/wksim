"""Write SHA256SUMS and manifest.json for this exclusive-write audit directory.

Read-only with respect to the repository: it reads the files inside this
deliverable directory and writes only ``SHA256SUMS`` and ``manifest.json`` here.
It runs no build, native, ROS, flight-controller, model, UE or MATLAB step.

Usage: python -B validation/coordination/ds-g0-g5-frontier-20260913-01/write_manifest.py
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SELF_EXCLUDED = {"SHA256SUMS", "manifest.json"}
ARCHITECTURE_ANCESTOR = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args):
    done = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False)
    return done.returncode, done.stdout.strip()


def main():
    files = sorted(
        path for path in HERE.rglob("*")
        if path.is_file() and path.name not in SELF_EXCLUDED
    )
    entries = []
    for path in files:
        entries.append({
            "path": path.relative_to(HERE).as_posix(),
            "exists": True,
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        })

    sums_lines = [
        "# SHA256SUMS - ds-g0-g5-frontier-20260913-01 (exclusive-write read-only audit deliverable)",
        "# Byte pinning: .gitattributes declares '* -text' for this directory.",
        "# Scope: this directory only. No shared ledger, issue or existing file is covered.",
    ]
    for entry in entries:
        sums_lines.append(f"{entry['sha256']}  {entry['path']}")
    sums_path = HERE / "SHA256SUMS"
    sums_path.write_text("\n".join(sums_lines) + "\n", encoding="utf-8")

    head_code, head = git("rev-parse", "HEAD")
    branch_code, branch = git("branch", "--show-current")
    ancestor_code, _ = git("merge-base", "--is-ancestor", ARCHITECTURE_ANCESTOR, "HEAD")

    manifest = {
        "schema": "wksim.ds-g0-g5-frontier-manifest.v1",
        "audit_id": "ds-g0-g5-frontier-20260913-01",
        "scope": (
            "Exclusive-write read-only G0-G5 closure-frontier audit. SHA256SUMS records this "
            "directory only; audit.json records the retained originals this audit cites."
        ),
        "checkout": {
            "cwd": str(REPO),
            "branch": branch if branch_code == 0 else None,
            "head_at_audit_start": "7e1e137879a779f2b051b384c044e6e936878d53",
            "head_when_manifest_written": head if head_code == 0 else None,
            "architecture_ancestor": ARCHITECTURE_ANCESTOR,
            "architecture_ancestor_exit_code": ancestor_code,
        },
        "deliverable_files": entries,
        "sha256sums": {
            "path": "SHA256SUMS",
            "sha256": sha256(sums_path),
        },
        "gates_in_scope": ["G0", "G1", "G2", "G3", "G4", "G5"],
        "gates_excluded": {
            "G6": "excluded by instruction",
            "issues": {
                "83": "already CLOSED",
                "84": "real MIXED perf-hook task under another agent's read-only audit",
                "9": "optional model-plugin / scene-feedback decision (DLL ABI branch)",
            },
        },
        "gate_verdicts": {gate: "not-closed" for gate in ("G0", "G1", "G2", "G3", "G4", "G5")},
        "non_claims": [
            "No G0-G5 gate is claimed as passed.",
            "No historical PASS is transferred to the f333316 architecture candidate.",
            "No in-checkout byte verification is claimed for the external oayggl_s originals or the /root model libraries.",
            "No issue, Goal, shared ledger, module-owner source or existing file was modified.",
        ],
        "regeneration_order": ["verify_frontier.py", "write_manifest.py"],
        "write_scope": "this directory only; the auditor stops writing after this deliverable",
    }
    (HERE / "manifest.json").write_text(
        json.dumps(manifest, indent=1) + "\n", encoding="utf-8")

    print(json.dumps({
        "files": len(entries),
        "sha256sums_sha256": manifest["sha256sums"]["sha256"],
        "head_when_manifest_written": manifest["checkout"]["head_when_manifest_written"],
        "ancestor_exit": ancestor_code,
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
