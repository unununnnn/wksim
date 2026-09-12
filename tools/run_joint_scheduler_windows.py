"""Windows host launcher for WSL joint scheduler profiling.

Launches the WSL Linux profiling runner and the Windows host snapshot server in parallel,
monitors process lifecycle under a unified deadline, communicates shutdown via host stdin EOF,
and strictly verifies diagnostic and cleanup retirement evidence before declaring success.
"""
from __future__ import annotations

import argparse
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
DEFAULT_GRACE_PERIOD_S = 100.0
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


def verify_report_evidence(report: Any) -> dict[str, Any]:
    """Strictly verify report.json against profile_joint_scheduler retirement invariants."""
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

    return report


def verify_cleanup_evidence(report: Any) -> tuple[bool, str]:
    """Verify cleanup-only evidence from a raw (possibly partial) Linux report.

    Distinct from verify_report_evidence: this never requires the diagnostic
    success status.  A run cancelled mid-diagnosis is acceptable as long as
    everything it created is provably retired.  Missing or unknown evidence is
    NOT proof of cleanliness.  Only fields the real profile_joint_scheduler
    schema actually writes are consulted; nothing is fabricated.
    """
    if not isinstance(report, dict):
        return False, f"report is not a dict: {type(report).__name__}"
    return _verify_component_cleanup(report)


def verify_run_cleanup(
    output_wsl: str,
    distro: str,
    wsl_bin: str,
    reader_fn: Callable[[str, str, str], dict[str, Any]] | None = None,
) -> tuple[bool, str]:
    """Read this run's raw Linux report (no success criteria) and verify cleanup."""
    try:
        if reader_fn is not None:
            report = reader_fn(output_wsl, distro, wsl_bin)
        else:
            report = decode_json_strict(read_linux_report_file(output_wsl, distro, wsl_bin))
    except Exception as err:
        return False, f"cleanup unverified: raw report unreadable: {err}"
    return verify_cleanup_evidence(report)


def read_linux_report(
    output_wsl: str,
    distro: str = DEFAULT_DISTRO,
    wsl_bin: str = "wsl.exe",
    reader_fn: Callable[[str, str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Read and strictly verify report.json from WSL output directory."""
    if reader_fn is not None:
        report = reader_fn(output_wsl, distro, wsl_bin)
    else:
        raw_text = read_linux_report_file(output_wsl, distro, wsl_bin)
        report = decode_json_strict(raw_text)

    return verify_report_evidence(report)


def run_joint_scheduler_windows(
    output_wsl: str,
    exchange_dir: Path | str,
    *,
    distro: str = DEFAULT_DISTRO,
    timeout_s: float = 60.0,
    grace_period_s: float = DEFAULT_GRACE_PERIOD_S,
    poll_interval_s: float = 0.05,
    wsl_bin: Path | str | None = None,
    popen_fn: Callable[..., Any] | None = None,
    read_report_fn: Callable[[str, str, str], dict[str, Any]] | None = None,
    read_raw_report_fn: Callable[[str, str, str], dict[str, Any]] | None = None,
    check_wsl_dir_fn: Callable[[str, str, str], bool] | None = None,
) -> dict[str, Any]:
    """Orchestrate parallel WSL profiling runner and Windows snapshot server."""
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

    # Redirect stdout and stderr to actual files in exchange_dir to prevent pipe deadlocks
    l_stdout_file = exchange_path / "wsl_runner.stdout.log"
    l_stderr_file = exchange_path / "wsl_runner.stderr.log"
    s_stdout_file = exchange_path / "snapshot_server.stdout.log"
    s_stderr_file = exchange_path / "snapshot_server.stderr.log"

    linux_proc = None
    server_proc = None
    failure_reason = None
    need_cleanup = False
    cleanup_verified = False
    cleanup_reason = None
    linux_identity = None

    with l_stdout_file.open("wb") as l_out_f, \
         l_stderr_file.open("wb") as l_err_f, \
         s_stdout_file.open("wb") as s_out_f, \
         s_stderr_file.open("wb") as s_err_f:

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

            # Launch Windows snapshot server
            server_proc = act_popen(
                cmd_server,
                stdout=s_out_f,
                stderr=s_err_f,
            )

            while True:
                now = time.monotonic()
                if now >= deadline:
                    failure_reason = f"Execution timed out after {timeout_s:.1f}s"
                    break

                s_rc = server_proc.poll()
                l_rc = linux_proc.poll()

                if s_rc is not None and s_rc != 0:
                    failure_reason = f"Snapshot server failed with exit code {s_rc}"
                    break

                if l_rc is not None and l_rc != 0:
                    failure_reason = f"Linux runner failed with exit code {l_rc}"
                    break

                if s_rc == 0 and l_rc == 0:
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
            linux_output_dir, distro=distro, wsl_bin=wsl_executable, reader_fn=read_report_fn
        )
    except Exception as err:
        # Diagnostic evidence rejected: process exit codes alone do not prove
        # cleanup, so verify cleanup-only evidence from the raw report.
        cleanup_verified, cleanup_reason = verify_run_cleanup(
            linux_output_dir, distro, wsl_executable, reader_fn=read_raw_report_fn
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
    parser.add_argument("--timeout", type=float, default=60.0, help="Total timeout in seconds.")
    parser.add_argument("--grace-period", type=float, default=DEFAULT_GRACE_PERIOD_S, help="Grace period for Linux self-termination.")
    args = parser.parse_args(argv)

    try:
        res = run_joint_scheduler_windows(
            output_wsl=args.output_wsl,
            exchange_dir=args.exchange_dir,
            distro=args.distro,
            timeout_s=args.timeout,
            grace_period_s=args.grace_period,
        )
        print(json.dumps(res, indent=2))
        return 0
    except Exception as err:
        sys.stderr.write(f"Windows joint scheduler runner error: {err}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
