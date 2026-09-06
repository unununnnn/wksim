"""Session Interface tests; Linux temporary files, no ROS graph or flight process."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'ros2/src/prometheus_control/prometheus_control/session.py'
spec = importlib.util.spec_from_file_location('wksim_session_under_test', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
RunSession = module.RunSession


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wksim-session-test-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'state'

    def open(self):
        session = RunSession('session-test', 1, self.directory)
        self.addCleanup(session.close)
        return session

    @staticmethod
    def request(session, request_id=1, **fields):
        return NS(**dict(dict(version=1, run_id=session.run_id, control_epoch=session.epoch,
                              request_id=request_id), **fields))

    def test_restart_changes_epoch_and_never_reuses_native_identity(self):
        first = self.open()
        old = self.request(first)
        self.assertEqual(first.accept(old), 1)
        identity = first.native_identity()
        first.close()
        second = self.open()
        self.assertNotEqual(first.epoch, second.epoch)
        with self.assertRaisesRegex(ValueError, 'wrong_run_or_control_epoch'):
            second.accept(old)
        self.assertEqual(second.last_request, 0)
        self.assertEqual(second.accept(self.request(second)), 1)
        self.assertNotEqual(identity, second.native_identity())

    def test_duplicate_and_invalid_envelopes_do_not_reenter(self):
        session = self.open()
        for changes in (dict(run_id='other'), dict(control_epoch='old'), dict(version=2),
                        dict(version=True), dict(request_id=0), dict(request_id=True), dict(request_id=2**64)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                session.accept(self.request(session, **changes))
        self.assertEqual(session.accept(self.request(session, request_id=9)), 9)
        for number in (9, 8, 1):
            with self.assertRaisesRegex(ValueError, 'request_id_not_increasing'):
                session.accept(self.request(session, request_id=number))

    def test_only_one_owner_for_run_and_vehicle(self):
        session = self.open()
        with self.assertRaises(BlockingIOError):
            self.open()
        session.close()
        second = self.open()
        self.assertEqual(second.native_identity(), (200, 1))

    def test_corrupt_counter_and_exhaustion_fail_closed(self):
        session = self.open()
        session.close()
        counter = self.directory / 'counter.json'
        counter.write_text('{')
        with self.assertRaises(ValueError):
            self.open()
        counter.write_text(json.dumps(dict(run_id='session-test', uav_id=1,
                                          next_native=RunSession.MAX_NATIVE_REQUESTS-1)))
        final = self.open()
        self.assertEqual(final.native_identity(), (254, 255))
        with self.assertRaisesRegex(ValueError, 'exhausted'):
            final.native_identity()
        final.close()
        with self.assertRaisesRegex(ValueError, 'exhausted'):
            self.open().native_identity()

    def test_persistence_failure_revokes_further_publication(self):
        session = self.open()
        with patch.object(session, '_commit', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                session.native_identity()
        with self.assertRaisesRegex(ValueError, 'closed'):
            session.native_identity()
        with self.assertRaisesRegex(ValueError, 'closed'):
            session.accept(self.request(session))

    def test_storage_and_run_identity_guards(self):
        for run_id in ('', '../old', 'run with spaces', 'x'*65):
            with self.assertRaises(ValueError):
                RunSession(run_id, 1, self.directory)
        for vehicle in (0, 256, True):
            with self.assertRaises(ValueError):
                RunSession('session-test', vehicle, self.directory)
        self.directory.mkdir(mode=0o755)
        with self.assertRaisesRegex(ValueError, 'mode0700'):
            self.open()
        self.directory.chmod(0o700)
        link = Path(self.temp.name) / 'alias'
        link.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'non-symlink'):
            RunSession('session-test', 1, link)


if __name__ == '__main__':
    unittest.main()
