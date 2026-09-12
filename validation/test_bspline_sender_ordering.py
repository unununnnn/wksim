"""ROS-less sender ordering and lifetime checks using owned test connections."""
import socket
import threading
import unittest

from validation.test_planner_transport_receiver import sender, FakeBspline, clear_cps
from Simulator.wksim_runtime.bspline_tcp_envelope import BsplineTcpEncoder, BsplineTcpDecoder

SID = "0123456789abcdef0123456789abcdef"


class RecordingConnection:
    def __init__(self):
        self.data = bytearray()
        self.closed = False

    def sendall(self, data):
        if self.closed:
            raise OSError("closed")
        self.data.extend(data)

    def shutdown(self, how):
        self.closed = True

    def close(self):
        self.closed = True


class SenderOrderingTests(unittest.TestCase):
    def test_default_v1_bytes_unchanged_and_controls_require_opt_in(self):
        connection = RecordingConnection()
        encoder = BsplineTcpEncoder(SID)
        stream = sender.OrderedFrameSender(encoder, connection)
        message = FakeBspline(clear_cps())
        self.assertTrue(stream.send_bspline(message))
        self.assertEqual(bytes(connection.data), sender.encode_bspline_frame(BsplineTcpEncoder(SID), message))
        with self.assertRaises(ValueError):
            stream.send_control({"kind": "gate", "open": True})
        self.assertEqual(encoder.next_sequence, 2)
        stream.close()

    def test_mixed_sequence_and_terminal_cancel_suppress_later_output(self):
        connection = RecordingConnection()
        stream = sender.OrderedFrameSender(BsplineTcpEncoder(SID), connection, accept_control=True)
        stream.send_control({"kind": "gate", "open": True})
        stream.send_bspline(FakeBspline(clear_cps()))
        stream.send_control({"kind": "hold"})
        stream.send_control({"kind": "cancel"})
        before = bytes(connection.data)
        self.assertFalse(stream.send_bspline(FakeBspline(clear_cps(), traj_id=2)))
        self.assertFalse(stream.send_control({"kind": "cancel"}))
        self.assertEqual(bytes(connection.data), before)
        decoder = BsplineTcpDecoder(SID, accept_control=True)
        decoder.feed(before)
        frames = [decoder.read_frame_any() for _ in range(4)]
        self.assertEqual([f[0] for f in frames], ["control", "bspline", "control", "control"])
        self.assertEqual([frames[i][1]["kind"] for i in (0, 2, 3)], ["gate", "hold", "cancel"])
        self.assertEqual(decoder.high_water_sequence, 4)
        stream.close()

    def test_concurrent_callbacks_cannot_interleave_frame_writes(self):
        write, read = socket.socketpair()
        self.addCleanup(read.close)
        started, resume = threading.Event(), threading.Event()
        class FragmentingConnection:
            count = 0
            def sendall(self, data):
                self.count += 1
                if self.count == 1:
                    write.sendall(data[:3])
                    started.set()
                    if not resume.wait(2):
                        raise OSError("test release timed out")
                    write.sendall(data[3:])
                else:
                    write.sendall(data)
            def shutdown(self, how): write.shutdown(how)
            def close(self): write.close()
        encoder = BsplineTcpEncoder(SID)
        stream = sender.OrderedFrameSender(encoder, FragmentingConnection(), accept_control=True)
        self.addCleanup(stream.close)
        errors = []
        def call(operation):
            try: operation()
            except Exception as error: errors.append(error)
        first = threading.Thread(target=call, args=(lambda: stream.send_bspline(FakeBspline(clear_cps())),))
        second = threading.Thread(target=call, args=(lambda: stream.send_control({"kind": "gate", "open": False}),))
        first.start()
        try:
            self.assertTrue(started.wait(1))
            second.start()
            self.assertEqual(encoder.next_sequence, 2)
        finally:
            resume.set()
            first.join(2)
            if second.ident is not None: second.join(2)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertFalse(errors)
        decoder = BsplineTcpDecoder(SID, accept_control=True)
        frames = []
        read.settimeout(1)
        while len(frames) < 2:
            decoder.feed(read.recv(4096))
            while True:
                frame = decoder.read_frame_any()
                if frame is None: break
                frames.append(frame)
        self.assertEqual([f[0] for f in frames], ["bspline", "control"])
        self.assertEqual(decoder.high_water_sequence, 2)

    def test_shutdown_interrupts_send_and_failed_connection_cannot_resume(self):
        started, shutdown = threading.Event(), threading.Event()
        class BlockedConnection(RecordingConnection):
            def sendall(self, data):
                started.set()
                shutdown.wait(2)
                raise OSError("interrupted write")
            def shutdown(self, how):
                shutdown.set()
                super().shutdown(how)
        connection = BlockedConnection()
        encoder = BsplineTcpEncoder(SID)
        stream = sender.OrderedFrameSender(encoder, connection)
        errors = []
        def publish():
            try: stream.send_bspline(FakeBspline(clear_cps()))
            except OSError as error: errors.append(error)
        worker = threading.Thread(target=publish)
        worker.start()
        self.assertTrue(started.wait(1))
        closer = threading.Thread(target=stream.close)
        closer.start()
        self.assertTrue(shutdown.wait(1))
        worker.join(2); closer.join(2)
        self.assertFalse(worker.is_alive() or closer.is_alive())
        self.assertEqual(len(errors), 1)
        high_water = encoder.next_sequence
        with self.assertRaises(OSError): stream.send_bspline(FakeBspline(clear_cps(), traj_id=2))
        self.assertEqual(encoder.next_sequence, high_water)
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
