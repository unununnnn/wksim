"""Control-flow tests for the explicit release experiment; no ROS or FC."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from planner_release_task import PlannerReleaseTask

class Setup:
    SET_PX4_MODE=1
    def __init__(self,**fields): self.__dict__.update(fields)

class ReleaseTaskFlowTests(unittest.TestCase):
    def driver(self,stack):
        task=object.__new__(PlannerReleaseTask)
        events=[]
        task.flight_stack=stack
        task.Setup=Setup
        task.Cmd=SimpleNamespace(LAND=3,EXIT_ABSOLUTE_CONTROL=2)
        task.prepare=lambda:events.append(('prepare',))
        task.fly_until_release=lambda:events.append(('moving_release',))
        task.fly_leg=lambda leg:events.append(('companion_leg',leg))
        task.send=lambda message,label:events.append(('setup',message.px4_mode,label))
        task.offer=lambda label,**fields:events.append(('command',label,fields))
        task.wait=lambda label,predicate,timeout=20:events.append(('wait',label,timeout))
        task.execute()
        return events

    def test_ap_uses_public_auto_land_after_release(self):
        events=self.driver('arducopter')
        self.assertEqual(events[:2],[('prepare',),('moving_release',)])
        self.assertEqual([e[1] for e in events if e[0]=='setup'],['AUTO.LAND','AUTO.LOITER'])
        self.assertFalse(any(e[0]=='command' for e in events))
        self.assertIn(('wait','landed_disarmed_public',30),events)
        self.assertEqual(events[-1][1],'normal_stop_ready')

    def test_px4_companion_retains_first_leg_and_absolute_exit_land(self):
        events=self.driver('px4')
        self.assertEqual(events[:2],[('prepare',),('companion_leg',1)])
        command=next(e for e in events if e[0]=='command')
        self.assertEqual(command[2],dict(agent_cmd=3,control_level=2))
        self.assertEqual([e[1] for e in events if e[0]=='setup'],['AUTO.LOITER'])

class ReleaseCliTests(unittest.TestCase):
    def test_release_requires_explicit_pv_profile_before_execution(self):
        import contextlib, io
        import run_joint_flight as runner
        from unittest.mock import patch
        with patch.object(runner, 'run') as execute, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                runner.main(['run','--planner-release-proof','--control-manifest','unused','--control-sha256','unused'])
            self.assertEqual(error.exception.code, 2)
            execute.assert_not_called()

    def test_explicit_release_reaches_runner_without_changing_nominal_default(self):
        import run_joint_flight as runner
        from unittest.mock import patch
        args=['run','--control-manifest','control','--control-sha256','sha',
              '--ap-mixed-manifest','ap','--ap-mixed-sha256','sha',
              '--message-manifest','message','--message-sha256','sha',
              '--task-profile',runner.PV_PROFILE]
        with patch.object(runner,'run',return_value=0) as execute:
            self.assertEqual(runner.main(args),0)
            self.assertFalse(execute.call_args.args[0].planner_release_proof)
            self.assertEqual(runner.main(args+['--planner-release-proof']),0)
            self.assertTrue(execute.call_args.args[0].planner_release_proof)

class PlannerProvenanceTests(unittest.TestCase):
    def test_actual_child_modules_must_match_candidate_paths_and_bytes(self):
        import tempfile, hashlib
        import run_joint_flight as runner
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            package=base/'prometheus_control'
            package.mkdir()
            modules={}
            hashes={}
            for module in ('planner_transport_node','planner_transport_receiver','planner_command_egress'):
                relative='wksim_runtime/'+module+'.py'
                path=base/'Simulator'/relative
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text('# test '+module)
                sha=hashlib.sha256(path.read_bytes()).hexdigest()
                hashes[relative]=sha
                modules['Simulator.wksim_runtime.'+module]={'path':str(path),'sha256':sha}
            release={'child_returncode':0,'child_teardown':'terminated','planner_loaded_modules':modules}
            report={'task':{'release':release}}
            control={'package':str(package),'simulator_python_sha256':hashes}
            self.assertEqual(runner.verify_planner_execution(report,control),modules)
            path.write_text('# tampered after child exit')
            with self.assertRaisesRegex(ValueError,'differs from sealed'):
                runner.verify_planner_execution(report,control)
            release['child_returncode']=-9
            with self.assertRaisesRegex(ValueError,'exit normally'):
                runner.verify_planner_execution(report,control)

if __name__=='__main__':unittest.main()
