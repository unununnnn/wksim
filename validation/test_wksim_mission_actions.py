"""Offline public-interface tests using real temporary filesystem mailboxes."""

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
from wksim_runtime.mission_actions import ActionMailbox, request_action


class MissionActionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.run, self.mission, self.token, self.epoch = [uuid.uuid4().hex for _ in range(4)]
        self.generation = 2
        self.mailbox = ActionMailbox(self.directory, self.run, self.mission)
        self.status()

    @property
    def target(self):
        return self.directory / ("mission-action-" + self.token + ".json")

    def status(self, **changes):
        value = dict(version=1, run_id=self.run, mission_id=self.mission,
                     action_token=self.token, control_epoch=self.epoch,
                     native_generation=self.generation, allowed_actions=["pause", "resume"])
        value.update(changes)
        (self.directory / "mission-status.json").write_text(json.dumps(value), encoding="utf-8")

    def request(self, **changes):
        value = dict(version=1, run_id=self.run, mission_id=self.mission,
                     action_token=self.token, control_epoch=self.epoch,
                     native_generation=self.generation, action="pause", request_id=uuid.uuid4().hex)
        value.update(changes)
        return value

    def publish(self, action="pause"):
        return request_action(self.directory, self.run, self.mission, self.token, action)

    def poll(self, **changes):
        args = dict(token=self.token, control_epoch=self.epoch,
                    native_generation=self.generation, allowed_actions=["pause", "resume"])
        args.update(changes)
        return self.mailbox.poll(**args)

    def test_absent(self):
        self.assertIsNone(self.poll())
        self.assertEqual(self.mailbox.rejections, [])

    def test_once_idempotence_and_old_offer_replay(self):
        first = self.publish()
        raw = self.target.read_bytes()
        self.assertEqual(self.publish(), first)
        self.assertEqual(self.poll(), first)
        self.assertEqual(self.target.read_bytes(), raw)
        old = self.token
        self.token = uuid.uuid4().hex
        self.status()
        second = self.publish("resume")
        self.assertNotEqual(first["request_id"], second["request_id"])
        self.assertEqual(self.poll(), second)
        self.token = old
        self.target.write_text(json.dumps(self.request(action="resume")))
        self.assertIsNone(self.poll())
        self.assertTrue(self.target.exists())

    def test_invalid_requests_do_not_consume_or_overwrite(self):
        changes = [dict(version=True), dict(version=1.0), dict(version=2), dict(extra=1),
                   dict(run_id="wrong"), dict(mission_id="wrong"),
                   dict(control_epoch=uuid.uuid4().hex), dict(control_epoch="A" * 32),
                   dict(native_generation=-1), dict(native_generation=True),
                   dict(native_generation=2.0), dict(native_generation=3),
                   dict(action_token=uuid.uuid4().hex), dict(action_token="../bad"),
                   dict(request_id="A" * 32), dict(request_id=12), dict(request_id="bad"),
                   dict(action="cancel"), dict(action=[])]
        for change in changes:
            with self.subTest(change=change):
                raw = json.dumps(self.request(**change)).encode()
                self.target.write_bytes(raw)
                self.assertIsNone(self.poll())
                with self.assertRaises(ValueError):
                    self.publish()
                self.assertEqual(self.target.read_bytes(), raw)
        value = self.request()
        self.target.write_text(json.dumps(value))
        self.assertEqual(self.poll(), value)
        self.assertTrue(self.mailbox.rejections)

    def test_wrong_runtime_offer_does_not_consume(self):
        value = self.publish()
        for change in [dict(control_epoch="f" * 32), dict(native_generation=3),
                       dict(native_generation=True), dict(allowed_actions=["resume"]),
                       dict(allowed_actions="pause"), dict(allowed_actions=[{}])]:
            with self.subTest(change=change):
                self.assertIsNone(self.poll(**change))
        for run, mission in [("old", self.mission), (self.run, "old")]:
            mailbox = ActionMailbox(self.directory, run, mission)
            self.assertIsNone(mailbox.poll(self.token, self.epoch, 2, ["pause"]))
            self.assertTrue(mailbox.rejections)
        self.assertEqual(self.poll(), value)

    def test_invalid_token_before_path_access(self):
        for token in [None, [], "../outside", "A" * 32, "a" * 31, "a" * 33]:
            with self.subTest(token=token):
                self.assertIsNone(self.poll(token=token))
                with self.assertRaises(ValueError):
                    request_action(self.directory / "absent", self.run, self.mission, token, "pause")
        self.assertEqual(list(self.directory.iterdir()), [self.directory / "mission-status.json"])

    def test_conflicting_action_is_not_overwritten(self):
        value = self.publish()
        with self.assertRaises(ValueError):
            self.publish("resume")
        self.assertEqual(self.poll(), value)

    def test_malformed_request_and_size_boundary(self):
        valid = json.dumps(self.request())
        for raw in [b"[]", b"\xff", b"{", b" " * 4097, b'{"version":NaN}',
                    b'{"version":Infinity}', b'{"version":-Infinity}',
                    valid.replace('"version": 1', '"version": 1, "version": 1').encode(),
                    b'{"extra":' + b"[" * 1500 + b"0" + b"]" * 1500 + b"}"]:
            with self.subTest(raw=raw[:40]):
                self.target.write_bytes(raw)
                self.assertIsNone(self.poll())
                with self.assertRaises(ValueError):
                    self.publish()
                self.assertEqual(self.target.read_bytes(), raw)
        raw = valid.encode()
        self.target.write_bytes(raw + b" " * (4096 - len(raw)))
        self.assertIsNotNone(self.poll())

    def test_status_validation_even_for_existing_request(self):
        self.publish()
        original = self.target.read_bytes()
        for change in [dict(version=True), dict(version=2), dict(run_id="old"),
                       dict(mission_id="old"), dict(action_token="a" * 32),
                       dict(control_epoch=None), dict(control_epoch="A" * 32),
                       dict(native_generation=-1), dict(native_generation=True),
                       dict(native_generation=2.0), dict(allowed_actions=None),
                       dict(allowed_actions="pause"), dict(allowed_actions=["cancel"]),
                       dict(allowed_actions=["resume"]), dict(allowed_actions=[])]:
            with self.subTest(change=change):
                self.status(**change)
                with self.assertRaises(ValueError):
                    self.publish()
                self.assertEqual(self.target.read_bytes(), original)

    def test_confirmed_scope_cannot_be_upgraded_or_mistyped(self):
        confirmed = dict(control_epoch=self.epoch, native_generation=self.generation)
        for change in [dict(control_epoch='f' * 32), dict(native_generation=3),
                       dict(native_generation=True), dict(native_generation=2.0),
                       dict(extra=1)]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                request_action(self.directory, self.run, self.mission, self.token, 'pause',
                               expected_offer=dict(confirmed, **change))
            self.assertFalse(self.target.exists())
        for invalid in ({}, [], 'current'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                request_action(self.directory, self.run, self.mission, self.token, 'pause',
                               expected_offer=invalid)
        value = request_action(self.directory, self.run, self.mission, self.token, 'pause',
                               expected_offer=confirmed)
        before = self.target.read_bytes()
        self.status(native_generation=3)
        with self.assertRaisesRegex(ValueError, 'confirmed offer identity changed'):
            request_action(self.directory, self.run, self.mission, self.token, 'pause',
                           expected_offer=confirmed)
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(self.poll(), value)

    def test_status_bounded_and_strict(self):
        status = self.directory / "mission-status.json"
        valid = status.read_bytes()
        for raw in [b" " * (1024 * 1024 + 1), b"{", b"[]", b'{"version":NaN}',
                    valid.replace(b'"version": 1', b'"version": 1, "version": 1')]:
            status.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.publish()
            self.assertFalse(self.target.exists())
        status.unlink()
        with self.assertRaises(OSError):
            self.publish()
        status.write_bytes(valid + b" " * (1024 * 1024 - len(valid)))
        self.assertIsNotNone(self.publish())

    def test_concurrent_submission_and_poll(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            values = list(pool.map(lambda _: self.publish(), range(24)))
            polls = list(pool.map(lambda _: self.poll(), range(24)))
        self.assertTrue(all(v == values[0] for v in values))
        self.assertEqual([v for v in polls if v is not None], [values[0]])
        self.assertEqual(list(self.directory.glob(".mission-action-*")), [])

    def test_concurrent_conflicting_actions(self):
        def submit(action):
            try:
                return self.publish(action)
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(submit, ["pause", "resume"]))
        winners = [v for v in values if v is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(self.poll(), winners[0])

    def test_status_change_during_submission(self):
        fsync = os.fsync
        for change in [dict(run_id="old"), dict(mission_id="old"),
                       dict(action_token=uuid.uuid4().hex),
                       dict(control_epoch=uuid.uuid4().hex), dict(native_generation=3),
                       dict(allowed_actions=["pause"]), dict(allowed_actions=[])]:
            with self.subTest(change=change):
                self.status()
                def transition(fd):
                    fsync(fd)
                    self.status(**change)
                with mock.patch("wksim_runtime.mission_actions.os.fsync", side_effect=transition):
                    with self.assertRaises(ValueError):
                        self.publish()
                self.assertFalse(self.target.exists())
                self.assertEqual(list(self.directory.glob(".mission-action-*")), [])

    def test_atomic_visibility_and_hardlink_failure(self):
        link = os.link
        def observe(source, target):
            self.assertIsNone(self.poll())
            value = json.loads(Path(source).read_bytes())
            link(source, target)
            self.assertEqual(self.poll(), value)
        with mock.patch("wksim_runtime.mission_actions.os.link", side_effect=OSError("unsupported")):
            with self.assertRaises(OSError):
                self.publish()
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.directory.glob(".mission-action-*")), [])
        with mock.patch("wksim_runtime.mission_actions.os.link", side_effect=observe):
            self.publish()

    def test_nonregular_request(self):
        self.target.mkdir()
        self.assertIsNone(self.poll())
        with self.assertRaises(ValueError):
            self.publish()
        self.assertTrue(self.target.is_dir())

    def symlink(self, source, target, directory=False):
        try:
            target.symlink_to(source, target_is_directory=directory)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symlink creation unavailable: " + str(exc))

    def test_symlink_request(self):
        source = self.directory / "source.json"
        source.write_text(json.dumps(self.request()))
        self.symlink(source, self.target)
        self.assertIsNone(self.poll())
        with self.assertRaises(ValueError):
            self.publish()

    def test_symlink_status(self):
        status = self.directory / "mission-status.json"
        source = self.directory / "original-status.json"
        status.rename(source)
        self.symlink(source, status)
        with self.assertRaises(ValueError):
            self.publish()

    def test_symlink_directory_and_ancestor(self):
        actual = self.directory / "actual"
        actual.mkdir()
        (actual / "child").mkdir()
        link = self.directory / "link"
        self.symlink(actual, link, True)
        for directory in [link, link / "child"]:
            mailbox = ActionMailbox(directory, self.run, self.mission)
            self.assertIsNone(mailbox.poll(self.token, self.epoch, 2, ["pause"]))
            self.assertTrue(mailbox.rejections)
            with self.assertRaises(ValueError):
                request_action(directory, self.run, self.mission, self.token, "pause")

    @unittest.skipUnless(os.name == "nt", "Windows reparse junction test")
    def test_windows_junction_directory(self):
        actual = self.directory / "actual"
        actual.mkdir()
        junction = self.directory / "junction"
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(actual)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            mailbox = ActionMailbox(junction, self.run, self.mission)
            self.assertIsNone(mailbox.poll(self.token, self.epoch, 2, ["pause"]))
            self.assertTrue(mailbox.rejections)
            with self.assertRaises(ValueError):
                request_action(junction, self.run, self.mission, self.token, "pause")
        finally:
            junction.rmdir()

    def test_cli(self):
        command = [sys.executable, "-X", "utf8", "-B",
                   str(ROOT / "tools" / "control-wksim-mission.py"), str(self.directory)]
        missing = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(missing.returncode, 0)
        self.assertFalse(self.target.exists())
        args = ["--run-id", self.run, "--mission-id", self.mission,
                "--token", self.token, "--action", "pause"]
        result = subprocess.run(command + args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertTrue(value["submitted"])
        self.assertIn("NOT action completion", value["message"])
        self.assertEqual(self.poll(), value["request"])
        failed = subprocess.run(command + args[:-1] + ["resume"], capture_output=True, text=True)
        self.assertEqual(failed.returncode, 1)
        self.assertFalse(json.loads(failed.stderr)["submitted"])


if __name__ == "__main__":
    unittest.main()
