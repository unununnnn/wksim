import json
from pathlib import Path
import tempfile
import unittest

from tools.rate_fault_physics import ScheduledFault,publish_event


class RateFaultTests(unittest.TestCase):
    def test_publication_is_complete_and_never_overwrites_an_event(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'event.json'
            event=dict(schema='wksim.rate-actuator-fault.v1',channel=0,start_tick=40,end_tick=1040,multiplier=.97)
            digest=publish_event(path,event)
            self.assertEqual(json.loads(path.read_text()),event)
            fault=ScheduledFault(path);fault.apply([.5]*16,0)
            self.assertEqual(fault.sha256,digest)
            with self.assertRaises(FileExistsError):publish_event(path,event)
    def test_exact_model_interval_and_only_declared_channel(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'event.json'
            path.write_text(json.dumps(dict(schema='wksim.rate-actuator-fault.v1',channel=0,start_tick=40,end_tick=1040,multiplier=.97)))
            fault=ScheduledFault(path);active=[];commands=[.5]*16
            for tick in range(1100):
                applied,on=fault.apply(commands,tick)
                self.assertEqual(applied[1:],commands[1:])
                self.assertEqual(applied[0],.485 if 40<=tick<1040 else .5)
                if on:active.append(tick)
            self.assertEqual(active,list(range(40,1040)))
            self.assertEqual(fault.applied,1000)
            self.assertEqual(commands,[.5]*16)

    def test_late_and_mutated_events_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'event.json'
            data=dict(schema='wksim.rate-actuator-fault.v1',channel=0,start_tick=40,end_tick=1040,multiplier=.97)
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):ScheduledFault(path).apply([.5]*16,60)
            fault=ScheduledFault(path);fault.apply([.5]*16,0)
            path.write_text(json.dumps(dict(data,multiplier=.96)))
            with self.assertRaises(ValueError):fault.apply([.5]*16,20)
