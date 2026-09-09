"""Exercise real bounded group retirement with recording process/signal doubles."""
import io
import signal
import unittest
from unittest.mock import patch

from tools import run_hex_flight as runner


class HexRetirementTests(unittest.TestCase):
    def test_physics_terminal_precedes_fc_disconnect(self):
        events = []

        class Child:
            def __init__(self, pid, name):
                self.pid, self.name = pid, name
            def wait(self, timeout):
                events.append(('reaped', self.name))
                return 0

        names = ('physics', 'agent', 'fc', 'control')
        children = [(name, Child(i+100, name), io.StringIO()) for i, name in enumerate(names)]
        labels = {child.pid: name for name, child, _ in children}

        def killpg(pid, number):
            name = labels[pid]
            if number == signal.SIGTERM:
                if name == 'fc' and ('reaped', 'physics') not in events:
                    events.append(('unexpected_terminal', 'ConnectionResetError'))
                events.append(('term', name))

        with patch('Simulator.wksim_runtime.runtime.os.killpg', side_effect=killpg, create=True), \
                patch('Simulator.wksim_runtime.runtime.signal.SIGKILL', 9, create=True):
            self.assertEqual(runner.stop_children(children), [])
        self.assertNotIn(('unexpected_terminal', 'ConnectionResetError'), events)
        self.assertEqual([name for kind, name in events if kind == 'term'],
                         ['physics', 'control', 'fc', 'agent'])
        self.assertEqual([name for name, _, _ in children], list(names))
        self.assertTrue(all(log.closed for _, _, log in children))

    def test_empty_partial_startup_cleanup(self):
        self.assertEqual(runner.stop_children([]), [])


if __name__ == '__main__':
    unittest.main()
