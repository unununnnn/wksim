import json
import math
from pathlib import Path
import tempfile
import unittest

from Simulator.ue55.bridge import LatestTruth, actor_errors, packet_from_truth


class VisualBridgeTests(unittest.TestCase):
    def record(self):
        values = [0.] * 60
        values[6:9], values[12:16], values[16:20] = [1, 2, -3], [1, 0, 0, 0], [10, 20, 30, 40]
        return dict(frame=10, time=0.1, vehicle=values)

    def test_tail_partial_line_and_coalescing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"truth.jsonl"
            tail = LatestTruth(path)
            self.assertIsNone(tail.poll())
            path.write_bytes(b'{"frame":1}\n{"frame":2}\n{"fra')
            self.assertEqual(tail.poll(), dict(frame=2))
            self.assertIsNone(tail.poll())
            with path.open("ab") as stream:
                stream.write(b'me":3}\n')
            self.assertEqual(tail.poll(), dict(frame=3))

    def test_position_and_quaternion_axes(self):
        for axis in range(3):
            record = self.record()
            q = [math.cos(0.2), 0, 0, 0]
            q[axis+1] = math.sin(0.2)
            record["vehicle"][12:16] = q
            packet = packet_from_truth(record, "a"*32, "px4")
            # Reflection of basis z changes axial vector x,y signs, not yaw.
            expected = [-q[1], -q[2], q[3], q[0]]
            ack = dict(run_id="a"*32, sequence=10, sim_time_s=.1,
                       ue_position_cm=[100, 200, 300], ue_quaternion_xyzw=expected)
            self.assertEqual(actor_errors(packet, ack), dict(position_cm=0, quaternion_l2=0, sim_time_s=0))
            ack["ue_quaternion_xyzw"] = [-v for v in expected]
            self.assertEqual(actor_errors(packet, ack)["quaternion_l2"], 0)

    def test_px4_trace_without_servo_frame(self):
        record = self.record()
        del record["frame"]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"truth.jsonl"
            path.write_text((json.dumps(record) + "\n") * 3, encoding="utf-8")
            tail = LatestTruth(path)
            self.assertEqual(packet_from_truth(tail.poll(), "a"*32, "px4")["sequence"], 3)
            record["time"] = .2
            with path.open("a", encoding="utf-8") as source:
                source.write(json.dumps(record) + "\n")
            self.assertEqual(tail.poll()["frame"], 4)

    def test_nonfinite_ack_rejected(self):
        packet = packet_from_truth(self.record(), "a"*32, "px4")
        ack = dict(run_id="a"*32, sequence=10, sim_time_s=math.nan,
                   ue_position_cm=[100, 200, 300], ue_quaternion_xyzw=[0, 0, 0, 1])
        with self.assertRaises(ValueError):
            actor_errors(packet, ack)

    def test_invalid_physical_state(self):
        for field, value in [(6, math.nan), (8, 1e7), (12, 2), (16, -1)]:
            record = self.record()
            record["vehicle"][field] = value
            with self.assertRaises(ValueError):
                packet_from_truth(record, "a"*32, "arducopter")
        with self.assertRaises(ValueError):
            packet_from_truth(self.record(), "wrong", "px4")
        record = self.record()
        record["frame"] = True
        with self.assertRaises(ValueError):
            packet_from_truth(record, "a"*32, "px4")


if __name__ == "__main__":
    unittest.main()
