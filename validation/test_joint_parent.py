"""Tests for the Linux direct-parent liveness guard.

Linux-only behavior is exercised for real in WSL with short-lived own python
processes (no ROS/SITL/UE, no killing by name, no leftovers). A small real
microbenchmark compares one json_identity check against one getppid check on
the same live parent; it says nothing about flight.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

from Simulator.wksim_runtime import joint_parent
from Simulator.wksim_runtime.joint_parent import DirectParentGuard, FAILURE

LINUX = sys.platform == "linux"
REPO = Path(__file__).resolve().parents[1]


class MalformedIdentityTests(unittest.TestCase):
    @unittest.skipUnless(LINUX, "field validation runs on Linux")
    def test_strict_field_validation(self):
        for bad in (None, [], {}, {"pid": True, "pgid": 1, "start_ticks": 1},
                    {"pid": 0, "pgid": 1, "start_ticks": 1},
                    {"pid": 1, "pgid": "x", "start_ticks": 1},
                    {"pid": 1, "pgid": 1, "start_ticks": -1},
                    {"pid": 1, "pgid": 1}):
            with self.assertRaises((ValueError, TypeError), msg=str(bad)):
                DirectParentGuard(bad)

    @unittest.skipIf(LINUX, "Windows construction rejection")
    def test_non_linux_rejected(self):
        with self.assertRaises(OSError):
            DirectParentGuard({"pid": 1, "pgid": 1, "start_ticks": 1})


@unittest.skipUnless(LINUX, "Linux-only kernel parentage")
class GuardLinuxTests(unittest.TestCase):
    def parent_identity(self):
        from Simulator.wksim_runtime.evidence import json_identity
        return json_identity(os.getppid())

    def test_real_parent_accepted_and_calls_pass(self):
        guard = DirectParentGuard(self.parent_identity())
        for _ in range(100):
            guard()  # No caching: every call re-checks the kernel parentage.

    def test_initial_identity_mismatch_rejected(self):
        expected = self.parent_identity()
        for change in ({"start_ticks": expected["start_ticks"] + 1},
                       {"pgid": expected["pgid"] + 1}):
            with self.assertRaises(RuntimeError) as caught:
                DirectParentGuard(dict(expected, **change))
            self.assertEqual(str(caught.exception), FAILURE)

    def test_wrong_parent_pid_rejected(self):
        with self.assertRaises(RuntimeError) as caught:
            DirectParentGuard(dict(self.parent_identity(), pid=os.getppid() + 1))
        self.assertEqual(str(caught.exception), FAILURE)

    def test_startup_race_between_checks_rejected(self):
        expected = self.parent_identity()
        pid = expected["pid"]
        calls = iter([pid, pid + 1])  # first check ok, recheck sees reparent
        original = os.getppid
        joint_parent.os.getppid = lambda: next(calls, original())
        try:
            with self.assertRaises(RuntimeError):
                DirectParentGuard(expected)
        finally:
            joint_parent.os.getppid = original

    def test_call_after_reparent_fails(self):
        guard = DirectParentGuard(self.parent_identity())
        original = os.getppid
        joint_parent.os.getppid = lambda: 1  # reparented to init
        try:
            with self.assertRaises(RuntimeError) as caught:
                guard()
            self.assertEqual(str(caught.exception), FAILURE)
        finally:
            joint_parent.os.getppid = original

    def test_real_parent_exit_reparenting(self):
        """A short-lived intermediate process spawns the guarded grandchild,
        waits for its readiness, then exits; the guard must fail with the exact
        original message and the child must exit on its own."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            identity_file = tmp / "parent.json"
            child_script = tmp / "child.py"
            child_script.write_text(
                "import json, sys, time\n"
                "from pathlib import Path\n"
                "sys.path.insert(0, " + json.dumps(str(REPO)) + ")\n"
                "from Simulator.wksim_runtime.joint_parent import DirectParentGuard\n"
                "expected = json.loads(Path(sys.argv[1]).read_text())\n"
                "out = Path(sys.argv[2])\n"
                "guard = DirectParentGuard(expected)\n"
                "out.joinpath('ready').write_text('ready')\n"
                "deadline = time.monotonic() + 10\n"
                "while time.monotonic() < deadline:\n"
                "    try:\n"
                "        guard()\n"
                "        time.sleep(0.01)\n"
                "    except RuntimeError as error:\n"
                "        out.joinpath('failed').write_text(str(error))\n"
                "        break\n"
                "else:\n"
                "    out.joinpath('failed').write_text('guard never failed')\n",
                encoding="utf-8")
            parent_script = tmp / "parent.py"
            parent_script.write_text(
                "import json, os, subprocess, sys, time\n"
                "from pathlib import Path\n"
                "stat = Path('/proc/%d/stat' % os.getpid()).read_text().rsplit(')', 1)[1].split()\n"
                "identity = {'pid': os.getpid(), 'pgid': int(stat[2]),"
                " 'start_ticks': int(stat[19])}\n"
                "Path(sys.argv[1]).write_text(json.dumps(identity))\n"
                "child = subprocess.Popen([sys.executable, sys.argv[2], sys.argv[1], sys.argv[3]])\n"
                "Path(sys.argv[4]).write_text(str(child.pid))\n"
                "deadline = time.monotonic() + 10\n"
                "while time.monotonic() < deadline"
                " and not Path(sys.argv[3], 'ready').is_file():\n"
                "    time.sleep(0.02)\n"
                "sys.exit(0)\n",
                encoding="utf-8")
            child_pid_file = tmp / "child.pid"
            parent = subprocess.Popen([sys.executable, str(parent_script), str(identity_file),
                                       str(child_script), str(tmp), str(child_pid_file)])
            self.assertEqual(parent.wait(timeout=15), 0)  # Parent retires once child is ready.
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and not (tmp / "failed").is_file():
                time.sleep(0.05)
            self.assertTrue((tmp / "ready").is_file(), "guard was never constructed")
            self.assertTrue((tmp / "failed").is_file(), "guard never noticed the exit")
            self.assertEqual((tmp / "failed").read_text(), FAILURE)
            child_pid = int(child_pid_file.read_text())
            # Writing the failure marker precedes exit; allow the kernel/init
            # to complete exit and reap rather than racing that final write.
            from Simulator.wksim_runtime.evidence import json_identity
            deadline = time.monotonic()+2
            while time.monotonic()<deadline:
                live=json_identity(child_pid)
                if live is None or live['argv'] and str(child_script) not in live['argv']:
                    break
                time.sleep(.01)
            else:self.fail('guarded child leaked')

    @unittest.skipUnless(os.environ.get('WKSIM_PARENT_BENCHMARK')=='1', 'Explicit performance run only')
    def test_microbenchmark_json_identity_vs_getppid(self):
        """Real per-call costs on the same live parent; no flight claim."""
        from Simulator.wksim_runtime.evidence import json_identity
        import hashlib
        pid = os.getppid()
        samples = {"json_identity": [], "getppid": []}
        for _ in range(20000):
            start = time.perf_counter_ns()
            json_identity(pid)
            samples["json_identity"].append(time.perf_counter_ns() - start)
            start = time.perf_counter_ns()
            os.getppid()
            samples["getppid"].append(time.perf_counter_ns() - start)
        report = {"schema": "wksim.joint-parent-guard-benchmark.v1",
                  "samples_per_arm": 20000,
                  "median_ns": {k: sorted(v)[len(v) // 2] for k, v in samples.items()},
                  "source_sha256": hashlib.sha256(
                      Path(joint_parent.__file__).read_bytes()).hexdigest(),
                  "raw_samples_ns": samples,
                  "scope": "single-call cost on one live parent; no flight conclusion"}
        out = REPO / "validation/coordination" / (
            "joint-parent-guard-benchmark-" + uuid.uuid4().hex[:8] + ".json")
        with out.open("x", encoding="utf-8") as stream:
            json.dump(report, stream)
        print("guard benchmark:", out, report["median_ns"])
        self.assertGreater(report["median_ns"]["json_identity"],
                           report["median_ns"]["getppid"])


if __name__ == "__main__":
    unittest.main()
