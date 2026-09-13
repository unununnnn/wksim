import copy
from pathlib import Path
import tempfile
import unittest

from Simulator.wksim_runtime.experiment_bundle import load_document,resolve

EXAMPLES=Path(__file__).resolve().parents[1]/'Simulator/wksim_runtime/examples/experiments'


class ExperimentBundleTests(unittest.TestCase):
    def test_two_real_experiment_families_resolve_without_machine_paths_in_intent(self):
        deployment=load_document(EXAMPLES/'local-deployment.json')
        for name in ('rate-control.json','copter-rate-control.json','ground-waypoints.json',
                     'rate-disturbance.json','copter-rate-disturbance.json'):
            intent=load_document(EXAMPLES/name)
            self.assertNotIn('/root/',str(intent))
            result=resolve(intent,deployment)
            self.assertIn('--manifest',result['python_argv'])
            self.assertFalse(result['production_admitted'])

    def test_relocating_or_replacing_receipt_changes_only_deployment(self):
        intent=load_document(EXAMPLES/'rate-control.json');before=copy.deepcopy(intent)
        deployment=load_document(EXAMPLES/'local-deployment.json')
        deployment['firmware_releases']['quad_rate_candidate']['manifest_linux']='/root/wksim-px4-inner-next/candidate.json'
        deployment['firmware_releases']['quad_rate_candidate']['manifest_sha256']='a'*64
        result=resolve(intent,deployment)
        self.assertEqual(intent,before)
        self.assertIn('/root/wksim-px4-inner-next/candidate.json',result['python_argv'])

    def test_wrong_vehicle_firmware_or_unimplemented_selection_is_rejected(self):
        deployment=load_document(EXAMPLES/'local-deployment.json')
        intent=load_document(EXAMPLES/'ground-waypoints.json')
        for changes in (dict(firmware='quad_rate_candidate'),dict(vehicle_model='fixed_wing'),
                        dict(path_controller='mpc'),dict(algorithms=['lqr']),dict(kind='fixed_wing'),dict(schema_version=True)):
            with self.subTest(changes=changes),self.assertRaises(ValueError):resolve(dict(intent,**changes),deployment)

    def test_receipt_path_hash_and_duplicate_json_are_strict(self):
        intent=load_document(EXAMPLES/'rate-control.json')
        for key,value in (('manifest_linux','/root/../elsewhere/candidate.json'),('manifest_sha256','latest')):
            deployment=load_document(EXAMPLES/'local-deployment.json')
            deployment['firmware_releases']['quad_rate_candidate'][key]=value
            with self.assertRaises(ValueError):resolve(intent,deployment)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'input.json';path.write_text('{"x":1,"x":2}')
            with self.assertRaises(ValueError):load_document(path)
