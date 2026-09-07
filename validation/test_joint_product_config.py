"""Pure configuration and explicit action identity; no flight substitutions."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace as NS

from Simulator.wksim_runtime.config import validate_config,ConfigError,load_config
from Simulator.wksim_runtime.evidence import write_json
from Simulator.wksim_runtime.joint_actions import submit,Mailbox
from Simulator.wksim_runtime.isolation import keys
from Simulator.wksim_runtime.joint_monitor import JointMonitor


class JointConfigTests(unittest.TestCase):
    def test_pause_requires_both_current_settled_task_owners(self):
        monitor=NS(ready=lambda run_id:True,sessions={
            1:NS(state=NS(armed=True,mode='GUIDED'),control=NS(control_state=2,COMMAND_CONTROL=2,failsafe=False)),
            2:NS(state=NS(armed=True,mode='AUTO.TAKEOFF'),control=NS(control_state=0,COMMAND_CONTROL=2,failsafe=False))})
        self.assertFalse(JointMonitor.can_pause(monitor,'joint'))
        monitor.sessions[2].state.mode='OFFBOARD'
        self.assertFalse(JointMonitor.can_pause(monitor,'joint'))
        monitor.sessions[2].control.control_state=2
        self.assertTrue(JointMonitor.can_pause(monitor,'joint'))
        monitor.sessions[1].control.failsafe=True
        self.assertFalse(JointMonitor.can_pause(monitor,'joint'))

    def test_joint_and_legacy_have_distinct_contracts(self):
        value=dict(schema_version=1,kind='joint_scene',run_id='formal-joint',runtime_profile='joint_quad_dds_v1')
        self.assertEqual(validate_config(value)['task'],'public_position')
        for changes in ({'schema_version':True},{'task':'pretend_trajectory'},{'rate':2},{'run_id':'../other'}):
            with self.subTest(changes=changes),self.assertRaises(ConfigError):
                validate_config(dict(value,**changes))
        self.assertNotIn('task',value)

    def test_duplicate_json_and_shared_resource_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'config.json'
            path.write_text('{"kind":"joint_scene","kind":"joint_scene"}')
            with self.assertRaises(ConfigError): load_config(path)
        resource=dict(experiment_kind='joint',network_namespace='net:[private]',run_id='joint',output='/tmp/joint')
        self.assertEqual(keys(resource),[('run_id','joint'),('output','/tmp/joint')])


class JointActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        (self.root/'actions').mkdir();(self.root/'action-results').mkdir()
        self.epoch='a'*32;self.offer='b'*32
        self.status(self.epoch,self.offer)

    def tearDown(self): self.tmp.cleanup()

    def status(self,epoch,offer,**fields):
        write_json(self.root/'status.json',dict(version=1,run_id='joint',epoch=epoch,offer_token=offer,
            allowed_actions=['pause','stop'],issued_monotonic_s=time.monotonic(),**fields))

    def test_submit_is_not_completion_and_never_executes_twice(self):
        response=submit(self.root,'pause',self.epoch)
        self.assertEqual(response['state'],'submitted')
        reader=Mailbox(self.root,'joint',self.epoch)
        request=reader.poll(self.offer,['pause','stop'])
        self.assertEqual(json.loads(Path(response['result_file']).read_text())['state'],'accepted')
        reader.respond(request,'completed',effect='paused')
        self.assertIsNone(reader.poll(self.offer,['pause']))
        self.assertEqual(json.loads(Path(response['result_file']).read_text())['state'],'completed')

    def test_cold_reset_rejects_old_queue_without_overwriting_old_result(self):
        response=submit(self.root,'pause',self.epoch)
        old=Mailbox(self.root,'joint',self.epoch)
        request=old.poll(self.offer,['pause']);old.respond(request,'completed')
        self.status('c'*32,'d'*32)
        new=Mailbox(self.root,'joint','c'*32)
        self.assertIsNone(new.poll('d'*32,['pause']))
        self.assertTrue(list(new.results.glob('rejected-*')))
        self.assertEqual(json.loads(Path(response['result_file']).read_text())['state'],'completed')
        with self.assertRaises(ValueError): submit(self.root,'pause',self.epoch)

    def test_stale_offer_and_unknown_action_do_not_execute(self):
        submitted=submit(self.root,'pause')
        reader=Mailbox(self.root,'joint',self.epoch)
        self.assertIsNone(reader.poll('e'*32,['pause']))
        self.assertEqual(json.loads(Path(submitted['result_file']).read_text())['state'],'rejected')
        with self.assertRaises(ValueError): submit(self.root,'takeover')

    def test_waiting_transport_does_not_consume_a_nonurgent_action(self):
        submitted=submit(self.root,'pause')
        reader=Mailbox(self.root,'joint',self.epoch)
        self.assertIsNone(reader.poll(self.offer,['stop'],only={'stop'}))
        self.assertFalse(Path(submitted['result_file']).exists())
        self.assertEqual(reader.poll(self.offer,['pause'])['action'],'pause')

    def test_malformed_request_and_reused_token_are_rejected(self):
        response=submit(self.root,'pause')
        reader=Mailbox(self.root,'joint',self.epoch)
        value=reader.poll(self.offer,['pause']);reader.respond(value,'completed')
        value=dict(value,command_id=value['command_id']+1)
        write_json(self.root/'actions'/f"{value['command_id']:020d}-{value['token']}.json",value)
        self.assertIsNone(reader.poll(self.offer,['pause']))
        self.assertEqual(json.loads(Path(response['result_file']).read_text())['state'],'completed')


if __name__=='__main__': unittest.main()
