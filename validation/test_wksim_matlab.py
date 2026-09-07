"""Real TCP + real product HTTP/config tests; deliberately starts no flight."""
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

from Simulator.wksim_console.server import ConsoleServer
from Simulator.wksim_console.workspace import Workspace
from Simulator.wksim_matlab.server import Bridge, Console, MAX_FRAME


def wire(method, session=None, params=None, ident='r1', run=None):
    return (json.dumps(dict(version=1, request_id=ident, session_id=session, run_id=run,
                            method=method, params={} if params is None else params))+'\n').encode()


class Protocol(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Workspace(Path(self.tmp.name)/'console')
        self.http = ConsoleServer(self.workspace, 0)
        self.http_thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.http_thread.start()
        self.bridge = Bridge(Console(self.http.server_port), 0, timeout=.4)
        self.thread = threading.Thread(target=self.bridge.serve_forever, daemon=True)
        self.thread.start()
        self.connect()

    def connect(self):
        self.sock = socket.create_connection(self.bridge.server_address, timeout=2)
        self.file = self.sock.makefile('rb')
        self.sock.sendall(wire('hello'))
        self.hello = json.loads(self.file.readline())
        self.session = self.hello['session_id']

    def tearDown(self):
        self.file.close(); self.sock.close()
        self.bridge.shutdown(); self.bridge.server_close(); self.thread.join()
        self.http.shutdown(); self.http.server_close(); self.http_thread.join()
        self.workspace.close(); self.tmp.cleanup()

    def read(self):
        return json.loads(self.file.readline())

    def test_fragment_coalescence_and_config(self):
        raw = wire('configs', self.session, ident='r2')
        for byte in raw:
            self.sock.sendall(bytes([byte]))
        defaults = self.read()['result']['defaults']
        p = dict(name='matlab-test', stack='px4', run_id='matlab-test',
                 mission=defaults['px4']['mission'], expected_revision='')
        self.sock.sendall(wire('config.save', self.session, p, 'r3') + wire('runs', self.session, ident='r4'))
        saved, runs = self.read(), self.read()
        self.assertTrue(saved['ok']); self.assertEqual(runs['result']['runs'], [])
        self.assertTrue((self.workspace.config_dir/'matlab-test.json').is_file())
        # Duplicate ID must not execute a second save, even with altered content.
        p['name'] = 'replayed'
        self.sock.sendall(wire('config.save', self.session, p, 'r3'))
        self.assertEqual(self.read()['error']['code'], 'duplicate_request')
        self.assertFalse((self.workspace.config_dir/'replayed.json').exists())
        p['model_library'] = '/tmp/evil.so'
        self.sock.sendall(wire('config.save', self.session, p, 'r5'))
        self.assertEqual(self.read()['error']['code'], 'invalid_params')
        self.assertEqual(self.workspace.processes, {})

    def test_invalid_inputs(self):
        for raw in (b'{bad}\n', b'{"x":1,"x":2}\n', b'{"x":NaN}\n',
                    b'{"x":1e999}\n', b'\xff\n', b'[]\n'):
            self.sock.sendall(raw)
            self.assertFalse(self.read()['ok'])
        for i, method in enumerate(('step', 'shell', 'command.raw')):
            self.sock.sendall(wire(method, self.session, ident='bad'+str(i)))
            self.assertEqual(self.read()['error']['code'], 'unknown_method')
        self.sock.sendall(b'x'*(MAX_FRAME+1)+b'\n')
        self.assertEqual(self.read()['error']['code'], 'frame_too_large')
        self.assertEqual(self.file.readline(), b'')

    def test_reconnect_and_timeout_no_replay(self):
        old = self.session
        self.file.close(); self.sock.close(); self.connect()
        self.assertNotEqual(old, self.session)
        self.sock.sendall(wire('configs', old, ident='old'))
        self.assertEqual(self.read()['error']['code'], 'stale_session')
        self.sock.sendall(b'{"partial":')
        time.sleep(.6)
        self.assertEqual(self.file.readline(), b'')
        self.assertEqual(self.workspace.jobs, {})


if __name__ == '__main__':
    unittest.main()
