"""Bounded profile admission negatives; no flight processes or installations."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from Simulator.wksim_runtime import joint_profile as profile
from Simulator.wksim_runtime.build_identity import file_identity


class JointProfileTests(unittest.TestCase):
    def test_unknown_profile(self):
        with self.assertRaises(ValueError):
            profile.select_profile('unknown')
        self.assertFalse(profile.check_profile('unknown','run')['ok'])

    def test_descriptor_copy(self):
        selected=profile.select_profile('joint_quad_dds_v1')
        selected['setup_files'].clear()
        self.assertEqual(len(profile.select_profile('joint_quad_dds_v1')['setup_files']),5)

    def test_bad_run_rejected_before_source_or_process(self):
        with patch.object(profile,'_firmware',side_effect=AssertionError('must not walk')):
            result=profile.check_profile('joint_quad_dds_v1','../bad')
        self.assertFalse(result['ok'])
        self.assertEqual(result['children_created'],0)
        self.assertIn('run_id',result['reasons'][0]['message'])

    def test_missing_ros_rejected_before_source(self):
        with patch.dict(os.environ,{'ROS_DISTRO':'wrong'}), patch.object(profile.platform,'system',return_value='Linux'), patch.object(profile,'_firmware',side_effect=AssertionError('must not walk')):
            result=profile.check_profile('joint_quad_dds_v1','run')
        self.assertFalse(result['ok'])

    def test_manifest_hash_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'build.json'; path.write_text('{}')
            pin=dict(path=str(path),sha256=profile.digest(path))
            self.assertEqual(profile._pinned_json(pin),{})
            path.write_text('{"tampered":true}')
            with self.assertRaisesRegex(ValueError,'SHA256'):
                profile._pinned_json(pin)

    def test_source_file_tamper_and_escape(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as external:
            root=Path(directory); path=root/'source.py'; path.write_text('one')
            expected={'source.py':file_identity(path,root)}
            profile._files(root,expected)
            path.write_text('two')
            with self.assertRaisesRegex(ValueError,'identity'):
                profile._files(root,expected)
            path.unlink(); outside=Path(external)/'source.py'; outside.write_text('one'); path.symlink_to(outside)
            with self.assertRaisesRegex(ValueError,'escapes'):
                profile._files(root,expected)

    def test_mixed_python_overlay(self):
        with patch.object(profile.importlib.util,'find_spec',return_value=None):
            with self.assertRaisesRegex(ValueError,'mixed overlay'):
                profile._overlay('prometheus_msgs','/wrong')

    def test_firmware_source_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            record=dict(candidate_root=directory,commit='1511f27194f1dcc3728270883047bdf022b3fd53',source={'files':{}})
            with patch.object(profile,'source_snapshot',return_value={'files':{'new':{}}}):
                with self.assertRaisesRegex(ValueError,'source snapshot'):
                    profile._firmware(record,'ap')

    def test_sealed_build_inputs_belong_to_historical_install(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            repo=root/'repo'; candidate=root/'candidate'
            package=candidate/'install/prometheus_control'/profile.PYTHON/'prometheus_control'
            staged=candidate/'src/prometheus_control'
            current=repo/'ros2/src/prometheus_control'
            for base in (package, staged/'prometheus_control', current/'prometheus_control'):
                base.mkdir(parents=True)
                (base/'__init__.py').write_text('same')
            (staged/'CMakeLists.txt').write_text('historical build')
            (current/'CMakeLists.txt').write_text('new candidate build')
            (candidate/'build.log').write_text('built')
            (repo/'tools').mkdir(); (repo/'tools/build-joint-control.sh').write_text('builder')
            record=dict(root=str(candidate),package=str(package),
                python_sha256={'__init__.py':profile.digest(package/'__init__.py')},
                build_inputs={'CMakeLists.txt':profile.digest(staged/'CMakeLists.txt')},
                build_log_sha256=profile.digest(candidate/'build.log'),
                build_script_sha256=profile.digest(repo/'tools/build-joint-control.sh'))
            with patch.object(profile,'REPO',repo):
                self.assertEqual(profile._control(record,sealed=True),str(package))
                with self.assertRaisesRegex(ValueError,'requires manifest version 2'):
                    profile._control(record,sealed=False)
                (staged/'CMakeLists.txt').write_text('tampered historical build')
                with self.assertRaisesRegex(ValueError,'build input'):
                    profile._control(record,sealed=True)

    def test_v2_control_checks_named_repo_support_and_complete_candidate_trees(self):
        from tools import joint_control_candidate as candidate_builder
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            repo=root/'repo'; candidate=root/'candidate'
            package=candidate/'install/prometheus_control'/profile.PYTHON/'prometheus_control'
            staged=candidate/'src/prometheus_control'
            current=repo/'ros2/src/prometheus_control'
            for base in (package, staged/'prometheus_control', current/'prometheus_control'):
                base.mkdir(parents=True)
                (base/'__init__.py').write_text('same')
            for namespace,names in candidate_builder.SIMULATOR_FILES.items():
                for base in (repo/'Simulator', candidate/'Simulator',
                             candidate/'install/prometheus_control'/profile.PYTHON/'Simulator'):
                    (base/namespace).mkdir(parents=True,exist_ok=True)
                    for name in names:
                        (base/namespace/name).write_text(namespace+'/'+name)
            for namespace,names in candidate_builder.SIMULATOR_ASSETS.items():
                for base in (repo/'Simulator', candidate/'Simulator',
                             candidate/'install/prometheus_control'/profile.PYTHON/'Simulator'):
                    (base/namespace).mkdir(parents=True,exist_ok=True)
                    for name in names:
                        (base/namespace/name).write_text('asset:'+name)
            # Unrelated repository modules are outside the installed closure.
            (repo/'Simulator/wksim_runtime/unrelated.py').write_text('not a candidate input')
            for name in candidate_builder.BUILD_INPUTS:
                for base in (current,staged):
                    path=base/name; path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_text(name)
            for name,target in candidate_builder.INSTALLED_INPUTS.items():
                installed=candidate/'install/prometheus_control'/target
                installed.parent.mkdir(parents=True,exist_ok=True)
                installed.write_bytes((current/name).read_bytes())
            transport=candidate/'install/prometheus_control/lib/libwksim_rc_take.so'
            transport.parent.mkdir(parents=True,exist_ok=True)
            transport.write_bytes(b'fixture transport, never loaded')
            (candidate/'build.log').write_text('built')
            (repo/'tools').mkdir()
            (repo/'tools/build-joint-control.sh').write_text('builder')
            (repo/'tools/joint_control_candidate.py').write_text('fixture sealer')
            (candidate/'build-joint-control.sh').write_text('builder')
            message=root/'message-build.json';message.write_text('fixture messages')
            with patch.object(profile,'REPO',repo), \
                    patch.object(candidate_builder,'REPO',repo), \
                    patch.object(candidate_builder,'PACKAGE',current), \
                    patch.object(candidate_builder,'MESSAGE_MANIFEST',message), \
                    patch.object(candidate_builder,'MESSAGE_SHA256',profile.digest(message)), \
                    patch.object(candidate_builder,'check_messages',return_value={'fixture':True}), \
                    patch.object(candidate_builder,'root_path',side_effect=lambda value:Path(value).resolve(strict=True)):
                record=candidate_builder.snapshot(candidate)
                (candidate/'build.json').write_text(json.dumps(record))
                self.assertEqual(len(record['simulator_python_sha256']),15)
                self.assertEqual(len(record['simulator_asset_sha256']),2)
                self.assertEqual(profile._control(record,sealed=False),str(package))
                self.assertEqual(profile._control(record,sealed=True),str(package))
                with self.assertRaisesRegex(ValueError,'record differs'):
                    profile._control(dict(record,scope='unbound record'),sealed=False)
                (repo/'Simulator/wksim_runtime/task.py').write_text('tampered')
                with self.assertRaisesRegex(ValueError,'Simulator'):
                    profile._control(record,sealed=False)
                (repo/'Simulator/wksim_runtime/task.py').write_text('wksim_runtime/task.py')
                asset=candidate/'Simulator/wksim_runtime/message_pins/ros1_Bspline.msg'
                original=asset.read_bytes();asset.write_text('tampered asset')
                for sealed in (False,True):
                    with self.subTest(sealed=sealed), self.assertRaisesRegex(ValueError,'Simulator.*asset'):
                        profile._control(record,sealed=sealed)
                asset.write_bytes(original)
                extra=candidate/'Simulator/wksim_runtime/extra.py';extra.write_text('extra')
                with self.assertRaisesRegex(ValueError,'Simulator support'):
                    profile._control(record,sealed=True)
                extra.unlink()
                transport.write_bytes(b'changed transport')
                with self.assertRaisesRegex(ValueError,'candidate changed'):
                    profile._control(record,sealed=False)
                transport.write_bytes(b'fixture transport, never loaded')
                (candidate/'install/prometheus_control/lib/prometheus_control/trajectory_bridge_node').write_text('tampered')
                with self.assertRaisesRegex(ValueError,'entry points'):
                    profile._control(record,sealed=True)

    def test_v1_sealed_control_requires_known_historical_builder(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve(); candidate=root/'candidate'
            package=candidate/'install/prometheus_control'/profile.PYTHON/'prometheus_control'
            staged=candidate/'src/prometheus_control'
            for base in (package, staged/'prometheus_control'):
                base.mkdir(parents=True); (base/'__init__.py').write_text('same')
            (staged/'CMakeLists.txt').write_text('historical')
            (candidate/'build.log').write_text('built')
            record=dict(version=1,root=str(candidate),package=str(package),
                python_sha256={'__init__.py':profile.digest(package/'__init__.py')},
                build_inputs={'CMakeLists.txt':profile.digest(staged/'CMakeLists.txt')},
                build_log_sha256=profile.digest(candidate/'build.log'),
                build_script_sha256=next(iter(profile.LEGACY_CONTROL_BUILD_SCRIPTS)))
            self.assertEqual(profile._control(record,sealed=True),str(package))
            with self.assertRaisesRegex(ValueError,'requires manifest version 2'):
                profile._control(record,sealed=False)
            record['build_script_sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'Unknown legacy'):
                profile._control(record,sealed=True)


PACERS=('Simulator/wksim_runtime/joint_rate.py','Simulator/wksim_runtime/joint_rate_probe.py')
FIXTURE_SOURCES=('tools/run_joint_flight.py','tools/ap_mixed_candidate.py',
    'tools/prepare_ap_mixed_candidate.py','tools/verify_ap_pv_candidate.py',
    'Simulator/wksim_runtime/joint_profile.py','Simulator/wksim_core/model.py')+PACERS+(
    'tools/run-joint-flight.sh',)  # one source beyond any required set, as real flights carry


def _mixed_proof_fixture(directory, *, drop=(), tamper_flight_hash=None,
                         tamper_admission_source=False, add_probe_record=False,
                         marker=None):
    """Build a complete, self-consistent two-task mixed/PV evidence tree on disk.

    Every pin digest is computed from the actual written bytes, so the real
    _mixed_proofs runs end to end against real files. Fixture data only; no
    flight, process, or installation.
    """
    root=Path(directory).resolve()
    sha=lambda data: hashlib.sha256(data).hexdigest()

    def write_json(path,obj):
        data=json.dumps(obj,indent=1,sort_keys=True).encode()
        path.write_bytes(data)
        return sha(data)

    ap_build=sha(b'fixture ap build manifest')
    control_build=sha(b'fixture control build manifest')
    mixed_source=sha(b'fixture mixed source manifest')
    baseline_pv=sha(b'fixture baseline pv build')
    ap_record={'name':'ap-record','baseline_manifest_sha256':baseline_pv}
    control_record={'name':'control-record'}
    model={'library':'model.so','name':'model'}
    px4={'name':'px4'}
    baseline={'manifests':{'px4':{'path':'/pinned/px4-build.json','sha256':'0'*64}},
              'px4':px4,'model':model,'message_packages':{},
              'arducopter_agent':{'path':'/agents/ap','sha256':'1'*64},
              'px4_agent':{'path':'/agents/px4','sha256':'2'*64}}
    native={'candidate':ap_record,'binary':'ap-binary','source_files':3,
            'source_repositories':'ap-repos','source_manifest_sha256':mixed_source,
            'baseline_verification':{'baseline_manifest_sha256':baseline_pv},
            'status':'verified-built-not-admitted','production_admitted':False,'flown':False}
    manifests={'ap':{'path':'/pinned/ap-build.json','sha256':ap_build},
               'control':{'path':'/pinned/control-build.json','sha256':control_build},
               'px4':{'path':'/pinned/px4-build.json','sha256':'0'*64}}
    control_profiles={'arducopter_pv_profile':profile.MIXED_TASKS[0],
                      'arducopter_mixed_profile':profile.MIXED_TASKS[1]}
    argv=['ros2','launch','prometheus_control','trajectory_bridge.launch.py','-p',
          'arducopter_pv_profile:='+profile.MIXED_TASKS[0],'-p',
          'arducopter_mixed_profile:='+profile.MIXED_TASKS[1]]
    capabilities={profile.MIXED_TASKS[0]:dict(profile=profile.MIXED_TASKS[0],position_axes='xyz',
                        velocity_axes='xyz',yaw=True,acceleration=False,yaw_rate=False,
                        mixed_axes=False,arducopter_type_mask=2496),
                  profile.MIXED_TASKS[1]:dict(profile=profile.MIXED_TASKS[1],position_axes='z',
                        velocity_axes='xy',yaw=True,yaw_rate=False,acceleration=False,terrain=False,
                        arducopter_type_mask=2531,native_submode=7,vertical_velocity_avoidance=False)}
    pins=[]; flights=[]
    for index,task in enumerate(profile.MIXED_TASKS):
        run=root/('run%d'%index); run.mkdir()
        (run/'ap-build.json').write_bytes(b'fixture ap build manifest')
        (run/'control-build.json').write_bytes(b'fixture control build manifest')
        (run/'mixed-source.json').write_bytes(b'fixture mixed source manifest')
        (run/'baseline-pv-build.json').write_bytes(b'fixture baseline pv build')
        sources={}
        for name in FIXTURE_SOURCES:
            if name in drop: continue
            data=('flown source: '+name).encode()
            (run/('source__'+name.replace('/','__')+'.txt')).write_bytes(data)
            sources[name]=sha(data)
        sealed=dict(sources)
        if tamper_flight_hash in sources:
            sources[tamper_flight_hash]='0'*64
        admission_sources={'tools/run_joint_flight.py':sources['tools/run_joint_flight.py']}
        if tamper_admission_source:
            admission_sources['tools/run_joint_flight.py']='f'*64
        admission={'task_profile':task,'ok':True,'experimental':True,'production_admitted':False,
                   'flown':False,'children_created':0,'reasons':[],'capability':capabilities[task],
                   'manifest_sha256':ap_build,'control_manifest_sha256':control_build,
                   'manifest_path':manifests['ap']['path'],
                   'control_manifest_path':manifests['control']['path'],
                   'candidate':ap_record,'control_candidate':control_record,
                   'identities':{'ap_mixed':native,'source_sha256':admission_sources,
                                 'baseline':baseline},
                   'candidate_verification':native}
        flight={'status':'pass','flight_completed':True,'source_unchanged':True,
                'control_shutdown_clean':True,'cleanup_errors':[],'task_profile':task,
                'run_id':'run-id-%d'%index,'scene_epoch':'epoch-1',
                'manifest_sha256':{'ap':ap_build,'control':control_build},
                'control_candidate':control_record,'mixed_admission':admission,
                'source_sha256':sources,'children':{'arducopter-control':{'argv':argv}},
                'model_build':model}
        if add_probe_record:
            flight['rate_timing_probe']={'classification':'diagnostic_only'}
        if marker is not None:
            marker_name,marker_value=marker
            flight[marker_name]=marker_value
        admission_sha=write_json(run/'experimental-admission.json',admission)
        result_sha=write_json(run/'result.json',flight)
        evidence={'ap-build.json':ap_build,'control-build.json':control_build,
                  'mixed-source.json':mixed_source,'baseline-pv-build.json':baseline_pv,
                  'experimental-admission.json':admission_sha}
        for name,value in sealed.items():
            evidence['source__'+name.replace('/','__')+'.txt']=value
        audit={'status':'pass','outstanding_checks':[],'task_profile':task,
               'result_sha256':result_sha,'run_id':'run-id-%d'%index,'scene_epoch':'epoch-1',
               'evidence_sha256':evidence,'identity':{'control_profiles':control_profiles}}
        audit_sha=write_json(run/'audit.json',audit)
        pins.append({'task_profile':task,
                     'result':{'path':str(run/'result.json'),'sha256':result_sha},
                     'audit':{'path':str(run/'audit.json'),'sha256':audit_sha},
                     'admission':{'path':str(run/'experimental-admission.json'),'sha256':admission_sha}})
        flights.append(flight)
    p={'evidence':pins,'manifests':manifests,'model_library':'model.so'}
    records={'ap':ap_record,'control':control_record}
    identities={'ap_mixed':native,'px4':px4}
    return p,records,identities,root,flights


class MixedProofPacerBindingTests(unittest.TestCase):
    """Real _mixed_proofs over the complete fixture: pacer-source binding (#84)."""

    def test_positive_with_pacer_sources_present_and_sealed(self):
        with tempfile.TemporaryDirectory() as directory:
            p,records,identities,_,flights=_mixed_proof_fixture(directory)
            for flight in flights:
                self.assertTrue(set(PACERS)<=set(flight['source_sha256']))
            healthy,resources=profile._mixed_proofs(p,records,identities)
            self.assertEqual(healthy['task_profile'],profile.MIXED_TASKS[1])
            self.assertEqual(resources['model']['library'],'model.so')
            self.assertEqual(resources['px4'],{'name':'px4'})

    def test_rejects_when_either_pacer_source_removed_from_flight_and_audit(self):
        for name in PACERS:
            with self.subTest(removed=name), tempfile.TemporaryDirectory() as directory:
                p,records,identities,_,flights=_mixed_proof_fixture(directory,drop=(name,))
                self.assertNotIn(name,flights[0]['source_sha256'])
                with self.assertRaisesRegex(ValueError,'Missing executed mixed proof source identity'):
                    profile._mixed_proofs(p,records,identities)

    def test_rejects_tampered_flight_source_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            p,records,identities,_,_=_mixed_proof_fixture(directory,tamper_flight_hash=PACERS[0])
            with self.assertRaisesRegex(ValueError,'Retained executed source is not sealed'):
                profile._mixed_proofs(p,records,identities)

    def test_rejects_tampered_retained_source_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            p,records,identities,root,_=_mixed_proof_fixture(directory)
            seal=root/'run0'/('source__'+PACERS[0].replace('/','__')+'.txt')
            seal.write_bytes(b'tampered retained source')
            with self.assertRaisesRegex(ValueError,'Raw flight evidence differs'):
                profile._mixed_proofs(p,records,identities)

    def test_rejects_admission_source_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            p,records,identities,_,_=_mixed_proof_fixture(directory,tamper_admission_source=True)
            with self.assertRaisesRegex(ValueError,'Admission/execution source differs'):
                profile._mixed_proofs(p,records,identities)

    def test_rejects_timing_probe_marker_in_formal_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            p,records,identities,_,_=_mixed_proof_fixture(directory,add_probe_record=True)
            with self.assertRaisesRegex(ValueError,'cannot include rate_timing_probe'):
                profile._mixed_proofs(p,records,identities)

    def test_rejects_group_work_timing_marker_with_any_value(self):
        # The formal gate is key-presence (joint_profile._mixed_proofs): True,
        # False, None and an empty object must all be rejected, not just a
        # populated diagnostic payload.
        for value in (True,False,None,{}):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                p,records,identities,_,_=_mixed_proof_fixture(
                    directory,marker=('group_work_timing',value))
                with self.assertRaisesRegex(ValueError,'cannot include group_work_timing'):
                    profile._mixed_proofs(p,records,identities)

    def test_rejects_perf_switch_capture_marker_with_any_value(self):
        for value in (True,False,None,{}):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                p,records,identities,_,_=_mixed_proof_fixture(
                    directory,marker=('perf_switch_capture',value))
                with self.assertRaisesRegex(ValueError,'cannot include perf_switch_capture'):
                    profile._mixed_proofs(p,records,identities)



if __name__=='__main__':
    unittest.main()
