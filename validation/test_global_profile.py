"""Admission proof and actual ROS parameter representation regressions."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from Simulator.wksim_control.global_profile import load_proof, validate_profile
from Simulator.wksim_runtime.config import validate_config
from Simulator.wksim_runtime.runtime import launch_spec
from validation.test_wksim_runtime import config


class GlobalProfileTests(unittest.TestCase):
    def profile(self, path='/tmp/proof.json', checksum='a'*64):
        return dict(schema='global-home-v1', proof_path=path, proof_sha256=checksum,
                    require_same_value_home_reset=False)

    def test_profile_rejects_unknown_fields_paths_and_unsupported_same_value_capability(self):
        for value in (dict(self.profile(), extra=True), self.profile('/tmp/../proof'),
                      self.profile('relative'), self.profile(checksum='bad')):
            with self.assertRaises(ValueError): validate_profile(value)
        cfg = dict(config('arducopter'), control_protocol='session_v1', global_reference=self.profile())
        cfg['global_reference']['require_same_value_home_reset'] = True
        with self.assertRaisesRegex(ValueError, 'same_value_home_reset'): validate_config(cfg)

    def test_proof_checks_native_and_source_bytes_and_exact_datum_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            native, source = root/'native', root/'source'
            native.write_bytes(b'fixture native bytes'); source.write_bytes(b'fixture source bytes')
            sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
            proof = dict(schema='global-datum-proof-v1', stack='px4', run_id='run', datum='amsl',
                scene_origin=dict(id='scene', latitude_deg=0., longitude_deg=0., alt_amsl_m=50.),
                native_binary=dict(path=str(native), sha256=sha(native)), sources={str(source): sha(source)})
            path = root/'proof.json'; path.write_text(json.dumps(proof))
            profile = self.profile(str(path), sha(path))
            self.assertEqual(load_proof(profile, 'px4', 'run'), proof)
            with self.assertRaisesRegex(ValueError, 'datum_unverified'): load_proof(profile, 'px4', 'other')
            native.write_bytes(b'changed fixture native')
            with self.assertRaisesRegex(ValueError, 'datum_source_changed'): load_proof(profile, 'px4', 'run')

    def test_launch_requires_explicit_admission_and_encodes_json_as_yaml_string(self):
        import yaml
        profile = self.profile()
        cfg = validate_config(dict(config(), control_protocol='session_v1', global_reference=profile))
        with self.assertRaisesRegex(ValueError, 'explicit candidate admission'):
            launch_spec(cfg, Path('/tmp/run'), Path('/tmp/model.so'))
        plan = launch_spec(cfg, Path('/tmp/run'), Path('/tmp/model.so'), admitted_capabilities=('global_home_v1',))
        raw = next(v.split(':=', 1)[1] for v in plan['control'] if v.startswith('global_reference_profile:='))
        self.assertIsInstance(yaml.safe_load(raw), str)
        self.assertEqual(json.loads(yaml.safe_load(raw)), profile)


if __name__ == '__main__': unittest.main()
