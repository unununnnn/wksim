"""Read-only review tests for the deferred ArUco task-report change.

Exercises joint_evidence.task_group_completed / load_retired_task_report
directly with fake workers and real files. No ROS/simulation/build; the
implementation is not modified. Run:
    python -B -m unittest validation.test_deferred_report_review -v
"""
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from Simulator.wksim_runtime.joint_evidence import (
    task_group_completed, load_retired_task_report)


def worker(code):
    return SimpleNamespace(pid=1000 + code if code else 1000,
                           poll=lambda: code)


def report_file(tmp, name, **fields):
    path = Path(tmp) / name
    path.write_text(json.dumps(fields), encoding="utf-8")
    return path


IDENTITY = dict(run_id="run", scene_epoch="epoch", stack="arducopter")


class TaskGroupCompletedTests(unittest.TestCase):
    def test_unexited_or_failed_worker_is_never_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports = [report_file(tmp, "a.json", **IDENTITY, status="pass"),
                       report_file(tmp, "b.json", **IDENTITY, status="pass")]
            for workers in ([worker(None), worker(0)], [worker(1), worker(0)],
                            [worker(None), worker(None)]):
                self.assertFalse(task_group_completed(workers, reports, defer_report_reads=True))
                self.assertFalse(task_group_completed(workers, reports, defer_report_reads=False))

    def test_deferred_completion_uses_only_trusted_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = [Path(tmp) / "a.json", Path(tmp) / "b.json"]  # No files yet.
            self.assertTrue(task_group_completed([worker(0), worker(0)], missing,
                                                 defer_report_reads=True))
            self.assertFalse(task_group_completed([worker(0), worker(0)], missing,
                                                  defer_report_reads=False))

    def test_non_deferred_still_requires_pass_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            failed = report_file(tmp, "a.json", **IDENTITY, status="failed")
            passed = report_file(tmp, "b.json", **IDENTITY, status="pass")
            self.assertFalse(task_group_completed([worker(0), worker(0)], [failed, passed],
                                                  defer_report_reads=False))

    def test_single_worker_group_is_never_complete(self):
        self.assertFalse(task_group_completed([worker(0)], [], defer_report_reads=True))


class LoadRetiredReportTests(unittest.TestCase):
    def test_identity_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for change in ({"run_id": "other"}, {"scene_epoch": "other"}, {"stack": "px4"}):
                path = report_file(tmp, "r.json", **dict(IDENTITY, **change), status="pass")
                with self.assertRaises(ValueError, msg=change):
                    load_retired_task_report(path, "run", "epoch", "arducopter", 0)

    def test_exit_zero_requires_pass_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            for status in ("failed", "stopped", None):
                path = report_file(tmp, "r.json", **IDENTITY, status=status)
                with self.assertRaises(ValueError, msg=str(status)):
                    load_retired_task_report(path, "run", "epoch", "arducopter", 0)

    def test_pass_report_with_clean_exit_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = report_file(tmp, "r.json", **IDENTITY, status="pass")
            report = load_retired_task_report(path, "run", "epoch", "arducopter", 0)
            self.assertEqual(report["status"], "pass")

    def test_failed_worker_with_pass_report_is_rejected(self):
        """A completed-looking file cannot override a failed worker exit."""
        with tempfile.TemporaryDirectory() as tmp:
            path = report_file(tmp, "r.json", **IDENTITY, status="pass")
            with self.assertRaises(ValueError):
                load_retired_task_report(path, "run", "epoch", "arducopter", 1)

    def test_failed_worker_with_failed_report_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = report_file(tmp, "r.json", **IDENTITY, status="failed")
            report = load_retired_task_report(path, "run", "epoch", "arducopter", 1)
            self.assertEqual(report["status"], "failed")

    def test_corrupt_report_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_retired_task_report(path, "run", "epoch", "arducopter", 0)


if __name__ == "__main__":
    unittest.main()
