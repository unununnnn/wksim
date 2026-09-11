"""Deterministic tests for state[k-1] -> terrain[k] JointPhysics integration."""
import math
import unittest
from unittest.mock import MagicMock, patch

from Simulator.wksim_core.joint import JointPhysics
from Simulator.wksim_runtime.scene_clock import SceneClock
from Simulator.wksim_runtime.terrain_feedback import TerrainFeedback


class DummyMavlinkSender:
    def __init__(self, *args, **kwargs):
        pass

    def hil_sensor_encode(self, *args, **kwargs):
        msg = MagicMock()
        msg.get_msgbuf.return_value = b"\x00" * 64
        return msg

    def hil_gps_encode(self, *args, **kwargs):
        msg = MagicMock()
        msg.get_msgbuf.return_value = b"\x00" * 64
        return msg

    def send(self, *args, **kwargs):
        pass


class JointTerrainFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.epoch = "0123456789abcdef0123456789abcdef"
        self.clock = SceneClock(self.epoch)
        self.workers = {"arducopter": MagicMock(), "px4": MagicMock()}

    def _make_physics(self, terrain_feedback=None):
        physics = object.__new__(JointPhysics)
        physics.clock = self.clock
        physics.workers = self.workers
        physics.health = lambda: None
        physics.record = lambda *args, **kwargs: None
        physics.peer = ("127.0.0.1", 14550)
        physics.px_time = 4000
        physics.px_commands = [0.0] * 16
        physics.pending_ap = {"frame": 1, "commands": [0.0] * 16}
        physics.ap = MagicMock()
        physics.protocol = DummyMavlinkSender()
        physics.cpu_timing = False
        physics.states = {}
        physics.inflight = None
        physics.finish_inputs = MagicMock()
        physics.terrain_feedback = terrain_feedback
        return physics

    def _make_state(self, tick=0, north=0.0, east=0.0, down=0.0):
        state = [0.0] * 120
        state[2] = tick / 1000.0
        state[6] = float(north)
        state[7] = float(east)
        state[8] = float(down)
        state[60] = float(tick * 1000)
        return state

    def _make_initial_response(self, north=0.0, east=0.0, down=0.0):
        return {
            "version": 1,
            "epoch": self.epoch,
            "tick": 0,
            "state": self._make_state(0, north, east, down),
            "initial": True,
        }

    def _make_step_response(self, tick, north=0.0, east=0.0, down=0.0):
        return {
            "version": 1,
            "epoch": self.epoch,
            "tick": tick,
            "state": self._make_state(tick, north, east, down),
        }

    def test_initialize_states_validations(self):
        physics = self._make_physics()

        # Non-dict initial_states
        with self.assertRaises(ValueError):
            physics.initialize_states(None)
        with self.assertRaises(ValueError):
            physics.initialize_states("invalid")

        # Incomplete worker set
        with self.assertRaises(ValueError):
            physics.initialize_states({"arducopter": self._make_initial_response()})

        # Extra worker set
        with self.assertRaises(ValueError):
            physics.initialize_states({
                "arducopter": self._make_initial_response(),
                "px4": self._make_initial_response(),
                "extra": self._make_initial_response(),
            })

        # Missing initial: True
        bad_resp = self._make_initial_response()
        del bad_resp["initial"]
        with self.assertRaises(ValueError):
            physics.initialize_states({"arducopter": bad_resp, "px4": self._make_initial_response()})

        # The full protocol response shape, version, and epoch are exact.
        for change in (
            lambda response: response.update(extra=True),
            lambda response: response.update(version=True),
            lambda response: response.update(version=2),
            lambda response: response.update(epoch="1" * 32),
        ):
            bad_resp = self._make_initial_response()
            change(bad_resp)
            with self.assertRaises(ValueError):
                physics.initialize_states({"arducopter": bad_resp, "px4": self._make_initial_response()})

        # Non-zero tick in initial response
        bad_resp = self._make_initial_response()
        bad_resp["tick"] = 1
        with self.assertRaises(ValueError):
            physics.initialize_states({"arducopter": bad_resp, "px4": self._make_initial_response()})

        # Non-120 state length
        bad_resp = self._make_initial_response()
        bad_resp["state"] = [0.0] * 60
        with self.assertRaises(ValueError):
            physics.initialize_states({"arducopter": bad_resp, "px4": self._make_initial_response()})
        bad_resp = self._make_initial_response()
        bad_resp["state"] = tuple(bad_resp["state"])
        with self.assertRaises(ValueError):
            physics.initialize_states({"arducopter": bad_resp, "px4": self._make_initial_response()})

        # Non-finite values in state
        for bad in (math.nan, math.inf, -math.inf, True, False, "0.0"):
            bad_resp = self._make_initial_response()
            bad_resp["state"][5] = bad
            with self.assertRaises(ValueError):
                physics.initialize_states({"arducopter": bad_resp, "px4": self._make_initial_response()})

        # Cannot call when tick != 0
        self.clock.tick = 1
        with self.assertRaises(ValueError):
            physics.initialize_states({
                "arducopter": self._make_initial_response(),
                "px4": self._make_initial_response(),
            })

    def test_initialize_states_deep_copy_and_no_mutation(self):
        physics = self._make_physics()
        ap_resp = self._make_initial_response(10.0, 20.0, -5.0)
        px4_resp = self._make_initial_response(0.0, 2.0, -1.0)
        init_states = {"arducopter": ap_resp, "px4": px4_resp}

        physics.initialize_states(init_states)

        # Mutate caller dictionary and lists
        init_states["arducopter"]["state"][6] = 999.0
        init_states["arducopter"] = None
        init_states["px4"]["state"][7] = 888.0

        # Verify physics.states remains isolated and unmutated
        self.assertEqual(physics.states["arducopter"][6], 10.0)
        self.assertEqual(physics.states["arducopter"][7], 20.0)
        self.assertEqual(physics.states["arducopter"][8], -5.0)
        self.assertEqual(physics.states["px4"][7], 2.0)
        self.assertEqual(len(physics.states["arducopter"]), 120)
        self.assertEqual(len(physics.states["px4"]), 120)

        with self.assertRaises(ValueError):
            physics.initialize_states({
                "arducopter": self._make_initial_response(),
                "px4": self._make_initial_response(),
            })

    @patch("Simulator.wksim_core.joint.receive_workers")
    def test_advance_tick1_uses_initial_states_and_attaches_exact_terrain(self, mock_receive_workers):
        tf = TerrainFeedback(self.epoch)
        physics = self._make_physics(terrain_feedback=tf)

        # Initialize at tick 0:
        # arducopter: outside box -> ENU [20.0, 10.0, 5.0] -> support height 0.0 -> terrain15d[0] = 0.0
        # px4: above box center [2.0, 0.0] -> ENU [2.0, 0.0, 2.0] -> support height 1.0 -> terrain15d[0] = -1.0
        physics.initialize_states({
            "arducopter": self._make_initial_response(10.0, 20.0, -5.0),
            "px4": self._make_initial_response(0.0, 2.0, -2.0),
        })

        captured_requests = {}

        def fake_receive_workers(requests, epoch, timeout=3.0, health=None):
            for k, v in requests.items():
                captured_requests[k] = v[1]
            return {
                "arducopter": self._make_step_response(1, 10.0, 20.0, -5.0),
                "px4": self._make_step_response(1, 0.0, 2.0, -2.0),
            }

        mock_receive_workers.side_effect = fake_receive_workers

        states = physics.advance()

        # Both workers received requests before receive_workers was completed
        self.assertEqual(mock_receive_workers.call_count, 1)
        self.assertIn("arducopter", captured_requests)
        self.assertIn("px4", captured_requests)

        # Check exact terrain attachment
        ap_req = captured_requests["arducopter"]
        px4_req = captured_requests["px4"]

        self.assertEqual(ap_req["tick"], 1)
        self.assertEqual(px4_req["tick"], 1)
        self.assertEqual(ap_req["terrain"], [0.0] * 15)
        self.assertEqual(px4_req["terrain"], [-1.0] + [0.0] * 14)
        self.assertTrue(all(type(v) is float for v in ap_req["terrain"]))
        self.assertTrue(all(type(v) is float for v in px4_req["terrain"]))

        # Clock committed tick 1
        self.assertEqual(self.clock.tick, 1)
        self.assertIsNone(self.clock.pending)
        self.assertEqual(states["arducopter"][2], 0.001)

    @patch("Simulator.wksim_core.joint.receive_workers")
    def test_advance_tick2_uses_prior_committed_state(self, mock_receive_workers):
        tf = TerrainFeedback(self.epoch)
        physics = self._make_physics(terrain_feedback=tf)

        # Tick 0 init
        physics.initialize_states({
            "arducopter": self._make_initial_response(0.0, 0.0, 0.0),
            "px4": self._make_initial_response(0.0, 0.0, 0.0),
        })

        captured_requests = {}

        def fake_receive_workers(requests, epoch, timeout=3.0, health=None):
            captured_requests.clear()
            for k, v in requests.items():
                captured_requests[k] = dict(v[1])
            tick = next(iter(requests.values()))[1]["tick"]
            # At tick 1, arducopter moves above box: ENU [2.0, 0.0, 3.0]
            if tick == 1:
                return {
                    "arducopter": self._make_step_response(1, 0.0, 2.0, -3.0),
                    "px4": self._make_step_response(1, 10.0, 20.0, -5.0),
                }
            elif tick == 2:
                return {
                    "arducopter": self._make_step_response(2, 0.0, 2.0, -3.0),
                    "px4": self._make_step_response(2, 10.0, 20.0, -5.0),
                }
            raise AssertionError(f"Unexpected tick {tick}")

        mock_receive_workers.side_effect = fake_receive_workers

        # Advance tick 1
        physics.advance()
        self.assertEqual(self.clock.tick, 1)

        # Clear barrier for 4-tick macro pacing in test clock
        self.clock.last_barrier = 0

        # Advance tick 2: should use tick 1 committed response state
        physics.advance()
        self.assertEqual(self.clock.tick, 2)

        # arducopter was at [0.0, 2.0, -3.0] -> ENU [2.0, 0.0, 3.0] -> above box -> height 1.0 -> -1.0
        self.assertEqual(captured_requests["arducopter"]["terrain"], [-1.0] + [0.0] * 14)
        # px4 was at [10.0, 20.0, -5.0] -> outside box -> height 0.0 -> 0.0
        self.assertEqual(captured_requests["px4"]["terrain"], [0.0] * 15)

    @patch("Simulator.wksim_core.joint.receive_workers")
    def test_fail_closed_before_receive_workers_when_observer_frozen(self, mock_receive_workers):
        tf = TerrainFeedback(self.epoch)
        physics = self._make_physics(terrain_feedback=tf)

        physics.initialize_states({
            "arducopter": self._make_initial_response(0.0, 0.0, 0.0),
            "px4": self._make_initial_response(0.0, 0.0, 0.0),
        })

        # Freeze px4 observer prior to tick 1
        tf.observers["px4"].frozen = True
        tf.observers["px4"].freeze_reason = "simulated_observer_fault"

        # Advance tick 1 must fail-closed before receive_workers
        with self.assertRaises(RuntimeError) as ctx:
            physics.advance()

        self.assertIn("frozen", str(ctx.exception))
        self.assertEqual(mock_receive_workers.call_count, 0)

    @patch("Simulator.wksim_core.joint.receive_workers")
    def test_fail_closed_before_receive_workers_when_prior_state_corrupted(self, mock_receive_workers):
        tf = TerrainFeedback(self.epoch)
        physics = self._make_physics(terrain_feedback=tf)

        physics.initialize_states({
            "arducopter": self._make_initial_response(0.0, 0.0, 0.0),
            "px4": self._make_initial_response(0.0, 0.0, 0.0),
        })

        # Corrupt one prior state in physics.states
        physics.states["arducopter"][15] = math.nan

        with self.assertRaises(ValueError) as ctx:
            physics.advance()

        self.assertIn("finite numeric", str(ctx.exception))
        self.assertEqual(mock_receive_workers.call_count, 0)

    @patch("Simulator.wksim_core.joint.receive_workers")
    def test_legacy_no_feedback_request_shape(self, mock_receive_workers):
        # terrain_feedback is None
        physics = self._make_physics(terrain_feedback=None)

        physics.initialize_states({
            "arducopter": self._make_initial_response(0.0, 0.0, 0.0),
            "px4": self._make_initial_response(0.0, 0.0, 0.0),
        })

        captured_requests = {}

        def fake_receive_workers(requests, epoch, timeout=3.0, health=None):
            for k, v in requests.items():
                captured_requests[k] = v[1]
            return {
                "arducopter": self._make_step_response(1, 0.0, 0.0, 0.0),
                "px4": self._make_step_response(1, 0.0, 0.0, 0.0),
            }

        mock_receive_workers.side_effect = fake_receive_workers

        physics.advance()

        self.assertEqual(mock_receive_workers.call_count, 1)
        self.assertNotIn("terrain", captured_requests["arducopter"])
        self.assertNotIn("terrain", captured_requests["px4"])
        self.assertEqual(set(captured_requests["arducopter"].keys()), {"version", "epoch", "tick", "commands"})
        self.assertEqual(set(captured_requests["px4"].keys()), {"version", "epoch", "tick", "commands"})


if __name__ == "__main__":
    unittest.main()
