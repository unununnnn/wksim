"""Read-only real evidence checks and mutations of private temporary copies."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from tools.audit_independent_profile import audit, REPO
from Simulator.wksim_runtime.independent_profile import check_flight_evidence
from Simulator.wksim_runtime.joint_profile import select_profile

ARCHIVE = REPO/'validation/independent-admission-20260907/flown-source'

class IndependentEvidenceTests(unittest.TestCase):
    def test_retained_real_flights_and_build_binding(self):
        catalog = json.loads((REPO/'Simulator/wksim_runtime/independent-profile-evidence.json').read_text())
        archive = (REPO/catalog['archive_manifest']['path']).parent
        for label, row in catalog['runs'].items():
            directory = (REPO/row['result']['path']).parent.parent
            result = audit(directory, archive)
            self.assertFalse(result['source_audit']['current_checkout_accepted'])
            self.assertEqual(len(result['physical']['completed_waypoints']), 3)
            run = json.loads((directory/'run/result.json').read_text())
            identities = run['preflight']['identities']
            p = select_profile('joint_quad_dds_v1')
            proof = check_flight_evidence(run['stack'], p, identities)
            self.assertFalse(proof['current_admission_code_flown'])
            key = 'ap' if label == 'arducopter' else 'px4'
            identities[key]['sha256'] = 'changed'
            with self.assertRaisesRegex(ValueError, 'does not match'):
                check_flight_evidence(run['stack'], p, identities)

    def test_envelope_truth_image_mutations_rejected(self):
        original = REPO/'validation/independent-mission-px4-20260907-run1'
        for name in ('run/prometheus.jsonl', 'run/truth.jsonl', 'fc-maps.txt'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)/'flight'
                shutil.copytree(original, directory)
                target = directory/name
                if name.endswith('prometheus.jsonl'):
                    rows = [json.loads(s) for s in target.read_text().splitlines()]
                    next(r for r in rows if r.get('request_envelope'))['message']['run_id'] = 'foreign'
                    target.write_text(''.join(json.dumps(r)+'\n' for r in rows))
                elif name.endswith('truth.jsonl'):
                    target.write_text('')
                else:
                    target.write_text(target.read_text()+'\nchanged-image-identity\n')
                with self.assertRaises((ValueError, AssertionError)):
                    audit(directory, ARCHIVE)

if __name__ == '__main__':
    unittest.main()
