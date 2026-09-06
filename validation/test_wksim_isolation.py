"""Linux real flock tests, including path aliases and scoped reuse."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from Simulator.wksim_runtime.isolation import Reservation, resources


@unittest.skipUnless(sys.platform == 'linux', 'Linux reservations')
class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = dict(stack='px4', run_id='one', vehicle_id=1)
        self.a = resources(self.cfg, self.root / 'one')

    def reserve(self, resource):
        return Reservation(resource, self.root / 'locks')

    def other(self, **fields):
        return dict(self.a, run_id='two', output=str(self.root / 'two'), **fields)

    def test_duplicate_run_id_across_roots_and_networks(self):
        with self.reserve(self.a):
            with self.assertRaisesRegex(RuntimeError, 'run_id'):
                with self.reserve(dict(self.a, output='/different', network_namespace='other')):
                    pass

    def test_scoped_ids_ports_reusable_only_in_other_network(self):
        with self.reserve(self.a):
            with self.assertRaisesRegex(RuntimeError, 'conflict'):
                with self.reserve(self.other()):
                    pass
            with self.reserve(self.other(network_namespace='other')):
                pass

    def test_display_symlink_alias(self):
        target = self.root / 'display'
        target.mkdir()
        (self.root / 'alias').symlink_to(target, target_is_directory=True)
        first = resources(dict(self.cfg, display_socket=str(target / 'state.sock')), self.root / 'one')
        second = resources(dict(self.cfg, run_id='two', display_socket=str(self.root / 'alias/state.sock')), self.root / 'two')
        second['network_namespace'] = 'other'
        with self.reserve(first):
            with self.assertRaisesRegex(RuntimeError, 'display_socket'):
                with self.reserve(second):
                    pass

    def test_output_alias(self):
        (self.root / 'alias').symlink_to(self.root, target_is_directory=True)
        second = resources(dict(self.cfg, run_id='two'), self.root / 'alias/one')
        second['network_namespace'] = 'other'
        with self.reserve(self.a):
            with self.assertRaisesRegex(RuntimeError, 'output'):
                with self.reserve(second):
                    pass

    def test_telemetry_conflicts_across_networks_and_with_display(self):
        path = str(self.root / 'telemetry.sock')
        first = resources(dict(self.cfg, telemetry_socket=path), self.root / 'one')
        for field in ('telemetry_socket', 'display_socket'):
            second = resources(dict(self.cfg, run_id='two', **{field: path}), self.root / 'two')
            second['network_namespace'] = 'other'
            with self.reserve(first):
                with self.assertRaisesRegex(RuntimeError, 'conflict'):
                    with self.reserve(second):
                        pass

    def test_different_telemetry_consumers_in_independent_networks(self):
        first = resources(dict(self.cfg, telemetry_socket=str(self.root / 'a.sock')), self.root / 'one')
        second = resources(dict(self.cfg, run_id='two', telemetry_socket=str(self.root / 'b.sock')), self.root / 'two')
        second['network_namespace'] = 'other'
        with self.reserve(first), self.reserve(second):
            pass

    def test_lock_inherited_until_child_exits_and_reusable_after(self):
        with self.reserve(self.a) as reservation:
            child = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.read()'],
                                     stdin=subprocess.PIPE, pass_fds=reservation.fds)
        try:
            with self.assertRaisesRegex(RuntimeError, 'conflict'):
                with self.reserve(self.a):
                    pass
        finally:
            child.communicate(timeout=5)
        with self.reserve(self.a):
            pass


if __name__ == '__main__':
    unittest.main()
