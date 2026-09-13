"""Independent review tests for the main session's sample_joint_threads fixes.

Definitions only — the main session calls them after integrating its fixes
(zombie retirement, epoch-entry level, busy-thread row retention, batch
timing). They pin the intended contract, not the current broken behavior:

1. A busy thread whose utime/state counters change between the two reads of
   one sample is KEPT (only identity fields gate retention).
2. A changed start_ticks drops the thread/batch (identity change).
3. A zombie (state Z) PID retires immediately, with a target_retired record.
4. An epoch directory passed as --run resolves status.json/config.json at the
   run root and carries run_id/epoch in header and samples.
5. The thread-row cap fails explicitly; an empty target set never reports
   "sampled" success.

No real sampling, no SITL, no build. Deterministic fake proc trees; the
counter-mutation case monkeypatches the module's _stat_fields to flip utime
between the two reads of the same row.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

import tools.sample_joint_threads as sampler_module
from tools.sample_joint_threads import ThreadSampler

EPOCH = "ab" * 16


def fake_stat_line(pid, pgid, start_ticks, state="S", utime=0):
    fields = [state, "1", str(pgid), str(pgid)] + ["0"] * 15
    return f"{pid} (fake) {' '.join(fields)} {start_ticks} 0 0"


def fake_proc(root, pid, pgid, start_ticks, state="S", threads=(1, 2)):
    proc = Path(root) / str(pid)
    (proc / "task").mkdir(parents=True)
    (proc / "stat").write_text(fake_stat_line(pid, pgid, start_ticks, state))
    for tid in threads:
        task = proc / "task" / str(tid)
        task.mkdir(parents=True)
        task.joinpath("stat").write_text(fake_stat_line(pid, pgid, start_ticks, state))
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
    }))
    return run


def identities_for(run):
    epoch_dir = run / "epochs" / EPOCH
    return {100: {"pid": 100, "pgid": 100, "start_ticks": 7, "argv": ["sv", str(epoch_dir)]},
            200: {"pid": 200, "pgid": 100, "start_ticks": 9, "argv": ["fc", str(epoch_dir)]}}


class ReviewTests(unittest.TestCase):
    def make(self, tmp, *, targets=("supervisor", "arducopter-fc"), patches=None, **kwargs):
        proc = Path(tmp) / "proc"
        proc.mkdir()
        fake_proc(proc, 100, 100, 7)
        fake_proc(proc, 200, 100, 9)
        run = fake_run(tmp)
        switch = Path(tmp) / "sched_schedstats"
        switch.write_text("1")
        sampler = ThreadSampler(run, Path(tmp) / "out", proc_root=proc,
                                identity=identities_for(run).get,
                                schedstat_switch=switch, duration_s=0.2,
                                targets=list(targets), **kwargs)
        return run, sampler

    def rows(self, tmp):
        return [json.loads(l) for l in
                (Path(tmp) / "out" / "samples.jsonl").read_text().splitlines()]

    def test_busy_thread_counter_change_is_kept(self):
        """A thread legitimately burning CPU between the two stat reads of one
        row must be sampled, not dropped: only identity fields may gate."""
        with tempfile.TemporaryDirectory() as tmp:
            run, sampler = self.make(tmp)
            real = sampler_module._stat_fields
            calls = {"n": 0}

            def busy(root, pid, tid=None):
                row = real(root, pid, tid)
                if tid is not None:  # Thread rows: counters advance on re-read.
                    calls["n"] += 1
                    if calls["n"] % 2 == 0:
                        row = dict(row, utime_ticks=row["utime_ticks"] + 1)
                return row

            sampler_module._stat_fields = busy
            try:
                result = sampler.sample()
            finally:
                sampler_module._stat_fields = real
            self.assertEqual(result["status"], "sampled")
            sampled = [r for line in self.rows(tmp) if line["kind"] == "sample"
                       for r in line["threads"]]
            self.assertTrue(sampled, "busy-thread rows were dropped")

    def test_start_ticks_change_drops_and_retires(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, sampler = self.make(tmp)
            # PID 200 replaced: its start_ticks no longer match the identity.
            (sampler.proc_root / "200" / "stat").write_text(
                fake_stat_line(200, 100, 999))
            result = sampler.sample()
            lines = self.rows(tmp)
            retired = [r for r in lines if r["kind"] == "target_retired"]
            self.assertTrue(any(r["target"] == "arducopter-fc" for r in retired))
            for line in lines:
                if line["kind"] == "sample":
                    self.assertFalse(any(t["target"] == "arducopter-fc"
                                         for t in line["threads"]))

    def test_zombie_process_retires_immediately(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, sampler = self.make(tmp)
            (sampler.proc_root / "200" / "stat").write_text(
                fake_stat_line(200, 100, 9, state="Z"))
            result = sampler.sample()
            retired = [r for r in self.rows(tmp) if r["kind"] == "target_retired"]
            self.assertTrue(any(r["target"] == "arducopter-fc" for r in retired),
                            "a zombie must retire at once, not be sampled as live")

    def test_epoch_directory_entry_resolves_run_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, _ = self.make(tmp)
            proc = Path(tmp) / "proc"
            epoch_dir = run / "epochs" / EPOCH
            sampler = ThreadSampler(epoch_dir, Path(tmp) / "out2", proc_root=proc,
                                    identity=identities_for(run).get,
                                    schedstat_switch=Path(tmp) / "sched_schedstats",
                                    duration_s=0.1,targets=['supervisor','arducopter-fc'])
            result = sampler.sample()
            self.assertEqual(result["status"], "sampled")
            self.assertEqual(result["run_id"], "run")
            self.assertEqual(result["epoch"], EPOCH)
            header = json.loads((Path(tmp) / "out2" / "samples.jsonl")
                                .read_text().splitlines()[0])
            self.assertEqual(header["run_id"], "run")
            self.assertEqual(header["epoch"], EPOCH)

    def test_thread_row_cap_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, sampler = self.make(tmp)
            original = sampler_module.MAX_THREAD_ROWS
            sampler_module.MAX_THREAD_ROWS = 1
            try:
                result = sampler.sample()
            finally:
                sampler_module.MAX_THREAD_ROWS = original
            self.assertEqual(result["status"], "failed")
            self.assertIn("row cap", result["error"])

    def test_empty_target_set_is_not_a_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'nonempty'):
                self.make(tmp, targets=[])


if __name__ == "__main__":
    unittest.main()
