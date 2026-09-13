#!/usr/bin/env python3
"""Minimal end-to-end smoke of capture+compare on real owned processes.

Targets ONLY:
- this verifier's own pid (role "verifier"), and
- one ordinary Python child it creates (role "spinner").

No SITL/native/ROS/model/UE/MATLAB process is started or touched, and no
scheduler state is modified. The capture modules are used in-process; the
only extra process is the one spinner child, which is terminated and reaped
at the end. Intended total runtime is a few seconds (< 10 s).

Safety of reruns (audited fix):
- ``--output-dir`` is REQUIRED and must not exist. It is created with a single
  atomic ``os.mkdir`` (exist_ok=False) BEFORE any child is spawned; an existing
  directory, file, symlink or a lost race is refused with exit code 3 and no
  process is started. All artifacts are written exclusively (mode "x") inside
  that fresh directory, so an existing smoke's raw files and result are never
  overwritten or touched.
- ``packaging`` is not used; this script never writes next to itself.

On this host /proc/sys/kernel/sched_schedstats is 0, so the comparison's
runqueue_ns/timeslices must be null (never 0) while the CPU run (run_ns)
delta is kept and non-negative. If the spinner dies or changes identity the
result is explicitly "not_comparable" — never reported as a valid comparison.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from tools.capture_owned_scheduling import OwnedSchedulingCapture
from tools.compare_owned_scheduling import SnapshotComparison

SPIN_SECONDS = 1.5
BURN_SECONDS = 0.8
REFUSED_EXIT = 3
NOT_COMPARABLE_EXIT = 2
CHILD_SOURCE = (
    "import signal,sys,time\n"
    "def stop(signum,frame):\n"
    "    sys.exit(0)\n"
    "signal.signal(signal.SIGTERM,stop)\n"
    "end=time.monotonic()+float(sys.argv[1])\n"
    "while time.monotonic()<end:\n"
    "    pass\n"
    "while True:\n"
    "    time.sleep(0.05)\n"
)


class Refused(RuntimeError):
    """The requested output directory is not a fresh, empty location."""


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _prepare_output_dir(path):
    """Atomically create a fresh output directory; refuse anything existing.

    Uses a single ``os.mkdir`` so there is no check-then-create race: a
    concurrent creation, an existing directory, a file or a symlink all fail
    before any child process is started.
    """
    path = Path(path)
    try:
        os.mkdir(path)
    except FileExistsError as error:
        raise Refused(f"output dir already exists: {path}") from error
    except OSError as error:
        raise Refused(f"cannot create output dir {path}: {error!r}") from error
    return path


def _write_exclusive(path, text):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(text)


def _stat_fields(pid):
    text = Path(f"/proc/{pid}/stat").read_text()
    return text.rsplit(")", 1)[1].split()


def identity(pid, argv):
    fields = _stat_fields(pid)
    return {"pid": pid, "pgid": int(fields[2]),
            "start_ticks": int(fields[19]), "argv": argv}


def _same_identity(before_doc, after_doc):
    roles = [role for role in ("verifier", "spinner")
             if role in before_doc.get("procs", {}) or role in after_doc.get("procs", {})]
    return bool(roles) and all(
        before_doc.get("procs", {}).get(role, {}).get("expected")
        == after_doc.get("procs", {}).get(role, {}).get("expected")
        for role in roles)


def evaluate(result, before_doc, after_doc, children, host_boot,
             host_schedstats, cleanup, children_sha):
    """Pure check builder; must never raise on a missing spinner/delta."""
    roles = result.get("roles", {})
    spinner = roles.get("spinner", {})
    verifier = roles.get("verifier", {})
    spinner_threads = spinner.get("compared_threads", [])
    verifier_threads = verifier.get("compared_threads", [])
    spinner_delta = spinner_threads[0]["delta"] if spinner_threads else None
    verifier_delta = verifier_threads[0]["delta"] if verifier_threads else None
    spinner_identity = children.get("spinner", {}).get("identity", {})

    checks = {}
    checks["bound"] = result.get("binding", {}).get("status") == "bound"
    checks["same_children_sha256"] = (
        result.get("before", {}).get("children_sha256")
        == result.get("after", {}).get("children_sha256") == children_sha)
    checks["same_boot_id"] = (
        result.get("before", {}).get("boot_id")
        == result.get("after", {}).get("boot_id") == host_boot)
    checks["same_identity_both_roles"] = _same_identity(before_doc, after_doc)
    checks["spinner_compared"] = spinner.get("status") == "compared" and bool(spinner_threads)
    checks["verifier_compared"] = verifier.get("status") == "compared" and bool(verifier_threads)
    checks["spinner_start_ticks_matches"] = bool(spinner_threads) and (
        spinner_threads[0].get("start_ticks") == spinner_identity.get("start_ticks"))
    checks["nonneg_cpu_run_delta"] = spinner_delta is not None and all(
        spinner_delta.get(name) is not None and spinner_delta.get(name) >= 0
        for name in ("utime_ticks", "stime_ticks", "run_ns"))
    checks["cpu_work_observed"] = (
        spinner_delta is not None and spinner_delta.get("run_ns", 0) > 0)
    if host_schedstats == "1":
        checks["wait_effective"] = (
            spinner_delta is not None and spinner_delta.get("runqueue_ns") is not None)
    else:
        checks["wait_counters_disabled_are_null"] = (
            spinner_delta is not None
            and spinner_delta.get("runqueue_ns") is None
            and spinner_delta.get("timeslices") is None)
        checks["wait_null_reason_recorded"] = bool(
            spinner_threads and spinner_threads[0]["delta_unavailable"].get("runqueue_ns"))
    checks["cleanup_ok"] = (bool(cleanup.get("reaped"))
                            and cleanup.get("returncode") in (0, -15))

    comparable = bool(checks["bound"] and checks["spinner_compared"]
                      and checks["verifier_compared"])
    if comparable:
        verdict = "pass" if all(checks.values()) else "fail"
    else:
        verdict = "not_comparable"
    return checks, comparable, verdict, spinner_delta, verifier_delta


def _run(output_dir):
    if sys.platform != "linux":
        raise SystemExit("this smoke must run on Linux (WSL); no native/process ops elsewhere")
    started = time.monotonic()
    host_boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    host_schedstats = Path("/proc/sys/kernel/sched_schedstats").read_text().strip()

    child = subprocess.Popen([sys.executable, "-c", CHILD_SOURCE, str(SPIN_SECONDS)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cleanup = {"child_pid": child.pid}
    try:
        children = {
            "verifier": {"identity": identity(os.getpid(), [sys.executable, "run_e2e.py"])},
            "spinner": {"identity": identity(child.pid,
                                             [sys.executable, "-c", "<spinner>",
                                              str(SPIN_SECONDS)])},
        }
        children_path = output_dir / "children-start.json"
        _write_exclusive(children_path, json.dumps(children, indent=2) + "\n")

        OwnedSchedulingCapture(children_path, output_dir / "owned-scheduling-before.json",
                               phase="before", clock_ticks=os.sysconf("SC_CLK_TCK")).capture()
        deadline = time.monotonic() + BURN_SECONDS
        while time.monotonic() < deadline:
            pass
        OwnedSchedulingCapture(children_path, output_dir / "owned-scheduling-after.json",
                               phase="after", clock_ticks=os.sysconf("SC_CLK_TCK")).capture()

        result = SnapshotComparison(output_dir / "owned-scheduling-before.json",
                                    output_dir / "owned-scheduling-after.json",
                                    output_dir / "owned-scheduling-delta.json").compare()
    finally:
        child.terminate()
        try:
            returncode = child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            returncode = child.wait()
        cleanup["returncode"] = returncode
        cleanup["reaped"] = True
        cleanup["controlled_termination"] = returncode == 0
        cleanup["note"] = ("SIGTERM exit code 0 is a controlled termination "
                           "handler, not a natural exit")

    before_doc = json.loads((output_dir / "owned-scheduling-before.json").read_text())
    after_doc = json.loads((output_dir / "owned-scheduling-after.json").read_text())
    checks, comparable, verdict, spinner_delta, verifier_delta = evaluate(
        result, before_doc, after_doc, children, host_boot, host_schedstats,
        cleanup, _sha256(children_path))

    report = {
        "schema": "wksim.owned-scheduling-e2e.v1",
        "verdict": verdict,
        "checks": checks,
        "host": {"kernel": os.uname().release, "boot_id": host_boot,
                 "sched_schedstats": host_schedstats,
                 "wsl_distro": os.environ.get("WSL_DISTRO_NAME")},
        "ownership": {"verifier_pid": os.getpid(), "spinner_pid": cleanup["child_pid"],
                      "targets": ["verifier", "spinner"],
                      "note": "only this verifier and its own child were sampled"},
        "spinner_delta": spinner_delta,
        "verifier_delta": verifier_delta,
        "cleanup": cleanup,
        "output_dir": str(output_dir),
        "durations_s": {"total": round(time.monotonic() - started, 3)},
        "source_sha256": {
            "capture": _sha256(ROOT / "tools" / "capture_owned_scheduling.py"),
            "compare": _sha256(ROOT / "tools" / "compare_owned_scheduling.py"),
            "run_e2e": _sha256(Path(__file__).resolve()),
        },
        "children_sha256": _sha256(children_path),
        "python": sys.version.split()[0],
        "unavailable_reason_if_any": None if comparable else result["binding"].get("reasons"),
    }
    _write_exclusive(output_dir / "result.json",
                     json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"verdict": verdict, "checks": checks, "cleanup": cleanup,
                      "output_dir": str(output_dir),
                      "total_s": report["durations_s"]["total"]}, sort_keys=True))
    if verdict == "pass":
        return 0
    return NOT_COMPARABLE_EXIT if verdict == "not_comparable" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="new, previously nonexistent directory for all artifacts")
    args = parser.parse_args(argv)
    try:
        output_dir = _prepare_output_dir(args.output_dir)
    except Refused as error:
        print(json.dumps({"verdict": "refused", "reason": str(error),
                          "output_dir": str(args.output_dir)}, sort_keys=True))
        return REFUSED_EXIT
    return _run(output_dir)


if __name__ == "__main__":
    sys.exit(main())
