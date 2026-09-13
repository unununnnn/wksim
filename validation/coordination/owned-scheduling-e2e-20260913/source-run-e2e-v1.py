#!/usr/bin/env python3
"""Minimal end-to-end smoke of capture+compare on real owned processes.

Targets ONLY:
- this verifier's own pid (role "verifier"), and
- one ordinary Python child it creates (role "spinner").

No SITL/native/ROS/model/UE/MATLAB process is started or touched, and no
scheduler state is modified. The capture modules are used in-process; the
only extra process is the one spinner child, which is terminated and reaped
at the end. Intended total runtime is a few seconds (< 10 s).

On this host /proc/sys/kernel/sched_schedstats is 0, so the comparison's
runqueue_ns/timeslices must be null (never 0) while the CPU run (run_ns)
delta is kept and non-negative. If the spinner dies or changes identity the
result is explicitly "not_comparable" — never reported as a valid comparison.
"""
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


def _stat_fields(pid):
    text = Path(f"/proc/{pid}/stat").read_text()
    return text.rsplit(")", 1)[1].split()


def identity(pid, argv):
    fields = _stat_fields(pid)
    return {"pid": pid, "pgid": int(fields[2]),
            "start_ticks": int(fields[19]), "argv": argv}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run():
    if sys.platform != "linux":
        raise SystemExit("this smoke must run on Linux (WSL); no native/process ops elsewhere")
    started = time.monotonic()
    host_boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    host_schedstats = Path("/proc/sys/kernel/sched_schedstats").read_text().strip()

    child = subprocess.Popen([sys.executable, "-c", CHILD_SOURCE, str(SPIN_SECONDS)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    child_argv = [sys.executable, "-c", "<spinner>", str(SPIN_SECONDS)]
    children_path = HERE / "children-start.json"
    checks = {}
    cleanup = {"child_pid": child.pid}
    try:
        children = {
            "verifier": {"identity": identity(os.getpid(), [sys.executable, "run_e2e.py"])},
            "spinner": {"identity": identity(child.pid, child_argv)},
        }
        children_path.write_text(json.dumps(children, indent=2) + "\n",
                                 encoding="utf-8")

        OwnedSchedulingCapture(children_path, HERE / "owned-scheduling-before.json",
                               phase="before", clock_ticks=os.sysconf("SC_CLK_TCK")).capture()
        # Bounded CPU work in the verifier while the spinner also burns CPU.
        deadline = time.monotonic() + BURN_SECONDS
        while time.monotonic() < deadline:
            pass
        OwnedSchedulingCapture(children_path, HERE / "owned-scheduling-after.json",
                               phase="after", clock_ticks=os.sysconf("SC_CLK_TCK")).capture()

        result = SnapshotComparison(HERE / "owned-scheduling-before.json",
                                    HERE / "owned-scheduling-after.json",
                                    HERE / "owned-scheduling-delta.json").compare()
    finally:
        child.terminate()
        try:
            returncode = child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            returncode = child.wait()
        cleanup["returncode"] = returncode
        cleanup["reaped"] = True
        cleanup["normal_exit"] = returncode == 0

    before_doc = json.loads((HERE / "owned-scheduling-before.json").read_text())
    after_doc = json.loads((HERE / "owned-scheduling-after.json").read_text())
    roles = result.get("roles", {})
    spinner = roles.get("spinner", {})
    verifier = roles.get("verifier", {})
    spinner_threads = spinner.get("compared_threads", [])
    verifier_threads = verifier.get("compared_threads", [])

    def _delta(rows):
        return rows[0]["delta"] if rows else None

    spinner_delta = _delta(spinner_threads)
    verifier_delta = _delta(verifier_threads)

    checks["bound"] = result["binding"]["status"] == "bound"
    checks["same_children_sha256"] = (
        result["before"]["children_sha256"] == result["after"]["children_sha256"]
        == _sha256(children_path))
    checks["same_boot_id"] = (
        result["before"]["boot_id"] == result["after"]["boot_id"] == host_boot)
    checks["same_identity_both_roles"] = all(
        before_doc["procs"][role]["expected"] == after_doc["procs"][role]["expected"]
        for role in ("verifier", "spinner") if role in before_doc["procs"])
    checks["spinner_compared"] = spinner.get("status") == "compared" and bool(spinner_threads)
    checks["verifier_compared"] = verifier.get("status") == "compared" and bool(verifier_threads)
    checks["spinner_start_ticks_matches"] = bool(spinner_threads) and (
        spinner_threads[0]["start_ticks"] == children["spinner"]["identity"]["start_ticks"])
    checks["nonneg_cpu_run_delta"] = spinner_delta is not None and all(
        spinner_delta.get(name) is not None and spinner_delta.get(name) >= 0
        for name in ("utime_ticks", "stime_ticks", "run_ns"))
    checks["cpu_work_observed"] = spinner_delta is not None and spinner_delta.get("run_ns", 0) > 0
    if host_schedstats == "1":
        checks["wait_effective"] = spinner_delta.get("runqueue_ns") is not None
    else:
        checks["wait_counters_disabled_are_null"] = (
            spinner_delta is not None
            and spinner_delta.get("runqueue_ns") is None
            and spinner_delta.get("timeslices") is None)
        checks["wait_null_reason_recorded"] = bool(
            spinner_threads and spinner_threads[0]["delta_unavailable"].get("runqueue_ns"))

    comparable = checks["bound"] and checks["spinner_compared"] and checks["verifier_compared"]
    if comparable:
        verdict = "pass" if all(checks.values()) else "fail"
    else:
        verdict = "not_comparable"

    report = {
        "schema": "wksim.owned-scheduling-e2e.v1",
        "verdict": verdict,
        "checks": checks,
        "host": {"kernel": os.uname().release, "boot_id": host_boot,
                 "sched_schedstats": host_schedstats,
                 "wsl_distro": os.environ.get("WSL_DISTRO_NAME")},
        "ownership": {
            "verifier_pid": os.getpid(),
            "spinner_pid": cleanup["child_pid"],
            "targets": ["verifier", "spinner"],
            "note": "only this verifier and its own child were sampled",
        },
        "spinner_delta": spinner_delta,
        "verifier_delta": verifier_delta,
        "spinner_delta_unavailable": spinner_threads[0]["delta_unavailable"]
        if spinner_threads else None,
        "cleanup": cleanup,
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
    (HERE / "result.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                                      encoding="utf-8")
    print(json.dumps({"verdict": verdict, "checks": checks,
                      "spinner_delta": spinner_delta,
                      "cleanup": cleanup,
                      "total_s": report["durations_s"]["total"]}, sort_keys=True))
    return 0 if verdict == "pass" else (2 if verdict == "not_comparable" else 1)


if __name__ == "__main__":
    sys.exit(run())
