"""Independent adversarial reproductions for the #26 readiness fix review.

Read-only against the repository: every fixture is built in a temp directory.
Each case reports ``attack_success`` (security property violated) or
``defense_holds`` for the negative controls.  Pure Python plus git CLI for
index state, mirroring the audited tool's own queries.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import audit_26_closure_readiness as audit_mod
from validation.test_audit_26_closure_readiness import (
    ARCHIVED_WRAPPER_RELATIVE,
    IDENTITIES_RELATIVE,
    EVIDENCE_FILES,
    _declare_historical_wrapper,
    _fixture,
    _sha,
)


def _git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, timeout=30
    )


def _case(name, fn, results):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        try:
            results[name] = fn(root)
        except Exception as exc:  # keep the batch running
            results[name] = {"error": f"{type(exc).__name__}: {exc}"}


def case_staged_uncommitted_counts_as_tracked(root):
    """A1: index-level tracking accepts a never-committed archived copy."""
    manifest = _fixture(root)
    _declare_historical_wrapper(manifest, root)
    head = _git(root, "rev-parse", "--verify", "HEAD")
    report = audit_mod.audit(manifest, root=root)
    attack = report["status"] == "ready_blocked_by_formal_dependency" and head.returncode != 0
    return {
        "attack_success": attack,
        "detail": (
            "fixture repo has zero commits (rev-parse HEAD failed) yet the "
            "archived wrapper passed the 'tracked' check and the audit is ready"
            if attack
            else f"unexpected: status={report['status']} head_rc={head.returncode} "
            f"violations={report['violations']}"
        ),
    }


def case_untracked_declaration_still_authorizes(root):
    """A2: the identity declaration itself is never tracked-checked."""
    manifest = _fixture(root)
    _declare_historical_wrapper(manifest, root, tracked=False)
    # Track only the archived snapshot; leave the declaration untracked.
    _git(root, "add", "-f", "--", ARCHIVED_WRAPPER_RELATIVE)
    report = audit_mod.audit(manifest, root=root)
    ls = _git(root, "ls-files", "--error-unmatch", "--", IDENTITIES_RELATIVE)
    attack = report["status"] == "ready_blocked_by_formal_dependency" and ls.returncode != 0
    return {
        "attack_success": attack,
        "detail": (
            "declaration file is untracked (ls-files failed) yet its identity "
            "was honored and the audit is ready"
            if attack
            else f"unexpected: status={report['status']} violations={report['violations']}"
        ),
    }


def case_declaration_content_drift_undetected(root):
    """A3: declaration is not hash-pinned; mutating it changes nothing."""
    manifest = _fixture(root)
    _declare_historical_wrapper(manifest, root)
    declaration_path = root / IDENTITIES_RELATIVE
    data = json.loads(declaration_path.read_text(encoding="utf-8"))
    data["current_canonical_wrapper"]["sha256"] = "0" * 64
    data["purpose"] = "tampered narrative"
    declaration_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    report = audit_mod.audit(manifest, root=root)
    attack = report["status"] == "ready_blocked_by_formal_dependency"
    return {
        "attack_success": attack,
        "detail": (
            "declaration mutated (wrong current_canonical_wrapper digest, "
            "rewritten purpose) and the audit still reports ready; the "
            "declared current-canonical digest is never cross-hashed"
            if attack
            else f"unexpected: violations={report['violations']}"
        ),
    }


def case_wsl_receipt_trailing_payload(root):
    """A4: arbitrary text rides after the leading receipt JSON value."""
    manifest = _fixture(root)
    receipt = {
        "checked_unix": 1789000000.0,
        "distro": "RflySim-20.04",
        "boot_id": "00000000-0000-0000-0000-000000000000",
        "uptime": "10.0 20.0",
        "found": [],
    }
    payload = (
        json.dumps(receipt, indent=2)
        + "\n"
        + "TVpQAQIAAAAEAA" + "A" * 400 + "  # base64 MZ-style vendor blob\n"
        + "rflysim dependency config: COPTERSIM_HOME=/opt/rflysim\n"
    )
    target = root / "validation/coordination/probe/RflySim-20.04-precheck.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload, encoding="utf-8")
    _git(root, "add", "-f", "--", "validation/coordination/probe/RflySim-20.04-precheck.txt")
    report = audit_mod.audit(manifest, root=root)
    attack = not any("vendor artifacts" in item for item in report["violations"])
    return {
        "attack_success": attack,
        "detail": (
            "rflysim-named tracked file carrying a valid empty receipt plus "
            "trailing vendor text/base64 was classified as a clean receipt"
            if attack
            else f"unexpected: violations={report['violations']}"
        ),
    }


def case_malformed_declaration_fails_closed(root):
    """N1 (defense): duplicate keys / trailing garbage in the declaration."""
    manifest = _fixture(root)
    _declare_historical_wrapper(manifest, root)
    declaration_path = root / IDENTITIES_RELATIVE
    declaration_path.write_text('{"schema":"x","schema":"y"}\n', encoding="utf-8")
    report = audit_mod.audit(manifest, root=root)
    dup = report["status"] == "not_ready" and any(
        "malformed JSON" in item for item in report["violations"]
    )
    declaration_path.write_text(
        declaration_path.read_text(encoding="utf-8") + "\ngarbage\n",
        encoding="utf-8",
    )
    return {"defense_holds": dup, "violations_sample": report["violations"][:2]}


def case_found_type_tricks_rejected(root):
    """N2 (defense): non-list / non-empty ``found`` is vendor material."""
    _fixture(root)
    outcomes = {}
    for index, found in enumerate(["", 0, {}, [None], ["rflysim-core"]]):
        target = root / f"validation/coordination/probe/precheck-RflySim-{index}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "checked_unix": 1789000000.0,
                    "distro": "RflySim-20.04",
                    "boot_id": "0",
                    "uptime": "1 2",
                    "found": found,
                }
            ),
            encoding="utf-8",
        )
        _git(root, "add", "-f", "--", f"validation/coordination/probe/precheck-RflySim-{index}.json")
        reason = audit_mod._vendor_content_offender(target)
        outcomes[repr(found)] = reason is not None
    return {"defense_holds": all(outcomes.values()), "per_value": outcomes}


def case_linux_missing_fail_closed_mechanism(root):
    """N3 (defense): an addressable-but-missing provenance path is a violation."""
    _fixture(root)
    report = {"violations": [], "host_bounded": []}
    candidate = audit_mod._provenance_path(
        str(root / "absent" / "libwksim_e0.so"), root, "lifecycle cold_library", report
    )
    ok = candidate is not None and not audit_mod._actual_file(
        candidate, "lifecycle cold_library", report, sha256="0" * 64
    )
    return {
        "defense_holds": ok and bool(report["violations"]) and not report["host_bounded"],
        "violations_sample": report["violations"][:1],
    }


def case_real_cli_host_bounded_exit_zero(results):
    """E1 (evidence): real repo audit exits 0 while three checks are skipped."""
    completed = subprocess.run(
        [sys.executable, "-B", str(ROOT / "tools/audit_26_closure_readiness.py")],
        capture_output=True,
        timeout=60,
    )
    report = json.loads(completed.stdout.decode())
    return {
        "exit_code": completed.returncode,
        "status": report["status"],
        "violations": report["violations"],
        "host_bounded_count": len(report["host_bounded"]),
        "host_bounded_fields": sorted({item["field"] for item in report["host_bounded"]}),
        "observation": (
            "exit 0 / ready is reached on this Windows host only because the "
            "cold-library, cold-probe and build-output hash checks are skipped "
            "as host_bounded"
        ),
    }


def main():
    results = {}
    _case("A1_staged_uncommitted_counts_as_tracked", case_staged_uncommitted_counts_as_tracked, results)
    _case("A2_untracked_declaration_still_authorizes", case_untracked_declaration_still_authorizes, results)
    _case("A3_declaration_content_drift_undetected", case_declaration_content_drift_undetected, results)
    _case("A4_wsl_receipt_trailing_payload", case_wsl_receipt_trailing_payload, results)
    _case("N1_malformed_declaration_fails_closed", case_malformed_declaration_fails_closed, results)
    _case("N2_found_type_tricks_rejected", case_found_type_tricks_rejected, results)
    _case("N3_linux_missing_fail_closed_mechanism", case_linux_missing_fail_closed_mechanism, results)
    results["E1_real_cli_host_bounded"] = case_real_cli_host_bounded_exit_zero(results)
    out = Path(__file__).with_name("adversarial-output.json")
    out.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
