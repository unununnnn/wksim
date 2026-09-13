"""Fault-injection tests for experiment input identity binding.

These are pure-Python: no firmware, model, SITL, ROS, UE or build action runs.
`--execute` is only ever reached with `os.execvp` mocked, so no child process starts.
"""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from Simulator.wksim_runtime.experiment_bundle import (document_digest,load_document,
    load_document_with_digest,resolve,verify_document_identity)
from tools import run_experiment

REPO=Path(__file__).resolve().parents[1]
EXAMPLES=REPO/'Simulator/wksim_runtime/examples/experiments'
EXAMPLES_AND_IDS=(('rate-control.json','quad-rate-control-comparison'),
                  ('copter-rate-control.json','copter-rate-control-comparison'),
                  ('ground-waypoints.json','ackermann-waypoints'),
                  ('rate-disturbance.json','quad-rate-control-comparison-disturbance'),
                  ('copter-rate-disturbance.json','copter-rate-control-comparison-disturbance'))


def other_intent(identifier='rewritten-intent'):
    return dict(schema_version=1,id=identifier,kind='body_rate_comparison',vehicle_model='quad_x',
                firmware='quad_rate_candidate',algorithms=['pid'])


class ExperimentInputIdentityTests(unittest.TestCase):
    def setUp(self):
        self._directory=tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.directory=Path(self._directory.name)
        self.experiment=self.directory/'rate-control.json'
        self.deployment=self.directory/'local-deployment.json'
        self.original_experiment_bytes=(EXAMPLES/'rate-control.json').read_bytes()
        self.experiment.write_bytes(self.original_experiment_bytes)
        self.deployment.write_bytes((EXAMPLES/'local-deployment.json').read_bytes())

    def run_cli(self,argv):
        """Run the CLI entry with shell-like string arguments, restoring cwd even on failure."""
        argv=[str(item) for item in argv]
        cwd=os.getcwd();stream=io.StringIO()
        try:
            with contextlib.redirect_stdout(stream):result=run_experiment.main(argv)
        finally:os.chdir(cwd)
        return result,stream.getvalue()

    def execute_argv(self,arguments):
        return [str(item) for item in arguments]+['--execute']

    def test_one_read_yields_semantics_and_digest_of_the_same_bytes(self):
        document,digest=load_document_with_digest(self.experiment)
        self.assertEqual(digest,hashlib.sha256(self.original_experiment_bytes).hexdigest())
        self.assertEqual(document,load_document(self.experiment))
        self.experiment.write_text(json.dumps(other_intent()),encoding='utf-8')
        self.assertNotEqual(document['id'],other_intent()['id'])
        self.assertEqual(document['algorithms'],['native','pid','lqr','mpc'])
        self.assertEqual(digest,hashlib.sha256(self.original_experiment_bytes).hexdigest())
        self.assertNotEqual(document_digest(self.experiment),digest)

    def test_duplicate_and_nonfinite_validation_is_reused_by_the_single_read(self):
        cases=(('{"x":1,"x":2}','Duplicate configuration key: x'),
               ('{"schema_version":NaN}','Nonfinite JSON constant: NaN'),
               ('{"schema_version":Infinity}','Nonfinite JSON constant: Infinity'))
        for text,message in cases:
            with self.subTest(text=text):
                self.experiment.write_text(text,encoding='utf-8')
                for loader in (load_document,load_document_with_digest):
                    with self.assertRaises(ValueError) as caught:loader(self.experiment)
                    self.assertEqual(str(caught.exception),message)

    def test_changed_file_after_the_read_fails_closed_without_starting_a_process(self):
        real_read=run_experiment.load_document_with_digest
        def racing_read(path):
            document,digest=real_read(path)
            if Path(path)==self.experiment:
                self.experiment.write_text(json.dumps(other_intent()),encoding='utf-8')
            return document,digest
        execvp=mock.Mock()
        argv=self.execute_argv([self.experiment,'--deployment',self.deployment])
        cwd=os.getcwd();stream=io.StringIO()
        try:
            with mock.patch.object(run_experiment,'load_document_with_digest',side_effect=racing_read),\
                    mock.patch.object(run_experiment.os,'execvp',execvp),\
                    contextlib.redirect_stdout(stream):
                with self.assertRaises(RuntimeError) as caught:run_experiment.main(argv)
        finally:os.chdir(cwd)
        self.assertIn('changed after it was read',str(caught.exception))
        self.assertIn(str(self.experiment),str(caught.exception))
        execvp.assert_not_called()
        plan=json.loads(stream.getvalue())
        self.assertEqual(plan['intent']['id'],'quad-rate-control-comparison')
        self.assertEqual(plan['intent']['algorithms'],['native','pid','lqr','mpc'])
        self.assertEqual(plan['inputs'][str(self.experiment)],
                         hashlib.sha256(self.original_experiment_bytes).hexdigest())
        self.assertNotEqual(document_digest(self.experiment),plan['inputs'][str(self.experiment)])

    def test_changed_file_after_the_read_raises_only_after_the_plan_is_reported(self):
        real_read=run_experiment.load_document_with_digest
        def racing_read(path):
            document,digest=real_read(path)
            if Path(path)==self.deployment:
                self.deployment.write_text('{"schema_version":1,"firmware_releases":{}}',encoding='utf-8')
            return document,digest
        execvp=mock.Mock()
        cwd=os.getcwd();stream=io.StringIO()
        try:
            with mock.patch.object(run_experiment,'load_document_with_digest',side_effect=racing_read),\
                    mock.patch.object(run_experiment.os,'execvp',execvp),\
                    contextlib.redirect_stdout(stream):
                with self.assertRaises(RuntimeError) as caught:
                    run_experiment.main(self.execute_argv([self.experiment,'--deployment',self.deployment]))
        finally:os.chdir(cwd)
        self.assertIn('changed after it was read',str(caught.exception))
        self.assertIn(str(self.deployment),str(caught.exception))
        execvp.assert_not_called()
        self.assertEqual(json.loads(stream.getvalue())['inputs'][str(self.deployment)],
                         hashlib.sha256((EXAMPLES/'local-deployment.json').read_bytes()).hexdigest())

    def test_one_file_cannot_serve_as_both_documents(self):
        dot_alias=str(self.directory)+os.sep+'.'+os.sep+'rate-control.json'
        detour=str(self.directory/'nested'/'..'/'rate-control.json')
        pairs=((self.experiment,self.experiment),
               (self.experiment,dot_alias),
               (dot_alias,self.experiment),
               (self.experiment,detour))
        for experiment,deployment in pairs:
            with self.subTest(experiment=str(experiment),deployment=str(deployment)):
                loader=mock.Mock(side_effect=AssertionError('document loader must not run'))
                execvp=mock.Mock()
                with mock.patch.object(run_experiment,'load_document_with_digest',loader),\
                        mock.patch.object(run_experiment.os,'execvp',execvp),\
                        mock.patch.object(run_experiment.sys,'platform','linux'):
                    with self.assertRaises(ValueError) as caught:
                        self.run_cli(self.execute_argv([experiment,'--deployment',deployment]))
                self.assertIn('two distinct documents',str(caught.exception))
                loader.assert_not_called()
                execvp.assert_not_called()

    def test_one_inode_under_two_names_cannot_serve_as_both_documents(self):
        link=self.directory/'linked-experiment.json'
        try:os.link(self.experiment,link)
        except (AttributeError,NotImplementedError,OSError):self.skipTest('hard links unavailable here')
        loader=mock.Mock(side_effect=AssertionError('document loader must not run'))
        execvp=mock.Mock()
        with mock.patch.object(run_experiment,'load_document_with_digest',loader),\
                mock.patch.object(run_experiment.os,'execvp',execvp),\
                mock.patch.object(run_experiment.sys,'platform','linux'):
            with self.assertRaises(ValueError) as caught:
                self.run_cli(self.execute_argv([self.experiment,'--deployment',link]))
        self.assertIn('two distinct documents',str(caught.exception))
        loader.assert_not_called()
        execvp.assert_not_called()

    def test_distinct_documents_are_still_accepted(self):
        self.assertIsNone(run_experiment.require_distinct_documents(self.experiment,self.deployment))
        plan,identities=run_experiment.resolve_plan(self.experiment,self.deployment)
        self.assertEqual([str(path) for path,_ in identities],[str(self.experiment),str(self.deployment)])
        self.assertEqual(list(plan['inputs']),[str(self.experiment),str(self.deployment)])

    def test_unreadable_input_after_the_read_fails_closed(self):
        document,digest=load_document_with_digest(self.experiment)
        self.experiment.unlink()
        with self.assertRaises(RuntimeError) as caught:verify_document_identity(self.experiment,digest)
        self.assertIn('unreadable after it was read',str(caught.exception))
        self.assertEqual(document['id'],'quad-rate-control-comparison')

    def test_matching_bytes_still_reach_the_mocked_execvp_boundary(self):
        execvp=mock.Mock()
        with mock.patch.object(run_experiment.os,'execvp',execvp),\
                mock.patch.object(run_experiment.sys,'platform','linux'):
            _,printed=self.run_cli(self.execute_argv([self.experiment,'--deployment',self.deployment]))
        self.assertEqual(execvp.call_count,1)
        launched=execvp.call_args.args[1]
        self.assertEqual(execvp.call_args.args[0],sys.executable)
        self.assertEqual(launched,[sys.executable,'tools/run_rate_control_comparison.py','--manifest',
                                   '/root/wksim-px4-inner-dfy6dfbk/candidate.json','--sha256',
                                   '89605a520e98e0bccd8024359b9e6af90c9371f992f48c983d01e61119bca830',
                                   '--algorithms','native','pid','lqr','mpc'])
        self.assertEqual(json.loads(printed)['inputs'][str(self.experiment)],
                         hashlib.sha256(self.original_experiment_bytes).hexdigest())

    def test_ground_execution_keeps_the_namespace_wrapper(self):
        deployment=EXAMPLES/'local-deployment.json';experiment=EXAMPLES/'ground-waypoints.json'
        execvp=mock.Mock()
        with mock.patch.object(run_experiment.os,'execvp',execvp),\
                mock.patch.object(run_experiment.sys,'platform','linux'):
            self.run_cli(self.execute_argv([experiment,'--deployment',deployment]))
        launched=execvp.call_args.args[1]
        self.assertEqual(launched[:8],['unshare','--net','--ipc','--mount','--propagation','private','bash','-c'])
        self.assertEqual(launched[9],'wksim-ground')
        self.assertEqual(launched[10:12],[sys.executable,'tools/run_rover_experiment.py'])
        self.assertIn('--path-controller',launched)

    def test_existing_resolved_output_stops_before_any_process(self):
        output=self.directory/'resolved.json';output.write_text('{"sentinel":true}',encoding='utf-8')
        execvp=mock.Mock()
        with mock.patch.object(run_experiment.os,'execvp',execvp),\
                mock.patch.object(run_experiment.sys,'platform','linux'):
            with self.assertRaises(FileExistsError):
                self.run_cli(self.execute_argv([self.experiment,'--deployment',self.deployment,
                                                '--resolved-output',output]))
        execvp.assert_not_called()
        self.assertEqual(output.read_text(encoding='utf-8'),'{"sentinel":true}')

    def test_illegal_configuration_never_starts_a_process(self):
        cases=(('{"x":1,"x":2}',ValueError),
               ('{"schema_version":NaN}',ValueError),
               ('{}',ValueError),
               ('{"schema_version":1,"id":"x","kind":"fixed_wing","vehicle_model":"quad_x",'
                '"firmware":"quad_rate_candidate"}',ValueError),
               ('{"schema_version":1,"id":"x","kind":"body_rate_comparison","vehicle_model":"quad_x",'
                '"firmware":"quad_rate_candidate","algorithms":["pID"]}',ValueError),
               ('{"schema_version":1,"id":"x","kind":"body_rate_comparison","vehicle_model":"fixed_wing",'
                '"firmware":"quad_rate_candidate","algorithms":["pid"]}',ValueError),
               ('{"schema_version":1,"id":"x","kind":"ground_waypoints","vehicle_model":"ackermann_v1",'
                '"firmware":"rover_candidate","algorithms":["pid"]}',ValueError))
        for text,error in cases:
            with self.subTest(text=text):
                self.experiment.write_text(text,encoding='utf-8')
                execvp=mock.Mock()
                with mock.patch.object(run_experiment.os,'execvp',execvp),\
                        mock.patch.object(run_experiment.sys,'platform','linux'):
                    with self.assertRaises(error):
                        self.run_cli(self.execute_argv([self.experiment,'--deployment',self.deployment]))
                execvp.assert_not_called()
        self.experiment.write_bytes(b'{"schema_version":1}\xff')
        execvp=mock.Mock()
        with mock.patch.object(run_experiment.os,'execvp',execvp):
            with self.assertRaises(UnicodeDecodeError):
                self.run_cli(self.execute_argv([self.experiment,'--deployment',self.deployment]))
        execvp.assert_not_called()

    def test_caller_input_mutation_cannot_rewrite_a_resolved_plan(self):
        intent=load_document(EXAMPLES/'rate-control.json')
        deployment=load_document(EXAMPLES/'local-deployment.json')
        plan=resolve(intent,deployment);snapshot=copy.deepcopy(plan)
        release=deployment['firmware_releases']['quad_rate_candidate']
        intent['id']='rewritten';intent['algorithms'].clear();intent['unexpected']=True
        release['manifest_linux']='/root/rewritten/candidate.json';release['manifest_sha256']='b'*64
        deployment['firmware_releases']['rover_candidate']['target']='plane'
        self.assertEqual(plan,snapshot)
        self.assertIsNot(plan['intent'],intent)
        self.assertIsNot(plan['deployment'],release)
        self.assertEqual(plan['intent']['algorithms'],['native','pid','lqr','mpc'])
        self.assertEqual(plan['deployment']['manifest_sha256'],
                         '89605a520e98e0bccd8024359b9e6af90c9371f992f48c983d01e61119bca830')
        plan['intent']['algorithms'].append('native');plan['deployment']['family']='rewritten'
        self.assertEqual(intent['algorithms'],[])
        self.assertEqual(release['family'],'px4')

    def test_real_examples_keep_the_original_dry_run_plan_shape(self):
        deployment=EXAMPLES/'local-deployment.json'
        for name,expected_id in EXAMPLES_AND_IDS:
            with self.subTest(name=name):
                experiment=EXAMPLES/name
                result,printed=self.run_cli([experiment,'--deployment',deployment])
                self.assertIsNone(result)
                plan=json.loads(printed)
                self.assertEqual(sorted(plan),['deployment','experiment_id','inputs','intent',
                                               'production_admitted','python_argv','schema_version'])
                self.assertEqual(plan['experiment_id'],expected_id)
                self.assertFalse(plan['production_admitted'])
                self.assertEqual(list(plan['inputs']),[str(experiment),str(deployment)])
                for path in (experiment,deployment):
                    self.assertEqual(plan['inputs'][str(path)],
                                     hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertIn('--manifest',plan['python_argv'])
                self.assertEqual(sorted(plan['deployment']),
                                 ['family','manifest_linux','manifest_sha256','target','vehicle_model'])
        _,printed=self.run_cli([EXAMPLES/'rate-disturbance.json','--deployment',deployment])
        self.assertIn('--motor-command-disturbance',json.loads(printed)['python_argv'])
        self.assertNotIn('--motor-command-disturbance',
                         json.loads(self.run_cli([EXAMPLES/'rate-control.json',
                                                  '--deployment',deployment])[1])['python_argv'])


if __name__=='__main__':unittest.main()
