"""Windows host snapshot request server for WSL diagnostic exchange.

Monitors a local Windows NTFS exchange directory, processes pre_bootstrap_leaders
and post_capture_tasks requests once each, validates caller and owner identities,
and produces atomically published response snapshots.
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

from tools.wsl_root_task_snapshot import DEFAULT_DISTRO, find_wsl_binary, snapshot_wsl_root_tasks
from tools.wsl_snapshot_exchange import (
    decode_json_strict,
    is_strict_pos_int,
    make_snapshot_response,
    publish_create_only,
    validate_snapshot_request,
)

PHASES = ("pre_bootstrap_leaders", "post_capture_tasks")
MAX_REQUEST_BYTES = 64 * 1024


def validate_exchange_dir(path: Path | str) -> Path:
    """Validate exchange directory: must exist, local NTFS, no UNC, no Linux private root."""
    p = Path(path)
    raw = str(p).replace("\\", "/")
    if str(p).startswith(("\\\\", "//")):
        raise ValueError(f"UNC exchange directory rejected: {p}")
    if raw.startswith("/root"):
        raise ValueError(f"Linux private root exchange directory rejected: {p}")
    if p.is_symlink() or os.path.islink(p):
        raise ValueError(f"Symlink exchange directory rejected: {p}")
    resolved = p.resolve(strict=False)
    if str(resolved).startswith(("\\\\", "//")):
        raise ValueError(f"Resolved UNC exchange directory rejected: {resolved}")
    if resolved.is_symlink() or os.path.islink(resolved):
        raise ValueError(f"Symlink resolved exchange directory rejected: {resolved}")
    resolved_str = str(resolved).replace("\\", "/")
    if resolved_str.startswith("/root"):
        raise ValueError(f"Linux private root exchange directory rejected: {resolved}")
    if not resolved.is_dir():
        raise FileNotFoundError(f"Exchange directory does not exist or is not a directory: {resolved}")
    if os.name == "nt" and not re.match(r"^[a-zA-Z]:", str(resolved)):
        raise ValueError(f"Exchange directory must be on a local Windows drive: {resolved}")
    return resolved


def query_wsl_system_boot_id(
    *,
    distro: str = DEFAULT_DISTRO,
    wsl_path: Path | str | None = None,
    timeout_s: float = 5.0,
) -> str:
    """Query genuine host system root boot_id from /proc/sys/kernel/random/boot_id."""
    wsl_bin = str(wsl_path) if wsl_path is not None else find_wsl_binary()
    cmd = [wsl_bin, "-d", distro, "--system", "-u", "root", "cat", "/proc/sys/kernel/random/boot_id"]
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout_s, check=False)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Failed to query system boot_id (rc={proc.returncode}): {err}")
    boot_id = proc.stdout.decode("utf-8", errors="replace").strip()
    if not boot_id:
        raise RuntimeError("Empty boot_id returned by system container")
    return boot_id


def _verify_snapshot_targets(snapshot: dict[str, Any], req_dict: dict[str, Any]) -> None:
    """Verify collector and 5 owners are observed in host snapshot with matching start_ticks."""
    leaders = snapshot.get("leaders") if isinstance(snapshot, dict) else None
    if not isinstance(leaders, dict):
        raise ValueError("Snapshot missing valid leaders dictionary")
    targets = {**req_dict["owners"], "collector": req_dict["collector"]}
    for role, meta in targets.items():
        pid = meta["pid"]
        rec = leaders.get(pid) if pid in leaders else leaders.get(str(pid))
        if rec is None:
            raise ValueError(f"Target process {role} (pid {pid}) missing from snapshot leaders")
        if not isinstance(rec, dict):
            raise ValueError(
                f"Target process {role} (pid {pid}) leader record must be a dict, got: {type(rec).__name__}"
            )
        ticks = rec.get("start_ticks")
        if not is_strict_pos_int(ticks):
            raise ValueError(
                f"Target process {role} (pid {pid}) start_ticks must be a positive int, got: {ticks!r}"
            )
        if ticks != meta["start_ticks"]:
            raise ValueError(
                f"Target process {role} (pid {pid}) start_ticks mismatch: {ticks} != {meta['start_ticks']}"
            )


def serve_snapshot_requests(
    exchange_dir: Path | str,
    timeout_s: float,
    *,
    distro: str = DEFAULT_DISTRO,
    wsl_path: Path | str | None = None,
    snapshot_fn: Callable[..., dict[str, Any]] | None = None,
    boot_id_fn: Callable[..., str] | None = None,
    poll_interval_s: float = 0.05,
    max_request_bytes: int = MAX_REQUEST_BYTES,
) -> dict[str, Any]:
    """Process pre_bootstrap_leaders and post_capture_tasks requests once each."""
    if (
        isinstance(timeout_s, bool)
        or not isinstance(timeout_s, (int, float))
        or not math.isfinite(timeout_s)
        or timeout_s <= 0
    ):
        raise ValueError(f"timeout_s must be a finite positive number, got: {timeout_s!r}")

    if not is_strict_pos_int(max_request_bytes):
        raise ValueError(f"max_request_bytes must be a positive int, got: {max_request_bytes!r}")

    if (
        isinstance(poll_interval_s, bool)
        or not isinstance(poll_interval_s, (int, float))
        or not math.isfinite(poll_interval_s)
        or poll_interval_s <= 0
    ):
        raise ValueError(f"poll_interval_s must be a finite positive number, got: {poll_interval_s!r}")

    act_snapshot_fn = snapshot_fn if snapshot_fn is not None else snapshot_wsl_root_tasks
    act_boot_id_fn = boot_id_fn if boot_id_fn is not None else query_wsl_system_boot_id
    exchange_path = validate_exchange_dir(exchange_dir)
    start_mono = time.monotonic()
    deadline = start_mono + timeout_s

    phases_handled = []
    first_request: dict[str, Any] | None = None

    for phase in PHASES:
        resp_path = exchange_path / f"{phase}.response.json"
        if resp_path.exists():
            raise RuntimeError(f"Response file already exists for phase {phase}: {resp_path}")

        req_path = exchange_path / f"{phase}.request.json"
        while not req_path.exists():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for {req_path.name} after {timeout_s}s")
            time.sleep(min(poll_interval_s, max(0.001, remaining)))

        # The create-only publisher briefly retains the temporary hard link
        # after publishing the complete file.  That valid state is readable.
        if req_path.is_symlink() or os.path.islink(req_path):
            raise ValueError(f"Symlink request file rejected: {req_path}")

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Timed out before reading {req_path.name}")

        with open(req_path, "rb") as f:
            req_bytes = f.read(max_request_bytes + 1)
        if len(req_bytes) > max_request_bytes:
            raise ValueError(
                f"Request file {req_path.name} exceeds max size limit of {max_request_bytes} bytes"
            )
        if not req_bytes:
            raise ValueError(f"Empty request file: {req_path.name}")

        req_dict = validate_snapshot_request(decode_json_strict(req_bytes))
        if req_dict["phase"] != phase:
            raise ValueError(f"Phase mismatch in {req_path.name}: expected {phase}, got {req_dict['phase']}")

        col_pid = req_dict["collector"]["pid"]
        if col_pid in {meta["pid"] for meta in req_dict["owners"].values()}:
            raise ValueError(f"Collector pid {col_pid} collides with an owner pid")

        # Invariant check between phase 1 and phase 2
        if first_request is None:
            first_request = req_dict
        else:
            if req_dict["run_id"] != first_request["run_id"]:
                raise ValueError(
                    f"Phase {phase} run_id mismatch with phase 1: {req_dict['run_id']} != {first_request['run_id']}"
                )
            if req_dict["epoch"] != first_request["epoch"]:
                raise ValueError(
                    f"Phase {phase} epoch mismatch with phase 1: {req_dict['epoch']} != {first_request['epoch']}"
                )
            if req_dict["boot_id"] != first_request["boot_id"]:
                raise ValueError(
                    f"Phase {phase} boot_id mismatch with phase 1: {req_dict['boot_id']} != {first_request['boot_id']}"
                )
            if req_dict["target_pid_ns"] != first_request["target_pid_ns"]:
                raise ValueError(
                    f"Phase {phase} target_pid_ns mismatch with phase 1: {req_dict['target_pid_ns']} != {first_request['target_pid_ns']}"
                )
            if req_dict["collector"] != first_request["collector"]:
                raise ValueError(f"Phase {phase} collector mismatch with phase 1")
            if req_dict["owners"] != first_request["owners"]:
                raise ValueError(f"Phase {phase} owners mismatch with phase 1")
            if req_dict["request_id"] == first_request["request_id"]:
                raise ValueError(
                    f"Phase {phase} request_id must be distinct from phase 1, got identical: {req_dict['request_id']}"
                )

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Timed out before boot_id query (pre-snapshot) for {phase}")
        boot_before = act_boot_id_fn(distro=distro, wsl_path=wsl_path, timeout_s=remaining)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Timed out before snapshot collection for {phase}")
        targets = {**req_dict["owners"], "collector": req_dict["collector"]}
        snapshot = act_snapshot_fn(
            local_ns_inode=req_dict["target_pid_ns"],
            owned_processes=targets,
            distro=distro,
            wsl_path=wsl_path,
            timeout_s=remaining,
        )

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Timed out before boot_id query (post-snapshot) for {phase}")
        boot_after = act_boot_id_fn(distro=distro, wsl_path=wsl_path, timeout_s=remaining)

        if boot_before != boot_after:
            raise RuntimeError(f"System boot_id changed during snapshot: {boot_before} != {boot_after}")
        if boot_before != req_dict["boot_id"]:
            raise RuntimeError(f"System boot_id mismatch: system={boot_before} != request={req_dict['boot_id']}")

        _verify_snapshot_targets(snapshot, req_dict)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Timed out before publishing response for {phase}")

        resp_dict = make_snapshot_response(
            request=req_dict, request_bytes=req_bytes, boot_id=boot_after, snapshot=snapshot
        )
        publish_create_only(resp_path, resp_dict)
        phases_handled.append(phase)

    return {
        "status": "ok",
        "exchange_dir": str(exchange_path),
        "phases_handled": phases_handled,
        "elapsed_s": time.monotonic() - start_mono,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for serving snapshot requests."""
    parser = argparse.ArgumentParser(description="Serve WSL snapshot requests from Windows host.")
    parser.add_argument("--exchange-dir", required=True, help="Path to local exchange directory.")
    parser.add_argument("--timeout", type=float, default=30.0, help="Total deadline timeout in seconds.")
    parser.add_argument("--distro", default=DEFAULT_DISTRO, help="WSL distribution name.")
    parser.add_argument("--wsl-path", default=None, help="Path to wsl.exe.")
    parser.add_argument("--poll-interval", type=float, default=0.05, help="Poll interval in seconds.")
    parser.add_argument("--max-request-bytes", type=int, default=MAX_REQUEST_BYTES, help="Max request bytes.")
    args = parser.parse_args(argv)
    try:
        res = serve_snapshot_requests(
            args.exchange_dir,
            timeout_s=args.timeout,
            distro=args.distro,
            wsl_path=args.wsl_path,
            poll_interval_s=args.poll_interval,
            max_request_bytes=args.max_request_bytes,
        )
        print(json.dumps(res, indent=2))
        return 0
    except Exception as err:
        sys.stderr.write(f"Snapshot server error: {err}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
