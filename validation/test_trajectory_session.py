import unittest

from Simulator.wksim_planning.trajectory_session import MAX_COMMAND_ID, TrajectorySession


IDENTITY = dict(run_id="run-a", mission_id="mission-a", uav_id=1, control_epoch="epoch-a",
                planner_generation=0, command_high_water=40)


def identity(session, generation=None):
    value = dict(IDENTITY)
    value["planner_generation"] = session.generation if generation is None else generation
    return value


def start(session, event=1):
    generation = session.begin_replan(identity(session), event)
    session.accept_trajectory(identity(session, generation), generation, 7, 10, 20)
    return generation


class TrajectorySessionTests(unittest.TestCase):
    def test_initial_waiting_has_no_output_and_identity_is_bound(self):
        session = TrajectorySession(IDENTITY)
        self.assertEqual(session.state, "WAITING")
        self.assertIsNone(session.next_output(0, True, True))
        with self.assertRaises(ValueError):
            session.begin_replan(dict(IDENTITY, run_id="other"), 1)

    def test_replan_invalidates_old_result_and_ids_continue(self):
        session = TrajectorySession(IDENTITY)
        generation = start(session)
        session.sample(identity(session, generation), generation, 7, 10, (1, 2, 3), (0, 0, 0), (0, 0, 0), 0,
                       valid_until_tick=12)
        first = session.next_output(10, True, True)
        new_generation = session.begin_replan(identity(session), 2)
        self.assertGreater(new_generation, generation)
        with self.assertRaises(ValueError):
            session.accept_trajectory(identity(session, generation), generation, 8, 20, 30)
        session.accept_trajectory(identity(session, new_generation), new_generation, 8, 20, 30)
        session.sample(identity(session, new_generation), new_generation, 8, 20, (4, 5, 6), (0, 0, 0), (0, 0, 0), 0,
                       valid_until_tick=22)
        second = session.next_output(20, True, True)
        self.assertEqual((first["command_id"], second["command_id"]), (41, 42))
        self.assertEqual(second["generation"], new_generation)

    def test_stop_same_tick_wins_and_anchor_is_stable(self):
        session = TrajectorySession(IDENTITY)
        generation = start(session)
        session.sample(identity(session, generation), generation, 7, 10, (1, 2, 3), (1, 0, 0), (0, 0, 0), .2,
                       valid_until_tick=19)
        session.stop("no-route", identity(session), 2, anchor=((9, 8, 7), .4))
        first = session.next_output(10, True, True)
        second = session.next_output(11, True, True)
        self.assertEqual(first["intent"], second["intent"])
        self.assertEqual(first["position_ref"], [9.0, 8.0, 7.0])
        self.assertEqual(first["position_ref"], second["position_ref"])
        self.assertEqual(first["velocity_ref"], [0.0, 0.0, 0.0])
        self.assertEqual(first["acceleration_ref"], [0.0, 0.0, 0.0])
        self.assertEqual(first["command_id"] + 1, second["command_id"])

    def test_cancel_rejects_late_sample_and_replan(self):
        session = TrajectorySession(IDENTITY)
        generation = start(session)
        session.stop("cancel", identity(session), 2)
        self.assertEqual(session.state, "CANCELLED")
        self.assertIsNone(session.next_output(10, True, True))
        with self.assertRaises(ValueError):
            session.sample(identity(session, generation), generation, 7, 10, (0, 0, 0), (0, 0, 0), (0, 0, 0), 0)
        with self.assertRaises(ValueError):
            session.begin_replan(identity(session), 3)

    def test_sample_expiry_and_trajectory_end_hold(self):
        session = TrajectorySession(IDENTITY)
        generation = start(session)
        session.sample(identity(session, generation), generation, 7, 10, (1, 2, 3), (0, 0, 0), (0, 0, 0), 0,
                       valid_until_tick=11)
        self.assertEqual(session.next_output(10, True, True)["move_mode"], 6)
        expired = session.next_output(12, True, True)
        self.assertEqual((session.state, expired["intent"], expired["position_ref"]), ("HOLD", "hold", [1., 2., 3.]))
        session.accept_trajectory(identity(session), session.generation, 8, 20, 21)
        session.sample(identity(session), session.generation, 8, 20, (4, 5, 6), (0, 0, 0), (0, 0, 0), .1)
        self.assertEqual(session.next_output(21, True, True)["intent"], "hold")

    def test_safety_priority_releases_or_faults_without_output(self):
        session = TrajectorySession(IDENTITY)
        generation = start(session)
        session.sample(identity(session, generation), generation, 7, 10, (1, 2, 3), (0, 0, 0), (0, 0, 0), 0)
        self.assertIsNone(session.next_output(10, False, True))
        self.assertEqual(session.state, "RELEASED")
        self.assertIsNone(session.next_output(11, True, True))
        self.assertEqual(session.state, "RELEASED")
        stale = TrajectorySession(IDENTITY)
        start(stale)
        self.assertIsNone(stale.next_output(10, True, False))
        self.assertEqual(stale.state, "FAULTED")

    def test_rejects_bad_samples_events_and_non_monotonic_ticks(self):
        session = TrajectorySession(IDENTITY)
        generation = start(session)
        valid = (identity(session, generation), generation, 7, 10, (1, 2, 3), (0, 0, 0), (0, 0, 0), 0.)
        for changed in (dict(run_id="other", mission_id="mission-a", uav_id=1, control_epoch="epoch-a"),
                        identity(session, generation - 1)):
            with self.assertRaises(ValueError):
                session.sample(changed, *valid[1:])
        with self.assertRaises(ValueError):
            session.sample(*valid[:4], (True, 2, 3), *valid[5:])
        session.sample(*valid)
        with self.assertRaises(ValueError):
            session.sample(identity(session, generation), generation, 7, 10, (1, 2, 3), (0, 0, 0), (0, 0, 0), 0.)
        with self.assertRaises(ValueError):
            session.stop("stop", identity(session), 1, anchor=((0, 0, 0), 0))

    def test_failed_or_repeated_outputs_never_reuse_ids_and_overflow_faults(self):
        session = TrajectorySession(dict(IDENTITY, command_high_water=MAX_COMMAND_ID - 2))
        generation = start(session)
        session.sample(identity(session, generation), generation, 7, 10, (1, 2, 3), (0, 0, 0), (0, 0, 0), 0,
                       valid_until_tick=11)
        self.assertEqual(session.next_output(10, True, True)["command_id"], MAX_COMMAND_ID - 1)
        self.assertEqual(session.next_output(11, True, True)["command_id"], MAX_COMMAND_ID)
        with self.assertRaises(OverflowError):
            session.next_output(12, True, True)
        self.assertEqual(session.state, "FAULTED")


if __name__ == "__main__":
    unittest.main()
