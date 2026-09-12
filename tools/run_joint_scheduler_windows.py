"""Windows host launcher for WSL joint scheduler profiling.

The default kernel PID probe runs only the Linux profiling runner.  The legacy
``wsl_system`` mode additionally launches the Windows host snapshot server for
the old exchange protocol.  Both modes monitor process lifecycle under a
unified deadline, communicate shutdown via host stdin EOF, and strictly verify
diagnostic and cleanup retirement evidence before declaring success.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.wsl_root_task_snapshot import find_wsl_binary
from tools.wsl_snapshot_exchange import publish_create_only, decode_json_strict
from tools.profile_joint_scheduler import product_result_clean, failure_payload_clean

DEFAULT_DISTRO = "Ubuntu-22.04"
DEFAULT_TIMEOUT_S = 240.0
DEFAULT_GRACE_PERIOD_S = 100.0
PID_BINDING_CHOICES = ("kernel_bpf", "wsl_system")
KERNEL_BPF_TASK_ROLES = frozenset({
    "ap_worker",
    "px4_worker",
    "supervisor",
    "ap_fc/arducopter",
    "ap_fc/log_io",
    "ap_fc/DDS",
    "px4_fc/sim_send",
    "px4_fc/logger",
    "px4_fc/wq:lp_default",
})
COMPONENT_ROLES = ("preflight", "manager", "collector")
COMPONENT_EVIDENCE_FIELDS = {
    "preflight": (
        "preflight_identity", "preflight_returncode", "remaining_preflight_group",
        "preflight_cleanup_error", "preflight_group_snapshot",
    ),
    "manager": (
        "manager", "manager_returncode", "remaining_manager_group", "manager_cleanup_error",
        "manager_group_snapshot", "manager_group_killed", "stop_request",
    ),
    "collector": ("collector", "collector_returncode", "collector_cleanup_error", "collector_group_killed"),
}


def is_strict_zero_int(val: Any) -> bool:
    """Return True only if val is an int, strictly not a bool, and equals 0."""
    return isinstance(val, int) and not isinstance(val, bool) and val == 0


def _is_recorded_int(val: Any) -> bool:
    return isinstance(val, int) and not isinstance(val, bool)


def _read_components_started(report: dict[str, Any]) -> tuple[dict[str, bool] | None, str | None]:
    value = report.get("components_started")
    if not isinstance(value, dict) or set(value) != set(COMPONENT_ROLES):
        return None, "components_started must contain exactly preflight, manager and collector"
    if any(type(value[role]) is not bool for role in COMPONENT_ROLES):
        return None, "components_started values must be booleans"
    return {role: value[role] for role in COMPONENT_ROLES}, None


def _valid_process_identity(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and _is_recorded_int(value.get("pid"))
        and value.get("pid") > 0
        and _is_recorded_int(value.get("start_ticks"))
        and value.get("start_ticks") > 0
        and _is_recorded_int(value.get("pgid"))
        and value.get("pgid") > 0
    )


def _valid_group_snapshot(value: Any, identity: dict[str, Any]) -> bool:
    if not isinstance(value, list) or not value:
        return False
    observed = set()
    for row in value:
        if not isinstance(row, dict):
            return False
        pid, start_ticks = row.get("pid"), row.get("start_ticks")
        if (not _is_recorded_int(pid) or pid <= 0
                or not _is_recorded_int(start_ticks) or start_ticks <= 0):
            return False
        observed.add((pid, start_ticks))
    return (identity["pid"], identity["start_ticks"]) in observed


def _nested_cleanup_failure(value: Any) -> str | None:
    """Find cleanup-specific failures without treating trace/mission errors as residue."""
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if (
                normalized == "cleanup_error"
                or normalized == "cleanup_errors"
                or normalized.endswith("_cleanup_error")
                or normalized.endswith("_cleanup_errors")
            ) and child not in (None, "", [], {}, False):
                return normalized
            if normalized in {
                "remaining_group_members", "remaining_manager_group", "remaining_preflight_group",
            } and child not in (None, []):
                return normalized
            found = _nested_cleanup_failure(child)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for child in value:
            found = _nested_cleanup_failure(child)
            if found is not None:
                return found
    return None


def _verify_component_cleanup(report: dict[str, Any]) -> tuple[bool, str]:
    started, reason = _read_components_started(report)
    if started is None:
        return False, reason or "components_started is unknown"
    if started["manager"] and not started["preflight"]:
        return False, "manager started without preflight started evidence"
    if started["collector"] and not started["manager"]:
        return False, "collector started without manager started evidence"

    for role in COMPONENT_ROLES:
        fields = COMPONENT_EVIDENCE_FIELDS[role]
        if not started[role]:
            conflicts = [field for field in fields if field in report]
            if conflicts:
                return False, f"{role} marked not started but evidence is present: {conflicts}"
            continue

        identity_key = f"{role}_identity" if role == "preflight" else role
        if not _valid_process_identity(report.get(identity_key)):
            return False, f"{role} retirement identity is missing or invalid"
        identity = report[identity_key]
        if role in ("preflight", "manager") and not _valid_group_snapshot(
                report.get(f"{role}_group_snapshot"), identity):
            return False, f"{role}_group_snapshot is missing or invalid"
        returncode_key = f"{role}_returncode"
        if not _is_recorded_int(report.get(returncode_key)):
            return False, f"{role} retirement not recorded: {returncode_key}={report.get(returncode_key)!r}"
        cleanup_error_key = f"{role}_cleanup_error"
        if report.get(cleanup_error_key):
            return False, f"{cleanup_error_key}: {report.get(cleanup_error_key)!r}"
        if role != "collector":
            remaining_key = f"remaining_{role}_group"
            if report.get(remaining_key) != []:
                return False, f"{remaining_key} not provably empty: {report.get(remaining_key)!r}"

    if started["manager"] and report.get("epoch_groups_retired") is not True:
        return False, f"epoch_groups_retired is not True: {report.get('epoch_groups_retired')!r}"

    capture_present = "capture" in report
    capture = report.get("capture")
    if started["collector"]:
        if not isinstance(capture, dict) or capture.get("instance_removed") is not True:
            return False, "trace instance removal not proven (capture.instance_removed is not True)"
    elif capture_present:
        if not isinstance(capture, dict) or capture.get("instance_removed") is not True:
            return False, "collector not started but capture cleanup is not explicitly clean"

    nested_failure = _nested_cleanup_failure(report)
    if nested_failure is not None:
        return False, f"nested cleanup failure: {nested_failure}"
    return True, "created components retired, groups empty, epochs retired, trace instance removed"


def windows_path_to_wsl_mnt(path: Path | str) -> str:
    """Convert a local Windows drive path to its WSL /mnt/<drive>/ mount equivalent."""
    raw = str(path).replace("\\", "/")
    if raw.startswith(("//", "\\\\")) or str(path).startswith(("//", "\\\\")):
        raise ValueError(f"UNC paths cannot be converted to WSL /mnt mount: {path}")

    if os.name == "posix" and raw.startswith("/"):
        return raw

    from pathlib import PureWindowsPath
    pure = PureWindowsPath(path)
    drive = pure.drive
    if len(drive) < 2 or not drive[0].isalpha() or drive[1] != ":":
        raise ValueError(f"Path must be on a local Windows drive with a drive letter: {path}")
    drive_letter = drive[0].lower()
    rest = pure.as_posix()[len(drive):].lstrip("/")
    return f"/mnt/{drive_letter}/{rest}"


def validate_fresh_windows_dir(path: Path | str) -> Path:
    """Validate that exchange directory is on local Windows NTFS and is fresh (empty)."""
    raw = str(path).replace("\\", "/")
    if str(path).startswith(("\\\\", "//")) or raw.startswith(("//", "\\\\")):
        raise ValueError(f"UNC exchange directory rejected: {path}")
    if raw.startswith("/root"):
        raise ValueError(f"Linux private root exchange directory rejected: {path}")
    p = Path(path)
    if p.is_symlink() or os.path.islink(p):
        raise ValueError(f"Symlink exchange directory rejected: {p}")
    try:
        resolved = p.resolve(strict=False)
    except OSError as err:
        raise ValueError(f"Invalid exchange directory: {err}")
    if str(resolved).startswith(("\\\\", "//")):
        raise ValueError(f"Resolved UNC exchange directory rejected: {resolved}")
    if resolved.is_symlink() or os.path.islink(resolved):
        raise ValueError(f"Symlink resolved exchange directory rejected: {resolved}")
    if os.name == "nt" and not re.match(r"^[a-zA-Z]:", str(resolved)):
        raise ValueError(f"Exchange directory must be on a local Windows drive: {resolved}")
    if resolved.exists():
        if not resolved.is_dir():
            raise NotADirectoryError(f"Exchange directory exists but is not a directory: {resolved}")
        if any(resolved.iterdir()):
            raise ValueError(f"Exchange directory must be fresh and empty, but contains files: {resolved}")
    else:
        resolved.mkdir(parents=True, exist_ok=False)
    return resolved


def check_wsl_directory_status(
    output_wsl: str, distro: str = DEFAULT_DISTRO, wsl_bin: str = "wsl.exe"
) -> bool:
    """Check WSL directory: return True if exists (rc=0), False if absent (rc=1), raise on other rc."""
    cmd = [
        wsl_bin, "-d", distro, "-u", "root", "--", "sh", "-c",
        'if [ -L "$1" ]; then echo SYMLINK; exit 2; elif [ -e "$1" ]; then exit 0; else exit 1; fi',
        "wksim-output-check", output_wsl,
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=5.0, check=False)
    if proc.returncode == 0:
        return True
    elif proc.returncode == 1:
        return False
    elif proc.returncode == 2 or b"SYMLINK" in proc.stdout:
        raise ValueError(f"output_wsl path is a symlink in WSL: {output_wsl}")
    else:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"WSL output directory existence check failed with unexpected code {proc.returncode}: {err}"
        )


def validate_fresh_wsl_dir(
    output_wsl: str,
    distro: str = DEFAULT_DISTRO,
    wsl_bin: str = "wsl.exe",
    check_fn: Callable[[str, str, str], bool] | None = None,
) -> str:
    """Validate that output_wsl aligns with profile pattern and is fresh (does not exist)."""
    if not isinstance(output_wsl, str) or not output_wsl.strip():
        raise ValueError(f"output_wsl must be a non-empty string, got: {output_wsl!r}")
    cleaned = output_wsl.strip()

    if ".." in cleaned.split("/"):
        raise ValueError(f"output_wsl must not contain '..' path traversal: {output_wsl!r}")
    if not re.fullmatch(r"/root/wksim-scheduler-probe-[^/]+", cleaned):
        raise ValueError(
            "output_wsl must match profile pattern '/root/wksim-scheduler-probe-*' "
            f"with /root as its parent, got: {output_wsl!r}"
        )

    checker = check_fn if check_fn is not None else check_wsl_directory_status
    if checker(cleaned, distro, wsl_bin):
        raise ValueError(f"output_wsl directory already exists in WSL (must be fresh): {cleaned}")
    return cleaned


def read_linux_report_file(
    output_wsl: str, distro: str = DEFAULT_DISTRO, wsl_bin: str = "wsl.exe"
) -> str:
    """Read report.json content from WSL via wsl command."""
    cmd = [
        wsl_bin, "-d", distro, "-u", "root", "--", "python3", "-c",
        f"import pathlib, sys; p = pathlib.Path({repr(output_wsl)}) / 'report.json'; sys.stdout.write(p.read_text())",
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=10.0, check=False)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Failed to read report.json from WSL (rc={proc.returncode}): {err}")
    return proc.stdout.decode("utf-8", errors="replace")


def _verify_kernel_bpf_success(report: dict[str, Any]) -> None:
    if report.get("pid_binding") != "kernel_bpf":
        raise RuntimeError("Kernel BPF report pid_binding must be exactly 'kernel_bpf'")

    manifest_path = report.get("pid_probe_manifest")
    if not isinstance(manifest_path, str) or not manifest_path:
        raise RuntimeError("Kernel BPF report pid_probe_manifest is missing")
    if report.get("pid_probe_transferred_to_collector") is not True:
        raise RuntimeError("Kernel BPF probe transfer is not proven")
    if report.get("pid_probe_parent_closed") is not True:
        raise RuntimeError("Kernel BPF parent probe close is not proven")

    capture = report.get("capture")
    if not isinstance(capture, dict):
        raise RuntimeError("Kernel BPF report capture is missing")
    if capture.get("pid_binding") != "kernel_bpf":
        raise RuntimeError("Kernel BPF capture pid_binding must be exactly 'kernel_bpf'")
    if not isinstance(capture.get("kernel_probe_manifest"), dict):
        raise RuntimeError("Kernel BPF capture manifest is missing")
    if capture.get("kernel_probe_closed") is not True:
        raise RuntimeError("Kernel BPF collector probe close is not proven")

    mapping = capture.get("pid_mapping")
    if not isinstance(mapping, dict):
        raise RuntimeError("Kernel BPF pid_mapping is missing")
    if mapping.get("bpf_sampling_detached") is not True:
        raise RuntimeError("Kernel BPF sampling detachment is not proven")
    if not is_strict_zero_int(mapping.get("bpf_dropped_updates")):
        raise RuntimeError("Kernel BPF bpf_dropped_updates must be exact int 0")
    detached_ns = mapping.get("bpf_detached_monotonic_ns")
    if not _is_recorded_int(detached_ns) or detached_ns <= 0:
        raise RuntimeError("Kernel BPF detach timestamp is missing")

    boundaries = capture.get("capture_boundaries")
    if not isinstance(boundaries, dict):
        raise RuntimeError("Kernel BPF capture boundaries are missing")
    boundary_detached_ns = boundaries.get("bpf_detached_monotonic_ns")
    if boundary_detached_ns != detached_ns:
        raise RuntimeError("Kernel BPF detach timestamp is not bound to capture boundaries")
    started_ns = capture.get("started_monotonic_ns")
    if not _is_recorded_int(started_ns) or started_ns <= 0:
        raise RuntimeError("Kernel BPF formal capture start timestamp is missing")
    if detached_ns >= started_ns:
        raise RuntimeError("Kernel BPF sampling detached after formal capture began")

    proof = capture.get("post_capture_tasks_proof")
    if not isinstance(proof, dict):
        raise RuntimeError("Kernel BPF post_capture_tasks_proof is missing")
    roles = proof.get("roles_verified")
    if (
        not isinstance(roles, list)
        or len(roles) != len(KERNEL_BPF_TASK_ROLES)
        or set(roles) != KERNEL_BPF_TASK_ROLES
    ):
        raise RuntimeError("Kernel BPF post_capture_tasks_proof must contain exactly 9 roles")
    if type(proof.get("count")) is not int or proof.get("count") != 9:
        raise RuntimeError("Kernel BPF post_capture_tasks_proof count must be exact int 9")
    if type(proof.get("owner_count")) is not int or proof.get("owner_count") != 5:
        raise RuntimeError("Kernel BPF post_capture_tasks_proof owner_count must be exact int 5")
    if proof.get("source") != "kernel_bpf_then_stable_proc_lifetimes":
        raise RuntimeError("Kernel BPF post-capture proof source is not native BPF proof")


def _verify_kernel_bpf_cleanup(report: dict[str, Any]) -> tuple[bool, str]:
    """Verify only probe mode/retirement for a failed or cancelled kernel run."""
    if report.get("pid_binding") != "kernel_bpf":
        return False, "kernel_bpf cleanup report pid_binding is missing or mismatched"

    has_manifest = "pid_probe_manifest" in report
    has_transfer = "pid_probe_transferred_to_collector" in report
    if has_manifest and (not isinstance(report.get("pid_probe_manifest"), str)
                         or not report["pid_probe_manifest"]):
        return False, "pid_probe_manifest is malformed"
    if has_transfer and report.get("pid_probe_transferred_to_collector") is not True:
        return False, "pid_probe_transferred_to_collector is not True"

    if has_manifest or has_transfer:
        if report.get("pid_probe_parent_closed") is not True:
            return False, "pid_probe_parent_closed is not proven"

    capture = report.get("capture")
    if capture is not None:
        if not isinstance(capture, dict):
            return False, "capture is malformed"
        if capture.get("pid_binding") != "kernel_bpf":
            return False, "kernel_bpf capture pid_binding is missing or mismatched"
        if not has_transfer:
            return False, "kernel_bpf capture exists without probe transfer evidence"
        if capture.get("kernel_probe_closed") is not True:
            return False, "kernel_probe_closed is not proven after probe transfer"
    elif has_transfer:
        return False, "kernel_probe_closed is not proven after probe transfer"
    return True, "kernel BPF probe creation/transfer cleanup is proven"


def verify_report_evidence(
    report: Any, *, pid_binding: str = "kernel_bpf"
) -> dict[str, Any]:
    """Strictly verify report.json against profile_joint_scheduler retirement invariants."""
    if pid_binding not in PID_BINDING_CHOICES:
        raise ValueError(f"pid_binding must be one of {PID_BINDING_CHOICES!r}, got: {pid_binding!r}")
    if not isinstance(report, dict):
        raise ValueError(f"report.json content must be a dict, got: {type(report).__name__}")
    if not failure_payload_clean(report):
        raise RuntimeError('Report contains non-empty nested failure evidence')

    status = report.get("status")
    if status != "diagnostic_captured_and_retired":
        raise RuntimeError(f"Report status is not diagnostic_captured_and_retired: {status!r}")

    mgr_rc = report.get("manager_returncode")
    if not is_strict_zero_int(mgr_rc):
        raise RuntimeError(f"Report manager_returncode must be exact int 0, got: {mgr_rc!r}")

    col_rc = report.get("collector_returncode")
    if not is_strict_zero_int(col_rc):
        raise RuntimeError(f"Report collector_returncode must be exact int 0, got: {col_rc!r}")

    if report.get("epoch_groups_retired") is not True:
        raise RuntimeError(f"Report epoch_groups_retired must be True, got: {report.get('epoch_groups_retired')!r}")

    if report.get("sources_unchanged") is not True:
        raise RuntimeError(f"Report sources_unchanged must be True, got: {report.get('sources_unchanged')!r}")

    if report.get("remaining_manager_group") != []:
        raise RuntimeError(
            f"Report remaining_manager_group must be [], got: {report.get('remaining_manager_group')!r}"
        )

    capture = report.get("capture")
    if not isinstance(capture, dict):
        raise RuntimeError(f"Report capture must be a dict, got: {type(capture).__name__}")
    if capture.get("complete") is not True:
        raise RuntimeError(f"Report capture.complete must be True, got: {capture.get('complete')!r}")
    if capture.get("instance_removed") is not True:
        raise RuntimeError(f"Report capture.instance_removed must be True, got: {capture.get('instance_removed')!r}")

    prod_result = report.get("product_result")
    if not product_result_clean(prod_result):
        raise RuntimeError(f"Report product_result is not clean: {prod_result!r}")

    cleanup_errors = [k for k in report.keys() if k.endswith("error")]
    if cleanup_errors:
        details = {k: report[k] for k in cleanup_errors}
        raise RuntimeError(f"Report contains cleanup errors: {details}")

    cleanup_ok, cleanup_reason = _verify_component_cleanup(report)
    if not cleanup_ok:
        raise RuntimeError(f"Report cleanup evidence is incomplete: {cleanup_reason}")
    components, _ = _read_components_started(report)
    if components != {role: True for role in COMPONENT_ROLES}:
        raise RuntimeError(f"Full report requires all components_started=True, got: {components!r}")

    if pid_binding == "kernel_bpf":
        _verify_kernel_bpf_success(report)

    return report


def verify_cleanup_evidence(
    report: Any, *, pid_binding: str = "kernel_bpf"
) -> tuple[bool, str]:
    """Verify cleanup-only evidence from a raw (possibly partial) Linux report.

    Distinct from verify_report_evidence: this never requires the diagnostic
    success status.  A run cancelled mid-diagnosis is acceptable as long as
    everything it created is provably retired.  Missing or unknown evidence is
    NOT proof of cleanliness.  Only fields the real profile_joint_scheduler
    schema actually writes are consulted; nothing is fabricated.
    """
    if pid_binding not in PID_BINDING_CHOICES:
        return False, f"invalid pid_binding: {pid_binding!r}"
    if not isinstance(report, dict):
        return False, f"report is not a dict: {type(report).__name__}"
    if pid_binding == "kernel_bpf":
        probe_ok, probe_reason = _verify_kernel_bpf_cleanup(report)
        if not probe_ok:
            return False, probe_reason
    return _verify_component_cleanup(report)


def verify_run_cleanup(
    output_wsl: str,
    distro: str,
    wsl_bin: str,
    reader_fn: Callable[[str, str, str], dict[str, Any]] | None = None,
    *,
    pid_binding: str = "kernel_bpf",
) -> tuple[bool, str]:
    """Read this run's raw Linux report (no success criteria) and verify cleanup."""
    try:
        if reader_fn is not None:
            report = reader_fn(output_wsl, distro, wsl_bin)
        else:
            report = decode_json_strict(read_linux_report_file(output_wsl, distro, wsl_bin))
    except Exception as err:
        return False, f"cleanup unverified: raw report unreadable: {err}"
    return verify_cleanup_evidence(report, pid_binding=pid_binding)


