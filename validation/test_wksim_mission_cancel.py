"""Offline stdlib tests; all runtime evidence lives in temporary directories."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Simulator"))
from wksim_runtime.mission_cancel import CancelMailbox, request_cancel


class MissionCancelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.run = uuid.uuid4().hex
        self.mission = uuid.uuid4().hex
        self.target = self.directory / "mission-cancel.json"
        self.mailbox = CancelMailbox(self.directory, self.run, self.mission)
        self.status()

    def status(self, **changes):
        value = dict(version=1, run_id=self.run, mission_id=self.mission,
                     state="running", update_sequence=1)
        value.update(changes)
        (self.directory / "mission-status.json").write_text(json.dumps(value))

    def request(self, **changes):
        value = dict(version=1, run_id=self.run, mission_id=self.mission,
                     request_id=uuid.uuid4().hex, action="cancel")
        value.update(changes)
        return value

    def publish(self):
        return request_cancel(self.directory, self.run, self.mission)

    def test_absent(self):
        self.assertIsNone(self.mailbox.poll())
        self.assertEqual(self.mailbox.rejections, [])

    def test_once_and_idempotence(self):
        value = self.publish()
        original = self.target.read_bytes()
        self.assertEqual(self.publish(), value)
        self.assertEqual(self.target.read_bytes(), original)
        self.assertEqual(self.mailbox.poll(), value)
        self.assertIsNone(self.mailbox.poll())
        self.target.write_text(json.dumps(self.request()))
        self.assertIsNone(self.mailbox.poll())

    def test_invalid_requests_do_not_overwrite_or_consume(self):
        cases = [dict(run_id="wrong"), dict(mission_id=uuid.uuid4().hex),
                 dict(action="land"), dict(extra=True), dict(version=True),
                 dict(version=2), dict(request_id="bad"), dict(request_id=32)]
        for changes in cases:
            with self.subTest(changes=changes):
                raw = json.dumps(self.request(**changes)).encode()
                self.target.write_bytes(raw)
                self.assertIsNone(self.mailbox.poll())
                with self.assertRaises(ValueError):
                    self.publish()
                self.assertEqual(self.target.read_bytes(), raw)
        self.target.unlink()
        self.assertEqual(self.mailbox.poll(), None)
        self.assertEqual(self.mailbox.poll(), None)
        value = self.publish()
        self.assertEqual(self.mailbox.poll(), value)
        self.assertTrue(self.mailbox.rejections)

    def test_malformed(self):
        valid = json.dumps(self.request())
        for raw in [b'{"version":', b" " * 4097, b"[]", b"\xff",
                    valid.replace('"version": 1', '"version": 1, "version": 1').encode(),
                    b'{"version":NaN}', b"{" + b"[" * 1500]:
            with self.subTest(raw=raw[:30]):
                self.target.write_bytes(raw)
                self.assertIsNone(self.mailbox.poll())
                with self.assertRaises(ValueError):
                    self.publish()
                self.assertEqual(self.target.read_bytes(), raw)

    def test_byte_boundary(self):
        raw = json.dumps(self.request()).encode()
        self.target.write_bytes(raw + b" " * (4096 - len(raw)))
        self.assertIsNotNone(self.mailbox.poll())

    def test_status_rejections(self):
        for changes in [dict(state=s) for s in ("completed", "failed", "cancelled", "other")] + [
                dict(run_id="wrong"), dict(mission_id="old"),
                dict(update_sequence=True), dict(version=True), dict(state=[])]:
            with self.subTest(changes=changes):
                self.status(**changes)
                with self.assertRaises(ValueError):
                    self.publish()
                self.assertFalse(self.target.exists())

    def test_terminal_rejects_even_existing(self):
        self.publish()
        original = self.target.read_bytes()
        self.status(state="completed")
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(self.target.read_bytes(), original)

    def test_old_mission_and_run_cannot_replay(self):
        self.publish()
        for run, mission in [(self.run, uuid.uuid4().hex),
                             (uuid.uuid4().hex, self.mission)]:
            mailbox = CancelMailbox(self.directory, run, mission)
            self.assertIsNone(mailbox.poll())
            self.assertTrue(mailbox.rejections)

    def test_concurrent_publication(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.publish(), range(24)))
        self.assertTrue(all(value == results[0] for value in results))
        self.assertEqual(self.mailbox.poll(), results[0])
        self.assertEqual(list(self.directory.glob(".mission-cancel-*")), [])

    def test_publication_exposes_only_complete_request(self):
        link = os.link

        def observe(source, target):
            self.assertIsNone(self.mailbox.poll())
            value = json.loads(Path(source).read_bytes())
            self.assertEqual(value["mission_id"], self.mission)
            link(source, target)
            self.assertEqual(self.mailbox.poll(), value)

        with mock.patch("wksim_runtime.mission_cancel.os.link", side_effect=observe):
            self.publish()

    def test_link_failure_has_no_partial_fallback(self):
        with mock.patch("wksim_runtime.mission_cancel.os.link",
                        side_effect=OSError("hard links unavailable")):
            with self.assertRaises(OSError):
                self.publish()
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.directory.glob(".mission-cancel-*")), [])

    def test_missing_and_truncated_status(self):
        status = self.directory / "mission-status.json"
        status.unlink()
        with self.assertRaises(OSError):
            self.publish()
        status.write_text('{"version":')
        with self.assertRaises(ValueError):
            self.publish()
        self.assertFalse(self.target.exists())

    def test_state_change_before_link_is_rejected(self):
        fsync = os.fsync

        def complete(fd):
            fsync(fd)
            self.status(state="completed")

        with mock.patch("wksim_runtime.mission_cancel.os.fsync", side_effect=complete):
            with self.assertRaises(ValueError):
                self.publish()
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.directory.glob(".mission-cancel-*")), [])

    def test_nonregular(self):
        self.target.mkdir()
        self.assertIsNone(self.mailbox.poll())
        with self.assertRaises(ValueError):
            self.publish()
        self.assertTrue(self.target.is_dir())

    def symlink(self, target, link, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symlink creation unavailable: " + str(exc))

    def test_symlink_file(self):
        source = self.directory / "source.json"
        source.write_text(json.dumps(self.request()))
        self.symlink(source, self.target)
        self.assertIsNone(self.mailbox.poll())
        with self.assertRaises(ValueError):
            self.publish()

    def test_symlink_status(self):
        status = self.directory / "mission-status.json"
        source = self.directory / "status-source.json"
        status.rename(source)
        self.symlink(source, status)
        with self.assertRaises(ValueError):
            self.publish()
        self.assertFalse(self.target.exists())

    def test_symlink_directory_and_ancestor(self):
        actual = self.directory / "actual"
        actual.mkdir()
        child = actual / "child"
        child.mkdir()
        link = self.directory / "link"
        self.symlink(actual, link, True)
        for directory in (link, link / "child"):
            mailbox = CancelMailbox(directory, self.run, self.mission)
            self.assertIsNone(mailbox.poll())
            self.assertTrue(mailbox.rejections)
            with self.assertRaises(ValueError):
                request_cancel(directory, self.run, self.mission)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO only")
    def test_fifo_does_not_block(self):
        os.mkfifo(self.target)
        self.assertIsNone(self.mailbox.poll())
        with self.assertRaises(ValueError):
            self.publish()

    def test_cli_explicit_identity_and_submission_message(self):
        command = [sys.executable, "-B", str(ROOT / "tools" / "cancel-wksim.py"),
                   str(self.directory)]
        missing = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(missing.returncode, 0)
        self.assertFalse(self.target.exists())
        result = subprocess.run(command + ["--run-id", self.run, "--mission-id", self.mission],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout.splitlines()[0])["mission_id"], self.mission)
        self.assertIn("NOT confirmation", result.stdout)


if __name__ == "__main__":
    unittest.main()
