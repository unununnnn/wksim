"""Offline resource-admission regressions; synthetic fixtures are never flight proof."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from Simulator.wksim_runtime import joint_profile as joint


class MixedProfileAdmissionTests(unittest.TestCase):
    def test_missing_proofs_and_user_bypass_create_no_children(self):
        p = joint.select_profile(joint.MIXED_PROFILE)
        with patch.object(joint, '_mixed_firmware', side_effect=AssertionError('must not verify')):
            result = joint.check_resources(p)
        self.assertFalse(result['ok'])
        self.assertEqual(result['children_created'], 0)
        self.assertEqual(result['capabilities'], [])
        self.assertIn('Missing final mixed/PV', result['reasons'][0]['message'])
        for key, value in (('control_source', 'sealed_legacy'), ('promotion_flight', True),
                           ('capabilities', ['full_xyz_pv_yaw_v1'])):
            changed = dict(p, **{key: value})
            self.assertIn('descriptor differs', joint.check_resources(changed)['reasons'][0]['message'])

    def test_catalog_selectors_fail_closed_even_if_catalog_is_replaced(self):
        p = joint.select_profile(joint.MIXED_PROFILE)
        p['evidence'] = [dict(task_profile=task) for task in joint.MIXED_TASKS]
        cases = [dict(control_source='sealed_legacy'), dict(evidence_schema='legacy'),
                 dict(capabilities=['public_position']), dict(manifest_kinds=dict(ap='wksim_build_v1')),
                 dict(evidence=[dict(task_profile=joint.MIXED_TASKS[0])]*2)]
        for changes in cases:
            changed = dict(p, **changes)
            with self.subTest(changes=changes), patch.object(joint, 'select_profile', return_value=changed):
                with self.assertRaises(ValueError):
                    joint._profile_contract(changed)

    def test_legacy_pins_and_installed_source_remain_sealed(self):
        p = joint.select_profile(joint.LEGACY_PROFILE)
        self.assertEqual(p['manifests']['control']['sha256'],
                         'f02edf158bf9b4d75cfd2221412bdbe83a10b21bc1642c97259294e12ef487a7')
        self.assertEqual(p['manifests']['ap']['sha256'],
                         'f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a')
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory).resolve()/'repo'
            root = Path(directory).resolve()/'control'
            current = repo/'ros2/src/prometheus_control'
            staged = root/'src/prometheus_control'
            package = root/'install/prometheus_control'/joint.PYTHON/'prometheus_control'
            for base in (current/'prometheus_control', staged/'prometheus_control', package):
                base.mkdir(parents=True)
                (base/'node.py').write_text('sealed old source')
            for base in (current, staged):
                (base/'package.xml').write_text('build inputs')
            (root/'build.log').write_text('built')
            (repo/'tools').mkdir()
            (repo/'tools/build-joint-control.sh').write_text('build script')
            record = dict(root=str(root), package=str(package),
                          python_sha256={'node.py': joint.digest(package/'node.py')},
                          build_inputs={'package.xml': joint.digest(current/'package.xml')},
                          build_log_sha256=joint.digest(root/'build.log'),
                          build_script_sha256=joint.digest(repo/'tools/build-joint-control.sh'))
            with patch.object(joint, 'REPO', repo):
                with self.assertRaisesRegex(ValueError, 'requires manifest version 2'):
                    joint._control(record)
                (current/'prometheus_control/node.py').write_text('new current source')
                self.assertEqual(joint._control(record, sealed=True), str(package))
                with self.assertRaisesRegex(ValueError, 'requires manifest version 2'):
                    joint._control(record)
                (package/'node.py').write_text('tampered installed old source')
                with self.assertRaisesRegex(ValueError, 'source or installed'):
                    joint._control(record, sealed=True)

    def proof_fixture(self, root):
        """A minimal sealed test packet, not a native run or an auditor substitute."""
        p = joint.select_profile(joint.MIXED_PROFILE)
        p['evidence'] = []
        records = dict(ap={'baseline_manifest_sha256': 'b'*64}, control={'root': 'control'})
        native = dict(candidate=records['ap'], binary=dict(path='ap', sha256='a'*64),
                      source_files=24593, source_repositories=22, source_manifest_sha256='c'*64,
                      baseline_verification={'baseline_manifest_sha256': 'd'*64},
                      status='verified-built-not-admitted', production_admitted=False, flown=False)
        identities = dict(ap_mixed=native, px4=dict(path='px4', sha256='e'*64))
        model = dict(library=p['model_library'], library_sha256='f'*64)
        baseline = dict(px4=identities['px4'], model=model, message_packages={},
                        arducopter_agent={'path': 'ap-agent', 'sha256': '1'*64},
                        px4_agent={'path': 'px4-agent', 'sha256': '2'*64}, manifests=p['manifests'])
        sources = {name: '3'*64 for name in ('tools/run_joint_flight.py', 'tools/ap_mixed_candidate.py',
            'tools/prepare_ap_mixed_candidate.py', 'tools/verify_ap_pv_candidate.py',
            'Simulator/wksim_runtime/joint_profile.py', 'Simulator/wksim_core/model.py')}
        packets = []
        for task in joint.MIXED_TASKS:
            run = root/task
            run.mkdir()
            admission = dict(task_profile=task, ok=True, experimental=True, production_admitted=False,
                flown=False, children_created=0, reasons=[], manifest_sha256=p['manifests']['ap']['sha256'],
                control_manifest_sha256=p['manifests']['control']['sha256'],
                manifest_path=p['manifests']['ap']['path'], control_manifest_path=p['manifests']['control']['path'],
                candidate=records['ap'], control_candidate=records['control'], candidate_verification=native,
                identities=dict(ap_mixed=native, baseline=copy.deepcopy(baseline), source_sha256=sources))
            admission['capability'] = (dict(profile=task, position_axes='xyz', velocity_axes='xyz', yaw=True,
                acceleration=False, yaw_rate=False, mixed_axes=False, arducopter_type_mask=2496)
                if task == joint.MIXED_TASKS[0] else dict(profile=task, position_axes='z', velocity_axes='xy',
                    yaw=True, yaw_rate=False, acceleration=False, terrain=False, arducopter_type_mask=2531,
                    native_submode=7, vertical_velocity_avoidance=False))
            flight = dict(status='pass', flight_completed=True, source_unchanged=True, control_shutdown_clean=True,
                cleanup_errors=[], task_profile=task, run_id=task, scene_epoch='epoch', mixed_admission=admission,
                manifest_sha256={key:p['manifests'][key]['sha256'] for key in ('ap', 'control')},
                control_candidate=records['control'], model_build=model, source_sha256=sources,
                children={'arducopter-control': {'argv': ['control', '-p',
                    'arducopter_pv_profile:='+joint.MIXED_TASKS[0], '-p',
                    'arducopter_mixed_profile:='+joint.MIXED_TASKS[1]]}})
            audit = dict(status='pass', outstanding_checks=[], task_profile=task, run_id=task, scene_epoch='epoch',
                identity=dict(control_profiles=dict(arducopter_pv_profile=joint.MIXED_TASKS[0],
                                                     arducopter_mixed_profile=joint.MIXED_TASKS[1])),
                evidence_sha256={'ap-build.json':p['manifests']['ap']['sha256'],
                    'control-build.json':p['manifests']['control']['sha256'], 'mixed-source.json':'c'*64,
                    'baseline-pv-build.json':'b'*64,
                    **{'source__'+name.replace('/', '__')+'.txt':value for name,value in sources.items()}})
            packets.append((run, admission, flight, audit))
        return p, records, identities, packets

    def seal(self, p, packets):
        p['evidence'] = []
        for root, admission, flight, audit in packets:
            pins = dict(task_profile=flight['task_profile'])
            for key, name, value in (('admission', 'experimental-admission.json', admission),
                                     ('result', 'result.json', flight), ('audit', 'audit.json', audit)):
                if key == 'audit':
                    audit['result_sha256'] = pins['result']['sha256']
                    audit['evidence_sha256']['experimental-admission.json'] = pins['admission']['sha256']
                path = root/name
                path.write_text(json.dumps(value), encoding='utf-8')
                pins[key] = dict(path=str(path), sha256=joint.digest(path))
            p['evidence'].append(pins)

    def add_current_messages(self, root, records, packets):
        message_root = root/'messages'
        candidate = dict(version=1, root=str(message_root), packages={
            name: dict(prefix=str(message_root/'install'/name), installed_sha256=digit*64)
            for name,digit in (('prometheus_msgs','8'), ('wksim_msgs','9'))})
        message_path = message_root/'message-build.json'
        message_root.mkdir()
        message_path.write_text(json.dumps(candidate), encoding='utf-8')
        checksum = joint.digest(message_path)
        records['control'].update(message_candidate=candidate,
                                  message_manifest_path=str(message_path), message_manifest_sha256=checksum)
        for run, admission, flight, audit in packets:
            (run/'message-build.json').write_bytes(message_path.read_bytes())
            flight.update(message_candidate=copy.deepcopy(candidate))
            flight['manifest_sha256']['message'] = checksum
            admission.update(message_candidate=copy.deepcopy(candidate), message_manifest_path=str(message_path),
                             message_manifest_sha256=checksum)
            admission['identities']['message_candidate'] = copy.deepcopy(candidate)
            audit['evidence_sha256']['message-build.json'] = checksum
        return candidate

    def test_current_message_proofs_supply_exact_current_overlay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            p, records, identities, packets = self.proof_fixture(root)
            candidate = self.add_current_messages(root, records, packets)
            self.seal(p, packets)
            with patch.object(joint, '_raw_proof', side_effect=lambda pin,audit: Path(pin['result']['path']).parent):
                _, resources = joint._mixed_proofs(p, records, identities)
            self.assertEqual(set(resources['message_packages']), {'prometheus_msgs', 'wksim_msgs'})
            for name, item in resources['message_packages'].items():
                self.assertEqual(item['prefix'], candidate['packages'][name]['prefix'])
                self.assertEqual(item['sha256'], candidate['packages'][name]['installed_sha256'])
                self.assertIs(item['complete_snapshot'], True)

    def test_current_message_proof_mismatches_cannot_fall_back_to_baseline(self):
        changes = (
            lambda a,f,u: f['manifest_sha256'].pop('message'),
            lambda a,f,u: f.update(message_candidate=None),
            lambda a,f,u: a.update(message_manifest_path='/wrong/message-build.json'),
            lambda a,f,u: a.update(message_manifest_sha256='0'*64),
            lambda a,f,u: a['identities'].pop('message_candidate'),
            lambda a,f,u: u['evidence_sha256'].pop('message-build.json'),
        )
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                p, records, identities, packets = self.proof_fixture(root)
                self.add_current_messages(root, records, packets)
                change(*packets[0][1:])
                self.seal(p, packets)
                with patch.object(joint, '_raw_proof', side_effect=lambda pin,audit: Path(pin['result']['path']).parent):
                    with self.assertRaises(ValueError):
                        joint._mixed_proofs(p, records, identities)

    def test_retained_message_bytes_are_verified_not_just_recorded_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            p, records, identities, packets = self.proof_fixture(root)
            self.add_current_messages(root, records, packets)
            self.seal(p, packets)
            (packets[0][0]/'message-build.json').write_text('{}')
            with patch.object(joint, '_raw_proof', side_effect=lambda pin,audit: Path(pin['result']['path']).parent):
                with self.assertRaisesRegex(ValueError, 'SHA256'):
                    joint._mixed_proofs(p, records, identities)

    def test_mixed_result_with_rate_timing_probe_is_rejected(self):
        markers = (None, {}, False, 'enabled', {'diagnostic': 'anything'})
        for marker in markers:
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as directory:
                p, records, identities, packets = self.proof_fixture(Path(directory).resolve())
                packets[0][2]['rate_timing_probe'] = marker
                self.seal(p, packets)
                with patch.object(
                    joint,
                    '_raw_proof',
                    side_effect=lambda pin, audit: Path(pin['result']['path']).parent,
                ) as raw:
                    with self.assertRaisesRegex(ValueError, 'rate_timing_probe'):
                        joint._mixed_proofs(p, records, identities)
                raw.assert_not_called()
    def test_mixed_result_without_rate_timing_probe_uses_existing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            p, records, identities, packets = self.proof_fixture(Path(directory).resolve())
            self.seal(p, packets)
            with patch.object(
                joint,
                '_raw_proof',
                side_effect=lambda pin, audit: Path(pin['result']['path']).parent,
            ):
                healthy, resources = joint._mixed_proofs(p, records, identities)
            self.assertEqual(healthy['task_profile'], joint.MIXED_TASKS[-1])
            self.assertEqual(resources['px4'], identities['px4'])

    def test_cross_capability_identity_and_source_rejections(self):
        with tempfile.TemporaryDirectory() as directory:
            base = self.proof_fixture(Path(directory).resolve())
            p, records, identities, packets = base
            self.seal(p, packets)
            # Raw hashing is tested separately; here isolate cross-proof semantic binding.
            with patch.object(joint, '_raw_proof', side_effect=lambda pin, audit: Path(pin['result']['path']).parent):
                self.assertEqual(joint._mixed_proofs(p, records, identities)[1]['px4'], identities['px4'])
                changes = [
                    lambda a, f, u: a['identities']['baseline']['px4'].update(sha256='0'*64),
                    lambda a, f, u: a['identities']['baseline']['px4_agent'].update(sha256='0'*64),
                    lambda a, f, u: f['manifest_sha256'].update(ap='0'*64),
                    lambda a, f, u: a['candidate_verification'].update(source_files=1),
                    lambda a, f, u: u['evidence_sha256'].pop('mixed-source.json'),
                    lambda a, f, u: u['evidence_sha256'].pop('source__tools__ap_mixed_candidate.py.txt'),
                    lambda a, f, u: f['children']['arducopter-control']['argv'].pop(),
                    lambda a, f, u: a['capability'].update(velocity_axes='xyz'),
                    lambda a, f, u: u['identity']['control_profiles'].pop('arducopter_pv_profile'),
                    lambda a, f, u: u.update(task_profile='public_position'),
                ]
                for change in changes:
                    with self.subTest(change=change):
                        changed = copy.deepcopy(packets)
                        change(*changed[-1][1:])
                        self.seal(p, changed)
                        with self.assertRaises(ValueError):
                            joint._mixed_proofs(p, records, identities)

    def test_raw_bytes_pin_tamper_and_source_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            run = root/'run'
            run.mkdir()
            path = run/'result.json'
            path.write_text('{}')
            pin = dict(result=dict(path=str(path), sha256=joint.digest(path)))
            audit = dict(evidence_sha256={'result.json':joint.digest(path)})
            joint._raw_proof(pin, audit)
            path.write_text('{"status":"pass"}')
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                joint._pinned_json(pin['result'])
            with self.assertRaisesRegex(ValueError, 'Raw flight evidence'):
                joint._raw_proof(pin, audit)
            outside = root/'outside.json'
            outside.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'Raw flight evidence'):
                joint._raw_proof(pin, dict(evidence_sha256={'../outside.json':joint.digest(outside)}))


if __name__ == '__main__':
    unittest.main()
