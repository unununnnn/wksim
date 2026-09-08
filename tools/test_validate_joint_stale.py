"""Small regression gate: a fresh/misidentified/moved Actor must fail the audit."""
import copy
import json
from pathlib import Path
import unittest

from tools.validate_joint_stale import audit_snapshot


class StaleAuditTest(unittest.TestCase):
    def test_accepts_only_raw_correlated_dual_stale(self):
        # Existing real run supplies numerical samples; fixtures never claim new live proof.
        root = Path(__file__).resolve().parents[1]
        actor = json.loads((root / 'validation/joint-visual-20260907-run8/report.json').read_text())['airborne_actor']
        snapshot = copy.deepcopy(actor['ack'])
        for item in snapshot['observed_vehicles']: item['stale'] = True
        truths = {}
        for item in actor['packet']['vehicles']:
            state = [0] * 20
            state[6:9] = item['position_ned_m']; state[12:16] = item['quaternion_wxyz']
            truths[item['stack']] = dict(tick=snapshot['step'], state=state)
        authority = dict(tick=snapshot['step'])
        audit_snapshot(snapshot, actor['packet'], truths, authority)
        cases = []
        fresh = copy.deepcopy(snapshot); fresh['observed_vehicles'][0]['stale'] = False; cases.append(fresh)
        wrong = copy.deepcopy(snapshot); wrong['epoch'] = '0' * 32; cases.append(wrong)
        moved = copy.deepcopy(snapshot); moved['vehicles'][0]['ue_position_cm'][0] += 1; cases.append(moved)
        future = copy.deepcopy(snapshot); future['step'] += 1; cases.append(future)
        for candidate in cases:
            with self.assertRaises(ValueError): audit_snapshot(candidate, actor['packet'], truths, authority)


if __name__ == '__main__':
    unittest.main()