def read_linux_report(
    output_wsl: str,
    distro: str = DEFAULT_DISTRO,
    wsl_bin: str = "wsl.exe",
    reader_fn: Callable[[str, str, str], dict[str, Any]] | None = None,
    *,
    pid_binding: str = "kernel_bpf",
) -> dict[str, Any]:
    """Read and strictly verify report.json from WSL output directory."""
    if reader_fn is not None:
        report = reader_fn(output_wsl, distro, wsl_bin)
    else:
        raw_text = read_linux_report_file(output_wsl, distro, wsl_bin)
        report = decode_json_strict(raw_text)

    return verify_report_evidence(report, pid_binding=pid_binding)


def run_joint_scheduler_windows(
    output_wsl: str,
    exchange_dir: Path | str,
    *,
    distro: str = DEFAULT_DISTRO,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    grace_period_s: float = DEFAULT_GRACE_PERIOD_S,
    poll_interval_s: float = 0.05,
    wsl_bin: Path | str | None = None,
    popen_fn: Callable[..., Any] | None = None,
    read_report_fn: Callable[[str, str, str], dict[str, Any]] | None = None,
    read_raw_report_fn: Callable[[str, str, str], dict[str, Any]] | None = None,
    check_wsl_dir_fn: Callable[[str, str, str], bool] | None = None,
    pid_binding: str = "kernel_bpf",
) -> dict[str, Any]:
    """Run the Linux profiler, optionally with the legacy Windows snapshot server."""
    if pid_binding not in PID_BINDING_CHOICES:
        raise ValueError(
            f"pid_binding must be one of {PID_BINDING_CHOICES!r}, got: {pid_binding!r}"
        )

    use_wsl_system = pid_binding == "wsl_system"
    if (
        isinstance(timeout_s, bool)
        or not isinstance(timeout_s, (int, float))
        or not math.isfinite(timeout_s)
        or timeout_s <= 0
    ):
        raise ValueError(f"timeout_s must be a finite positive number, got: {timeout_s!r}")

    if (
        isinstance(grace_period_s, bool)
        or not isinstance(grace_period_s, (int, float))
        or not math.isfinite(grace_period_s)
        or grace_period_s <= 0
    ):
        raise ValueError(f"grace_period_s must be a finite positive number, got: {grace_period_s!r}")

    if (
        isinstance(poll_interval_s, bool)
        or not isinstance(poll_interval_s, (int, float))
        or not math.isfinite(poll_interval_s)
        or poll_interval_s <= 0
    ):
        raise ValueError(f"poll_interval_s must be a finite positive number, got: {poll_interval_s!r}")

    act_popen = popen_fn if popen_fn is not None else subprocess.Popen
    wsl_executable = str(wsl_bin) if wsl_bin is not None else find_wsl_binary()
    exchange_path = validate_fresh_windows_dir(exchange_dir)
    linux_output_dir = validate_fresh_wsl_dir(output_wsl, distro, wsl_executable, check_fn=check_wsl_dir_fn)
    linux_exchange_dir = windows_path_to_wsl_mnt(exchange_path)
    repo_root_wsl = windows_path_to_wsl_mnt(REPO_ROOT)

    cmd_linux = [
        wsl_executable,
        "-d", distro,
        "-u", "root",
        "--cd", repo_root_wsl,
        "--",
        "python3",
        "tools/profile_joint_scheduler.py",
        "--output", linux_output_dir,
        "--exchange-dir", linux_exchange_dir,
        "--watch-host-stdin",
    ]
    if pid_binding == "kernel_bpf":
        cmd_linux.append("--kernel-pid-probe")

    cmd_server = [
        sys.executable,
        str(REPO_ROOT / "tools" / "serve_wsl_snapshot_requests.py"),
        "--exchange-dir", str(exchange_path),
        "--timeout", str(timeout_s),
        "--distro", distro,
    ]
    if wsl_bin is not None:
        cmd_server.extend(["--wsl-path", str(wsl_bin)])

    start_mono = time.monotonic()
    deadline = start_mono + timeout_s

    # Redirect stdout and stderr to actual files in exchange_dir to prevent pipe deadlocks.
    l_stdout_file = exchange_path / "wsl_runner.stdout.log"
    l_stderr_file = exchange_path / "wsl_runner.stderr.log"
    s_stdout_file = exchange_path / "snapshot_server.stdout.log"
    s_stderr_file = exchange_path / "snapshot_server.stderr.log"

    linux_proc = None
    server_proc = None
    server_started = False
    failure_reason = None
    need_cleanup = False
    cleanup_verified = False
    cleanup_reason = None
    linux_identity = None

    with ExitStack() as stack:
        l_out_f = stack.enter_context(l_stdout_file.open("wb"))
        l_err_f = stack.enter_context(l_stderr_file.open("wb"))
        s_out_f = stack.enter_context(s_stdout_file.open("wb")) if use_wsl_system else None
        s_err_f = stack.enter_context(s_stderr_file.open("wb")) if use_wsl_system else None
        try:
            # Launch Linux runner with stdin=PIPE kept open
            linux_proc = act_popen(
                cmd_linux,
                stdin=subprocess.PIPE,
                stdout=l_out_f,
                stderr=l_err_f,
            )
            linux_identity = {
                "pid": getattr(linux_proc, "pid", None),
                "cmd": cmd_linux,
                "distro": distro,
                "output_wsl": linux_output_dir,
            }

            if use_wsl_system:
                # Launch Windows snapshot server only for the legacy protocol.
                server_proc = act_popen(
                    cmd_server,
                    stdout=s_out_f,
                    stderr=s_err_f,
                )
                server_started = True

            while True:
                now = time.monotonic()
                if now >= deadline:
                    failure_reason = f"Execution timed out after {timeout_s:.1f}s"
                    break

                l_rc = linux_proc.poll()

                if use_wsl_system:
                    s_rc = server_proc.poll()
                    if s_rc is not None and s_rc != 0:
                        failure_reason = f"Snapshot server failed with exit code {s_rc}"
                        break
                if l_rc is not None and l_rc != 0:
                    failure_reason = f"Linux runner failed with exit code {l_rc}"
                    break

                if use_wsl_system:
                    complete = s_rc == 0 and l_rc == 0
                else:
                    complete = l_rc == 0

                if complete:
                    break

                time.sleep(poll_interval_s)

        except BaseException as exc:
            if failure_reason is None:
                failure_reason = f"Execution aborted by {type(exc).__name__}: {exc}"
            raise
        finally:
            if linux_proc is not None:
                # Signal Linux process to self-terminate by closing stdin (EOF)
                if failure_reason is not None or linux_proc.poll() is None:
                    if linux_proc.stdin and not getattr(linux_proc.stdin, "closed", False):
                        try:
                            linux_proc.stdin.close()
                        except Exception:
                            pass

                    # Bounded grace period wait
                    grace_deadline = time.monotonic() + grace_period_s
                    while time.monotonic() < grace_deadline:
                        if linux_proc.poll() is not None:
                            break
                        time.sleep(0.05)

                    # Check whether Linux runner exited. Never kill wsl.exe or user processes!
                    if linux_proc.poll() is None:
                        need_cleanup = True
                        cleanup_reason = (
                            "linux runner still live after stdin EOF grace period; "
                            "left running (wsl.exe / user processes are never killed)"
                        )
                    elif failure_reason is not None:
                        # Wrapper exit alone does NOT prove inner cleanup: read this
                        # run's raw report and separately verify retirement of the
                        # preflight/manager/collector, epoch groups and trace
                        # instance.  Partial diagnostics with proven cleanup are OK;
                        # missing report/evidence or residue means need_cleanup.
                        cleanup_verified, cleanup_reason = verify_run_cleanup(
                            linux_output_dir, distro, wsl_executable,
                            reader_fn=read_raw_report_fn,
                            pid_binding=pid_binding,
                        )
                        need_cleanup = not cleanup_verified
                else:
                    # Normal completion: ensure stdin is closed cleanly
                    if linux_proc.stdin and not getattr(linux_proc.stdin, "closed", False):
                        try:
                            linux_proc.stdin.close()
                        except Exception:
                            pass
            else:
                cleanup_reason = "linux runner was never started"

            if server_proc is not None:
                # Terminate Windows server process if still running
                if server_proc.poll() is None:
                    try:
                        server_proc.terminate()
                    except Exception:
                        pass
                    server_grace = time.monotonic() + 5.0
                    while time.monotonic() < server_grace:
                        if server_proc.poll() is not None:
                            break
                        time.sleep(0.05)
                    if server_proc.poll() is None:
                        try:
                            server_proc.kill()
                        except Exception:
                            pass

            # Write run_log.json if aborted by exception
            if failure_reason is not None and not (exchange_path / "run_log.json").exists():
                abort_record: dict[str, Any] = {
                    "start_monotonic": start_mono,
                    "elapsed_s": time.monotonic() - start_mono,
                    "timeout_s": timeout_s,
                    "grace_period_s": grace_period_s,
                    "distro": distro,
                    "output_wsl": linux_output_dir,
                    "exchange_dir": str(exchange_path),
                    "pid_binding": pid_binding,
                    "server_started": server_started,
                    "linux_returncode": linux_proc.poll() if linux_proc else None,
                    "server_returncode": server_proc.poll() if server_proc else None,
                    "need_cleanup": need_cleanup,
                    "cleanup_verified": cleanup_verified,
                    "cleanup_reason": cleanup_reason,
                    "identity": linux_identity if need_cleanup else None,
                    "failure_reason": failure_reason,
                    "status": "failed",
                }
                try:
                    publish_create_only(exchange_path / "run_log.json", abort_record)
                except Exception:
                    pass

    log_record: dict[str, Any] = {
        "start_monotonic": start_mono,
        "elapsed_s": time.monotonic() - start_mono,
        "timeout_s": timeout_s,
        "grace_period_s": grace_period_s,
        "distro": distro,
        "output_wsl": linux_output_dir,
        "exchange_dir": str(exchange_path),
        "pid_binding": pid_binding,
        "server_started": server_started,
        "linux_returncode": linux_proc.poll() if linux_proc else None,
        "server_returncode": server_proc.poll() if server_proc else None,
        "need_cleanup": need_cleanup,
        "cleanup_verified": cleanup_verified,
        "cleanup_reason": cleanup_reason,
        "identity": linux_identity if need_cleanup else None,
        "failure_reason": failure_reason,
    }

    if failure_reason is not None:
        log_record["status"] = "failed"
        if not (exchange_path / "run_log.json").exists():
            publish_create_only(exchange_path / "run_log.json", log_record)
        raise RuntimeError(
            f"Joint scheduler run failed: {failure_reason} "
            f"(need_cleanup={need_cleanup}, cleanup_verified={cleanup_verified})"
        )

    # Both exited with code 0: now verify report.json evidence
    try:
        report = read_linux_report(
            linux_output_dir, distro=distro, wsl_bin=wsl_executable,
            reader_fn=read_report_fn, pid_binding=pid_binding,
        )
    except Exception as err:
        # Diagnostic evidence rejected: process exit codes alone do not prove
        # cleanup, so verify cleanup-only evidence from the raw report.
        cleanup_verified, cleanup_reason = verify_run_cleanup(
            linux_output_dir, distro, wsl_executable,
            reader_fn=read_raw_report_fn, pid_binding=pid_binding,
        )
        need_cleanup = not cleanup_verified
        log_record["status"] = "failed"
        log_record["need_cleanup"] = need_cleanup
        log_record["cleanup_verified"] = cleanup_verified
        log_record["cleanup_reason"] = cleanup_reason
        log_record["identity"] = linux_identity if need_cleanup else None
        log_record["failure_reason"] = f"Report validation failed: {err}"
        if not (exchange_path / "run_log.json").exists():
            publish_create_only(exchange_path / "run_log.json", log_record)
        raise RuntimeError(
            f"Report validation failed: {err} "
            f"(need_cleanup={need_cleanup}, cleanup_verified={cleanup_verified})"
        ) from err

    log_record["status"] = "success"
    log_record["cleanup_verified"] = True
    log_record["cleanup_reason"] = "full report evidence verified"
    log_record["report"] = report
    publish_create_only(exchange_path / "run_log.json", log_record)

    return {
        "status": "success",
        "output_wsl": linux_output_dir,
        "exchange_dir": str(exchange_path),
        "distro": distro,
        "pid_binding": pid_binding,
        "server_started": server_started,
        "server_returncode": server_proc.poll() if server_proc else None,
        "elapsed_s": time.monotonic() - start_mono,
        "cleanup_verified": True,
        "report_status": report.get("status"),
        "report": report,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for running joint scheduler from Windows."""
    parser = argparse.ArgumentParser(description="Run joint scheduler from Windows host.")
    parser.add_argument("--output-wsl", required=True, help="Fresh Linux output directory (/root/wksim-scheduler-probe-*).")
    parser.add_argument("--exchange-dir", type=Path, required=True, help="Fresh local Windows exchange directory.")
    parser.add_argument("--distro", default=DEFAULT_DISTRO, help=f"WSL distribution name (default: {DEFAULT_DISTRO}).")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        help=f"Total startup and run timeout in seconds (default: {DEFAULT_TIMEOUT_S:.1f}).",
    )
    parser.add_argument("--grace-period", type=float, default=DEFAULT_GRACE_PERIOD_S, help="Grace period for Linux self-termination.")
    parser.add_argument(
        "--pid-binding",
        choices=PID_BINDING_CHOICES,
        default="kernel_bpf",
        help="PID evidence binding mode (default: kernel_bpf; wsl_system is legacy).",
    )
    args = parser.parse_args(argv)

    try:
        res = run_joint_scheduler_windows(
            output_wsl=args.output_wsl,
            exchange_dir=args.exchange_dir,
            distro=args.distro,
            timeout_s=args.timeout,
            grace_period_s=args.grace_period,
            pid_binding=args.pid_binding,
        )
        print(json.dumps(res, indent=2))
        return 0
    except Exception as err:
        sys.stderr.write(f"Windows joint scheduler runner error: {err}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
