"""Observer must preserve original decisions, calls, exceptions and class restoration."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from tools.observe_px4_setup import install


class Link:
    def __init__(self,node):
        self.node=node;self.latest={};self.received={};self.last_clock=0.;self.clock_invalid=False
        self.stale_seconds=2.;self.receive_calls=self.fresh_calls=0
    def receive(self,key,message):
        self.receive_calls+=1;self.latest[key]=message;self.received[key]=self.last_clock
        return 'received'
    def fresh(self,*keys):
        self.fresh_calls+=1
        return all(k in self.latest and 0<=self.last_clock-self.received[k]<=self.stale_seconds for k in keys)


class Node:
    def __init__(self):
        self.processor=SimpleNamespace(home=[0.,0.,0.])
        self.state=SimpleNamespace(armed=True,odom_valid=True)
        self.native=Link(self);self.events=[];self.setup_calls=0;self.fail=False
    def event(self,name,*,error=False,**fields):
        self.events.append((name,error,fields));return 'event'
    def on_setup(self,message):
        self.setup_calls+=1
        if self.fail:raise RuntimeError('original failure')
        if self.processor.home is None or not self.native.fresh('land'):
            self.event('setup_rejected',error=True,reason='missing_home_or_landed_state')
            return False
        self.event('setup_received',cmd=message.cmd);return True


class SetupObserverTests(unittest.TestCase):
    def test_captures_exact_stale_land_decision_without_extra_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'trace.jsonl';close=install(path,Node,Link)
            try:
                node=Node();message=SimpleNamespace(timestamp=1000,landed=True)
                self.assertEqual(node.native.receive('land',message),'received')
                node.native.last_clock=2.01
                self.assertIs(node.on_setup(SimpleNamespace(cmd=3)),False)
                self.assertEqual((node.setup_calls,node.native.receive_calls,node.native.fresh_calls),(1,1,1))
                rows=[json.loads(l) for l in path.read_text().splitlines()]
                self.assertFalse(rows[-1]['processor_home_missing'])
                self.assertFalse(rows[-1]['freshness'][0]['result'])
                self.assertEqual(rows[-1]['freshness'][0]['ages_s']['land'],2.01)
                self.assertEqual(rows[-1]['events'][0]['reason'],'missing_home_or_landed_state')
            finally:close()
    def test_home_short_circuit_does_not_fabricate_freshness_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'trace.jsonl';close=install(path,Node,Link)
            try:
                node=Node();node.processor.home=None
                self.assertIs(node.on_setup(SimpleNamespace(cmd=3)),False)
                row=json.loads(path.read_text().splitlines()[-1])
                self.assertTrue(row['processor_home_missing']);self.assertEqual(row['freshness'],[])
                self.assertEqual(node.native.fresh_calls,0)
            finally:close()
    def test_exception_propagates_and_original_methods_are_restored(self):
        old=(Node.on_setup,Node.event,Link.fresh,Link.receive)
        with tempfile.TemporaryDirectory() as tmp:
            close=install(Path(tmp)/'trace.jsonl',Node,Link)
            node=Node();node.fail=True
            try:
                with self.assertRaisesRegex(RuntimeError,'original failure'):node.on_setup(SimpleNamespace(cmd=3))
            finally:close();close()
        self.assertEqual((Node.on_setup,Node.event,Link.fresh,Link.receive),old)


if __name__=='__main__':unittest.main()
