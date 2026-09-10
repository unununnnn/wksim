"""Offline tests for tools/sample_joint_threads.py (v2 review fixes).

Synthetic proc root + identity stubs; one WSL smoke with a self-created
short-lived python process (exits in finally; no SITL/ROS/build). Run:
    python -B -m unittest validation.test_joint_thread_sampler -v
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.sample_joint_threads import ThreadSampler

LINUX = sys.platform == "linux"
EPOCH = "ab" * 16


def fake_stat_line(pid, pgid, start_ticks, state="S"):
    fields = [state, "1", str(pgid), str(pgid)] + ["0"] * 15
    return f"{pid} (fake) {' '.join(fields)} {start_ticks} 0 0"


def fake_proc(root, pid, pgid, start_ticks, threads=(1, 2)):
    proc = Path(root) / str(pid)
    (proc / "task").mkdir(parents=True)
    (proc / "stat").write_text(fake_stat_line(pid, pgid, start_ticks))
    for tid in threads:
        task = proc / "task" / str(tid)
        task.mkdir(parents=True)
        task.joinpath("stat").write_text(fake_stat_line(pid, pgid, start_ticks))
        task.joinpath("schedstat").write_text("1000 200 3")
    return proc


def fake_run(root, *, run_id="run", epoch=EPOCH):
    run = Path(root) / "run"
    epoch_dir = run / "epochs" / epoch
    epoch_dir.mkdir(parents=True)
    (run / "config.json").write_text(json.dumps({"run_id": run_id}))
    (run / "status.json").write_text(json.dumps(
        {"run_id": run_id, "epoch": epoch,
         "supervisor": {"pid": 100, "pgid": 100, "start_ticks": 7, "argv": ["sv", str(epoch_dir)]}}))
    (epoch_dir / "children.json").write_text(json.dumps({
        "arducopter-fc": {"identity": {"pid": 200, "pgid": 100, "start_ticks": 9,
                                       "argv": ["fc", str(epoch_dir)]}},
        "arducopter-model": {"identity": {"pid": 201, "pgid": 100, "start_ticks": 10,
                                          "argv": ["model", str(epoch_dir)]}},
        "px4-model": {"identity": {"pid": 202, "pgid": 100, "start_ticks": 11,
                                   "argv": ["model", str(epoch_dir)]}},
    }))
    return run


class SamplerTests(unittest.TestCase):
    def make(self, tmp, *, bad_switch=None, **kwargs):
        proc = Path(tmp) / "proc"
        proc.mkdir()
        for pid, ticks in ((100, 7), (200, 9), (201, 10), (202, 11)):
            fake_proc(proc, pid, 100, ticks)
        run = fake_run(tmp)
        identities = {pid: {"pid": pid, "pgid": 100, "start_ticks": ticks,
                            "argv": argv}
                      for (pid, ticks), argv in zip(
                          ((100, 7), (200, 9), (201, 10), (202, 11)),
                          (["sv", str(run / "epochs" / EPOCH)],
                           ["fc", str(run / "epochs" / EPOCH)],
                           ["model", str(run / "epochs" / EPOCH)],
                           ["model", str(run / "epochs" / EPOCH)]))}
        switch = Path(tmp) / "sched_schedstats"
        switch.write_text(bad_switch or "1")
        return run, ThreadSampler(run, Path(tmp) / "out", proc_root=proc,
                                  identity=identities.get, schedstat_switch=switch,
                                  duration_s=0.2, **kwargs)

    def test_happy_path_keeps_tid_identity_and_run_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, sampler = self.make(tmp)
            result = sampler.sample()
            self.assertEqual(result["status"], "sampled")
            self.assertEqual(result["run_id"], "run")
            self.assertEqual(result["epoch"], EPOCH)
            self.assertTrue(result["runqueue_counters_valid"])
            lines = (Path(tmp) / "out" / "samples.jsonl").read_text().splitlines()
            kinds = [json.loads(l)["kind"] for l in lines]
            self.assertEqual(kinds[0], "header")
            self.assertEqual(kinds[-1], "close")
            sample = next(json.loads(l) for l in lines if json.loads(l)["kind"] == "sample")
            self.assertEqual(sample["run_id"], "run")
            thread = sample["threads"][0]
            self.assertIn("start_ticks", thread)  # Per-TID identity retained.
            self.assertIn("runqueue_ns", thread)  # Runnable-wait, not all off-CPU.
            close = json.loads(lines[-1])
            self.assertIn("sampler_thread_cpu_ns", close)

    def test_schedstats_disabled_is_recorded_not_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, sampler = self.make(tmp, bad_switch="0")
            result = sampler.sample()
            self.assertEqual(result["sched_schedstats_original"], "0")
            self.assertFalse(result["runqueue_counters_valid"])

    def test_status_epoch_or_run_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = fake_run(tmp)
            status = json.loads((run / "status.json").read_text())
            status["epoch"] = "cd" * 16
            (run / "status.json").write_text(json.dumps(status))
            proc = Path(tmp) / "proc"
            proc.mkdir()
            sampler = ThreadSampler(run, Path(tmp) / "out", proc_root=proc,
                                    identity=lambda pid: None, duration_s=0.1)
            result = sampler.sample()  # Failures are recorded, not raised.
            self.assertEqual(result["status"], "failed")
            self.assertIn("epoch differs", result["error"])

    def test_argv_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, sampler = self.make(tmp)
            sampler.identity = lambda pid: {"pid": pid, "pgid": 100, "start_ticks": 7,
                                            "argv": ["different", "argv"]}
            result = sampler.sample()
            self.assertEqual(result["status"], "failed")
            self.assertIn("argv differs", result["error"])

    def test_pid_identity_change_mid_run_retires_without_following(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, sampler = self.make(tmp)
            original = self.make.__globals__["fake_proc"]
            # Rewrite pid 200's start_ticks: the process was replaced.
            (sampler.proc_root / "200" / "stat").write_text(
                fake_stat_line(200, 100, 999))
            result = sampler.sample()
            self.assertEqual(result["status"], "sampled")
            lines = (Path(tmp) / "out" / "samples.jsonl").read_text().splitlines()
            retired = [json.loads(l) for l in lines if json.loads(l)["kind"] == "target_retired"]
            self.assertTrue(any(r["target"] == "arducopter-fc" for r in retired))
            for line in lines:
                row = json.loads(line)
                if row["kind"] == "sample":
                    self.assertFalse(any(t["target"] == "arducopter-fc"
                                         for t in row["threads"]))

    def test_parameter_bounds_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, _ = self.make(tmp)
            for bad in ({"rate_hz": 0}, {"rate_hz": True}, {"rate_hz": 100.5},
                        {"rate_hz": 1001}, {"duration_s": 0}, {"duration_s": 41},
                        {"duration_s": float("inf")}, {"duration_s": float("nan")},
                        {"duration_s": True}):
                with self.assertRaises(ValueError, msg=str(bad)):
                    ThreadSampler(run, Path(tmp) / "out2", proc_root=Path(tmp) / "proc",
                                  identity=lambda pid: None, **bad)

    def test_existing_output_dir_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, sampler = self.make(tmp)
            (Path(tmp) / "out").mkdir()
            with self.assertRaises(FileExistsError):
                sampler.sample()


@unittest.skipUnless(LINUX, "WSL smoke with own short-lived process")
class LiveSmokeTests(unittest.TestCase):
    def test_real_process_sampled_and_retired_cleanly(self):
        from Simulator.wksim_runtime.evidence import json_identity
        with tempfile.TemporaryDirectory() as tmp:
            child = subprocess.Popen([sys.executable, "-c",
                                      "import time; time.sleep(1.0)"])
            try:
                identity = json_identity(child.pid)
                run = Path(tmp) / "run"
                epoch_dir = run / "epochs" / EPOCH
                epoch_dir.mkdir(parents=True)
                (run / "config.json").write_text(json.dumps({"run_id": "run"}))
                (run / "status.json").write_text(json.dumps(
                    {"run_id": "run", "epoch": EPOCH, "supervisor": identity}))
                (epoch_dir / "children.json").write_text(json.dumps({}))
                sampler = ThreadSampler(run, Path(tmp) / "out", targets=["supervisor"],
                                        duration_s=2.0)
                result = sampler.sample()
                self.assertEqual(result["status"], "sampled")
                self.assertEqual(result["stop_reason"], "all targets retired")
                self.assertGreater(result["samples"], 0)
            finally:
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.terminate()
                    child.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
