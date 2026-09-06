"""Offline product state contract/IPC tests; no FC, UE, DDS or model replacement."""
import copy
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from Simulator.wksim_core.state_stream import LatestState, StateWriter, identity, validate
from Simulator.ue55.bridge import actor_errors
from Simulator.ue55.state_relay import private_path

RUN = "a" * 32


def state(stamp=1):
    result = [0.] * 120
    result[2] = stamp
    result[6:9] = [1, 2, -3]
    result[12] = 1
    result[16:20] = [10, 20, 30, 40]
    return result


@unittest.skipUnless(sys.platform == "linux", "pathname IPC runs in WSL Linux")
class StateStreamTests(unittest.TestCase):
    def test_absent_full_reconnect_latest(self):
        with tempfile.TemporaryDirectory(prefix="wksim-state-", dir="/tmp") as folder:
            path = str(Path(folder)/"state.sock")
            with StateWriter(path, RUN) as writer:
                self.assertFalse(writer.emit(state()))  # Receiver need not exist at startup.
                with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as receiver:
                    receiver.bind(path)
                    receiver.setblocking(False)
                    started = time.monotonic()
                    for i in range(1000):
                        writer.emit(state(i+2))
                    self.assertLess(time.monotonic()-started, 2)
                    self.assertGreater(writer.dropped, 0)
                os.unlink(path)
                with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as receiver:
                    receiver.bind(path)
                    self.assertTrue(writer.emit(state(2000)))
                    packet = json.loads(receiver.recv(4096))
                    self.assertEqual(packet["sequence"], 1002)
                    self.assertEqual(packet["sim_time_s"], 2000)
                    validate(packet, RUN)

    def test_rejections_and_coordinate_metadata(self):
        with tempfile.TemporaryDirectory(prefix="wksim-state-", dir="/tmp") as folder:
            path = str(Path(folder)/"state.sock")
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as receiver, StateWriter(path, RUN) as writer:
                receiver.bind(path)
                writer.emit(state())
                packet = json.loads(receiver.recv(4096))
            latest = LatestState(RUN)
            self.assertTrue(latest.accept(json.dumps(packet)))
            self.assertFalse(latest.accept(json.dumps(packet)))
            changes = dict(version=1, run_id="b"*32, vehicle_id=True, sequence=True,
                           sim_time_s=0, source_wall_time_s=time.time()-2,
                           position_ned_m=[float("nan"), 0, 0], quaternion_wxyz=[0]*4,
                           rotor_rpm=[-1]*4, rotor_order=["FL", "FR", "RL", "RR"], position_unit="cm")
            for key, value in changes.items():
                bad = dict(packet, sequence=2, sim_time_s=2)
                bad[key] = value
                self.assertFalse(latest.accept(json.dumps(bad)), key)
            for raw in (b"[]", b"{", b"x"*4097, b"\xff"):
                self.assertFalse(latest.accept(raw))
            self.assertFalse(latest.accept(json.dumps(dict(packet, position_ned_m=[10**400, 0, 0]))))
            self.assertEqual(latest.packet, packet)
            ack = dict(run_id=RUN, sequence=packet["sequence"], sim_time_s=1,
                       ue_position_cm=[100, 200, 300], ue_quaternion_xyzw=[0, 0, 0, 1])
            self.assertEqual(actor_errors(packet, ack), dict(position_cm=0, quaternion_l2=0, sim_time_s=0))
            latest.packet = copy.deepcopy(packet)
            latest.packet["source_wall_time_s"] -= 2
            self.assertIsNone(latest.current())

    def test_private_path(self):
        with tempfile.TemporaryDirectory(prefix="wksim-state-", dir="/tmp") as folder:
            path = Path(folder)/"state.sock"
            self.assertEqual(private_path(path), path)
            os.chmod(folder, 0o755)
            with self.assertRaises(ValueError):
                private_path(path)
            os.chmod(folder, 0o700)
            path.symlink_to("/tmp/nonexistent-wksim-state")
            with self.assertRaises(ValueError):
                private_path(path)
        for path in ("relative", "/mnt/c/state.sock", "/tmp/state.sock", "/run/state.sock"):
            with self.assertRaises(ValueError):
                private_path(path)

    def test_relay_pull_coalescing_expiry_and_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="wksim-state-", dir="/tmp") as folder:
            path = str(Path(folder)/"state.sock")
            child = subprocess.Popen([sys.executable, "-m", "Simulator.ue55.state_relay",
                                      "--state-socket", path, "--run-id", RUN],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 3
                while not os.path.exists(path) and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(os.path.exists(path))
                with StateWriter(path, RUN) as writer:
                    for i in range(10):
                        writer.emit(state(i+1))
                        time.sleep(.002)
                    child.stdin.write(b"?")
                    child.stdin.flush()
                    self.assertTrue(select.select([child.stdout], [], [], 2)[0])
                    self.assertEqual(json.loads(child.stdout.readline())["packet"]["sequence"], 10)
                    time.sleep(.8)
                    child.stdin.write(b"?")
                    child.stdin.flush()
                    self.assertTrue(select.select([child.stdout], [], [], 2)[0])
                    self.assertIsNone(json.loads(child.stdout.readline())["packet"])
                child.stdin.close()
                self.assertEqual(child.wait(timeout=3), 0)
                self.assertFalse(os.path.exists(path))
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()
                child.stdout.close()
                child.stderr.close()

    def test_disabled_writer(self):
        identity("Product_AP-2026", 1)
        for invalid in ("", "_first", "a/b", "a"*65, "注入", "a\n"):
            with self.assertRaises(ValueError):
                identity(invalid, 1)
        with StateWriter() as writer:
            self.assertFalse(writer.emit(None))

    def test_private_network_namespace_pathname_ipc(self):
        with tempfile.TemporaryDirectory(prefix="wksim-state-", dir="/tmp") as folder:
            path = str(Path(folder)/"state.sock")
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as receiver:
                receiver.bind(path)
                receiver.settimeout(2)
                code = ("from Simulator.wksim_core.state_stream import StateWriter; "
                        "from validation.test_wksim_state_stream import state; "
                        "import sys; "
                        "writer=StateWriter(sys.argv[1],sys.argv[2]); "
                        "assert writer.emit(state())")
                result = subprocess.run(["unshare", "--net", sys.executable, "-c", code, path, RUN],
                                        capture_output=True, text=True, timeout=3)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(receiver.recv(4096))["vehicle_id"], 1)


if __name__ == "__main__":
    unittest.main()
