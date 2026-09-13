"""Tests for AsyncEvidenceStream through its public interface.

Interface facts verified here: write(str) returns the CHARACTER count while
summary() accounts UTF-8 bytes; single producer; close has one monotonic
deadline; only the background thread closes the fd; failures never become
completion. Deterministic via the internal _writer/_opener/_closer seam
(events, no random sleeps); no ROS/simulation, no compilation.
"""
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest

from Simulator.wksim_runtime.evidence_stream import (
    AsyncEvidenceStream, EvidenceStreamError)


def write_file(tmp, records, **kwargs):
    path = Path(tmp) / "evidence.jsonl"
    with AsyncEvidenceStream(path, **kwargs) as stream:
        for record in records:
            stream.write(record)
    return path


def wait_for(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.005)
    return predicate()


class StreamTests(unittest.TestCase):
    def test_writer_enters_ordinary_scheduler_before_first_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            scheduled = threading.Event()

            def scheduler():
                scheduled.set()
                return dict(available=True, policy="SCHED_OTHER", priority=0,
                            actual_policy=0, actual_priority=0)

            def writer(fd, view):
                self.assertTrue(scheduled.is_set())
                return os.write(fd, view)

            path = Path(tmp) / "e.jsonl"
            with AsyncEvidenceStream(path, block_size=4, _scheduler=scheduler,
                                     _writer=writer) as stream:
                stream.write("data")
            self.assertEqual(stream.summary()["writer_scheduler"]["policy"], "SCHED_OTHER")

    def test_writer_scheduler_failure_is_latched_before_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            writes = []

            def scheduler():
                raise OSError("scheduler demotion failed")

            def writer(fd, view):
                writes.append(bytes(view))
                return os.write(fd, view)

            with self.assertRaisesRegex(OSError, "scheduler demotion failed"):
                AsyncEvidenceStream(Path(tmp) / "e.jsonl", block_size=4,
                                    _scheduler=scheduler, _writer=writer)
            self.assertEqual(writes, [])

    def test_writer_scheduler_setup_has_close_timeout_bound(self):
        release = threading.Event()
        closed = threading.Event()

        def scheduler():
            release.wait(5)
            return dict(available=True, policy="SCHED_OTHER", priority=0,
                        actual_policy=0, actual_priority=0)

        started = time.monotonic()
        try:
            with self.assertRaisesRegex(EvidenceStreamError, "scheduler setup timed out"):
                AsyncEvidenceStream("unused", close_timeout=.05, _scheduler=scheduler,
                                    _opener=lambda *_: 17,
                                    _closer=lambda _fd: closed.set())
        finally:
            release.set()
        self.assertLess(time.monotonic() - started, 1)
        self.assertTrue(closed.wait(1))

    def test_bytes_and_order_exactly_preserved_across_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = ["plain ascii\n", "中文与 é 混合 ✓\n", '{"a": 1}\n', "", "x" * 100]
            path = write_file(tmp, records)
            self.assertEqual(path.read_bytes(), "".join(records).encode("utf-8"))

    def test_write_returns_characters_summary_counts_utf8_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "e.jsonl"
            stream = AsyncEvidenceStream(path, block_size=16, queue_blocks=2)
            self.assertEqual(stream.write("中文\n"), 3)   # Characters, not bytes.
            self.assertEqual(stream.write("ab\n"), 3)
            stream.check()
            stream.close()
            summary = stream.summary()
            self.assertTrue(summary["complete"])
            self.assertEqual(summary["submitted_bytes"], 10)  # UTF-8 bytes.
            self.assertEqual(summary["written_bytes"], 10)
            self.assertFalse(summary["alive"])
            self.assertTrue(summary["closed"])
            self.assertIsNone(summary["error"])
            self.assertGreaterEqual(summary["queue_highwater"], 1)
            self.assertGreaterEqual(summary["io_calls"], 1)
            self.assertGreaterEqual(summary["max_io_wall_ns"], 0)
            self.assertEqual(path.read_bytes(), "中文\nab\n".encode("utf-8"))

    def test_partial_writes_are_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "e.jsonl"
            real_write = os.write
            calls = []

            def partial(fd, view):
                count = max(1, len(view) // 3)  # Never complete a block at once.
                calls.append(count)
                return real_write(fd, bytes(view[:count]))

            with AsyncEvidenceStream(path, block_size=8, queue_blocks=4,
                                     _writer=partial) as stream:
                stream.write("0123456789ABCDEF中文\n")
            self.assertGreater(len(calls), 2)
            self.assertEqual(path.read_bytes(), "0123456789ABCDEF中文\n".encode("utf-8"))

    def test_background_io_error_surfaces_at_next_contact(self):
        with tempfile.TemporaryDirectory() as tmp:
            release = threading.Event()

            def broken(fd, view):
                release.wait(5)
                raise OSError("simulated disk failure")

            stream = AsyncEvidenceStream(Path(tmp) / "e.jsonl", block_size=4,
                                         queue_blocks=2, _writer=broken)
            stream.write("abcd")  # Fills one block; background write will fail.
            release.set()
            self.assertTrue(wait_for(lambda: not stream.summary()["alive"]))
            with self.assertRaises(OSError):
                stream.check()
            with self.assertRaises(OSError):
                stream.close()
            summary = stream.summary()
            self.assertFalse(summary["complete"])
            self.assertIn("simulated disk failure", summary["error"])

    def test_partial_bytes_before_io_error_are_accounted(self):
        with tempfile.TemporaryDirectory() as tmp:
            attempts = []

            def partial_then_broken(fd, view):
                if not attempts:
                    attempts.append(True)
                    return os.write(fd, bytes(view[:3]))  # Exactly 3 bytes land.
                raise OSError("disk failed mid-record")

            stream = AsyncEvidenceStream(Path(tmp) / "e.jsonl", block_size=10,
                                         queue_blocks=2, _writer=partial_then_broken)
            stream.write("0123456789")  # 10 bytes in one block.
            self.assertTrue(wait_for(lambda: not stream.summary()["alive"]))
            with self.assertRaises(OSError):
                stream.close()
            summary = stream.summary()
            self.assertEqual(summary["written_bytes"], 3)
            self.assertEqual(summary["submitted_bytes"], 10)
            self.assertFalse(summary["complete"])

    def test_full_queue_fails_without_blocking_and_stays_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            gate = threading.Event()

            def blocked(fd, view):
                gate.wait(5)
                return os.write(fd, view)

            stream = AsyncEvidenceStream(Path(tmp) / "e.jsonl", block_size=4,
                                         queue_blocks=1, _writer=blocked)
            stream.write("abcd")  # One block queued; writer holds it.
            start = time.monotonic()
            with self.assertRaises(EvidenceStreamError):
                stream.write("efgh")  # Queue full: immediate, non-blocking failure.
            self.assertLess(time.monotonic() - start, 1)
            gate.set()
            with self.assertRaises(EvidenceStreamError):
                stream.check()  # Permanently failed.
            with self.assertRaises(EvidenceStreamError):
                stream.close()
            with self.assertRaises(EvidenceStreamError):
                stream.check()
            self.assertFalse(stream.summary()["complete"])

    def test_close_waits_bounded_for_tail_and_completes_after_release(self):
        """Queue momentarily busy and writer blocked when close starts; the tail
        is released during close and everything finishes — no false failure."""
        with tempfile.TemporaryDirectory() as tmp:
            entered = threading.Event()
            release = threading.Event()
            real_write = os.write

            def gated(fd, view):
                entered.set()
                release.wait(5)
                return real_write(fd, view)

            stream = AsyncEvidenceStream(Path(tmp) / "e.jsonl", block_size=4,
                                         queue_blocks=1, close_timeout=5,
                                         _writer=gated)
            stream.write("abcd")          # One block; writer takes and holds it.
            self.assertTrue(entered.wait(5))
            stream.write("ef")            # Accepted tail stays pending.
            outcome = {}

            def closer():
                try:
                    stream.close()
                    outcome["ok"] = True
                except BaseException as error:
                    outcome["error"] = error

            thread = threading.Thread(target=closer)
            thread.start()
            time.sleep(0.1)               # Close is now bounded-waiting on the writer.
            release.set()
            thread.join(10)
            self.assertTrue(outcome.get("ok"), outcome)
            summary = stream.summary()
            self.assertTrue(summary["complete"])
            self.assertEqual(summary["written_bytes"], 6)
            self.assertEqual((Path(tmp) / "e.jsonl").read_bytes(), b"abcdef")

    def test_close_timeout_stays_latched_after_late_writer_retirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            gate = threading.Event()

            def stuck(fd, view):
                gate.wait(30)
                return os.write(fd, view)

            stream = AsyncEvidenceStream(Path(tmp) / "e.jsonl", block_size=4,
                                         queue_blocks=2, close_timeout=0.3,
                                         _writer=stuck)
            stream.write("abcd")
            start = time.monotonic()
            with self.assertRaises(EvidenceStreamError):
                stream.close()
            self.assertLess(time.monotonic() - start, 5)
            gate.set()  # The daemon can now retire; the process never waited on it.
            self.assertTrue(wait_for(lambda: not stream.summary()["alive"]))
            with self.assertRaises(EvidenceStreamError):
                stream.close()  # Failure remains latched.
            self.assertFalse(stream.summary()["complete"])

    def test_closer_error_after_real_fd_close_cannot_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            real_close = os.close

            def closing_then_broken(fd):
                real_close(fd)  # The fd really is closed.
                raise OSError("close failed")

            stream = AsyncEvidenceStream(Path(tmp) / "e.jsonl", block_size=4,
                                         queue_blocks=2, _closer=closing_then_broken)
            stream.write("abcd")
            with self.assertRaises(OSError):
                stream.close()  # The closer ran, really closed the fd, then failed.
            self.assertFalse(stream.summary()["alive"])
            summary = stream.summary()
            self.assertFalse(summary["complete"])
            self.assertIn("close failed", summary["error"])

    def test_oversized_single_write_fails_at_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            stream = AsyncEvidenceStream(Path(tmp) / "e.jsonl", block_size=8, queue_blocks=2)
            with self.assertRaises(EvidenceStreamError):
                stream.write("x" * 17)  # Capacity is 16 bytes.
            with self.assertRaises(EvidenceStreamError):
                stream.check()
            with self.assertRaises(EvidenceStreamError):
                stream.close()  # Bounded close releases the fd for cleanup.

    def test_close_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_file(tmp, ["a\n"])
            stream = AsyncEvidenceStream(Path(tmp) / "b.jsonl")
            stream.write("b\n")
            stream.close()
            stream.close()  # Second close: same latched success, no error.
            self.assertTrue(stream.summary()["complete"])

    def test_existing_original_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "e.jsonl"
            path.write_text("original evidence", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                AsyncEvidenceStream(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "original evidence")

    def test_write_after_close_and_bad_types_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            stream = AsyncEvidenceStream(Path(tmp) / "e.jsonl")
            stream.close()
            with self.assertRaises(ValueError):
                stream.write("late")
        with tempfile.TemporaryDirectory() as tmp:
            stream = AsyncEvidenceStream(Path(tmp) / "e.jsonl")
            with self.assertRaises(TypeError):
                stream.write(b"bytes are not accepted")
            with self.assertRaises(UnicodeEncodeError):
                stream.write("lone surrogate \ud800")
            stream.close()
            self.assertTrue(stream.summary()["complete"])

    def test_parameter_validation_rejects_nonfinite_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            for bad in ({"block_size": 0}, {"block_size": True}, {"queue_blocks": 0},
                        {"queue_blocks": 1.5}, {"close_timeout": -1},
                        {"close_timeout": True}, {"close_timeout": float("inf")},
                        {"close_timeout": float("nan")}):
                with self.assertRaises(ValueError, msg=str(bad)):
                    AsyncEvidenceStream(Path(tmp) / "e.jsonl", **bad)


if __name__ == "__main__":
    unittest.main()
