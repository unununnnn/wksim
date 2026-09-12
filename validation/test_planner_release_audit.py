"""Boundary checks for the independent raw release auditor."""
import json
import math
import tempfile
import unittest
from pathlib import Path

from tools.audit_planner_release import (
    event_id_contiguous,
    publication_records,
    stop_metrics,
    tick_of,
)


class StopAuditTests(unittest.TestCase):
    def state(self, speed=0., north=0.):
        value = [0.]*13
        value[3] = speed
        value[6] = north
        return value

    def test_speed_or_drift_violation_is_rejected(self):
        self.assertEqual(stop_metrics(self.state(.25, 1.), [0., 0., 0.]), (.25, 1.))
        for state in (self.state(.250001), self.state(0., 1.000001), self.state(math.nan)):
            with self.assertRaises(ValueError):
                stop_metrics(state, [0., 0., 0.])

    def test_enu_transform_uses_original_physical_axes(self):
        state = self.state()
        state[6:9] = [3., 2., -4.]
        self.assertEqual(stop_metrics(state, [2., 3., 4.]), (0., 0.))

    def test_noninteger_or_off_grid_times_rejected(self):
        self.assertEqual(tick_of(67940000000), 67940)
        for bad in (0, 1000001, 1000000., True):
            with self.assertRaises(ValueError):
                tick_of(bad)


class EventIdContiguityTests(unittest.TestCase):
    """Source-assigned ControlNode event_id: real delivery evidence; gaps fail."""

    def test_contiguous_range_passes(self):
        self.assertEqual(event_id_contiguous([3, 1, 2]), [1, 2, 3])
        self.assertEqual(event_id_contiguous([7]), [7])

    def test_gap_fails(self):
        # A dropped datagram leaves a hole in the source counter: detected.
        for bad in ([1, 2, 4], [10, 12], [1, 3, 4]):
            with self.assertRaises(ValueError):
                event_id_contiguous(bad)

    def test_empty_fails(self):
        with self.assertRaises(ValueError):
            event_id_contiguous([])


class PublishLedgerTests(unittest.TestCase):
    """The task's own prometheus.jsonl is the authoritative send record."""

    def write_ledger(self, rows):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".jsonl", delete=False, encoding="utf-8")
        for row in rows:
            handle.write(json.dumps(row) + "\n")
        handle.close()
        self.addCleanup(Path(handle.name).unlink)
        return Path(handle.name)

    def row(self, kind, request_id, command_id=None, mode=None):
        message = {"version": 1, "run_id": "run-a", "control_epoch": "a" * 32,
                   "request_id": request_id}
        if kind == "CommandRequest":
            message["command"] = {"command_id": command_id}
        else:
            message["setup"] = {"cmd": 1, "px4_mode": mode}
        return {"wall": 0.1, "published": kind, "message": message,
                "request_envelope": True}

    def test_extracts_commands_and_setups_in_order(self):
        ledger = self.write_ledger([
            {"wall": 0.0, "phase": "x"},  # non-envelope rows skipped
            self.row("CommandRequest", 5, command_id=3),
            self.row("SetupRequest", 6, mode="AUTO.LAND"),
            self.row("CommandRequest", 7, command_id=4),
        ])
        records = publication_records(ledger)
        self.assertEqual([m['request_id'] for m in records],[5,6,7])
        self.assertEqual(records[0]['command']['command_id'],3)
        self.assertEqual(records[1]['setup']['px4_mode'],'AUTO.LAND')



class PublicationCoverageTests(unittest.TestCase):
    def test_actual_coverage_function_rejects_missing_or_changed_messages(self):
        import copy
        from tools.audit_planner_release import verify_publication_coverage
        messages=[dict(version=1,run_id='r',control_epoch='e',request_id=i,
                       command=dict(command_id=i,position_ref=[1.,2.,3.])) for i in (1,2,3)]
        args=dict(run_id='r',control_epoch='e')
        self.assertEqual(verify_publication_coverage(messages,messages,messages,**args)['requests'],3)
        self.assertEqual(verify_publication_coverage(messages,messages,list(reversed(messages)),**args)['requests'],3)
        for captured in (messages[1:],messages+[messages[-1]],messages[:1]+messages[2:]):
            with self.assertRaises(ValueError):verify_publication_coverage(messages,messages,captured,**args)
        changed=copy.deepcopy(messages);changed[1]['command']['position_ref'][0]=4.
        with self.assertRaises(ValueError):verify_publication_coverage(messages,messages,changed,**args)
        with self.assertRaises(ValueError):verify_publication_coverage(messages[:-1],messages,messages,**args)
        with self.assertRaises(ValueError):verify_publication_coverage(messages,messages,messages,run_id='other',control_epoch='e')

if __name__=='__main__':unittest.main()
