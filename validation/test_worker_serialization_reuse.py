"""Actual worker function with fake Model/in-memory pipes; no native resource."""
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Simulator.wksim_core import worker

EPOCH='a'*32


class MemoryFile(io.StringIO):
    def close(self):
        pass


class FakeModel:
    def __init__(self):
        self.ticks=0
        self.state=[-0.0,1e-250,1e250]+[.125]*117
        self.closed=False
    def __enter__(self): return self
    def __exit__(self,*args): self.closed=True
    def step(self,commands):
        self.ticks+=1
        return self.state


class SerializationReuse(unittest.TestCase):
    def setUp(self):
        self.model=FakeModel()
        self.stdin,self.stdout,self.trace=MemoryFile(),MemoryFile(),MemoryFile()
        self.calls=[]
        self.original_encoded=worker.encoded
        def encoded(value):
            self.calls.append(value)
            return self.original_encoded(value)
        for change in (patch.object(worker,'_started',False),patch.object(worker,'Model',lambda path:self.model),
                       patch.object(worker,'Path',lambda path:SimpleNamespace(open=lambda *a,**k:self.trace)),
                       patch.object(worker,'sys',SimpleNamespace(stdin=self.stdin,stdout=self.stdout)),
                       patch.object(worker,'encoded',encoded)):
            change.start()
            self.addCleanup(change.stop)

    def run_requests(self,requests):
        self.stdin.write(''.join(self.original_encoded(request)+'\n' for request in requests))
        self.stdin.seek(0)
        worker.model_worker('fake-never-loaded','in-memory-trace',EPOCH)

    def step(self):
        return dict(version=1,epoch=EPOCH,tick=1,commands=[-0.0,1]+[0.]*14)

    def test_step_and_snapshots_preserve_bytes_with_one_state_encode_per_response(self):
        initial=dict(version=1,epoch=EPOCH,tick=0,state=None)
        step=self.step()
        response=dict(initial,tick=1,state=self.model.state)
        snapshot=dict(version=1,epoch=EPOCH,snapshot=True)
        self.run_requests([snapshot,step,snapshot])
        self.assertEqual(self.stdout.getvalue(), ''.join(self.original_encoded(r)+'\n' for r in (initial,response,response)))
        expected=dict(**response,commands=step['commands'],input=self.original_encoded(step)+'\n',request=step)
        self.assertEqual(self.trace.getvalue(),self.original_encoded(expected)+'\n')
        self.assertEqual(sum(isinstance(r.get('state'),list) for r in self.calls),2)
        self.assertTrue(self.model.closed)

    def test_log_write_failure_propagates_before_response(self):
        with patch.object(self.trace,'write',side_effect=OSError('log failed')):
            with self.assertRaisesRegex(OSError,'log failed'):
                self.run_requests([self.step()])
        self.assertEqual(self.stdout.getvalue(),'')
        self.assertTrue(self.model.closed)

    def test_extras_serialization_failure_has_no_trace_or_response(self):
        def fail(value):
            if 'input' in value: raise TypeError('extras encoding failed')
            return self.original_encoded(value)
        with patch.object(worker,'encoded',fail),self.assertRaisesRegex(TypeError,'extras encoding failed'):
            self.run_requests([self.step()])
        self.assertEqual(self.trace.getvalue(),'')
        self.assertEqual(self.stdout.getvalue(),'')
        self.assertTrue(self.model.closed)

    def test_nonfinite_state_serialization_failure_has_no_trace_or_response(self):
        self.model.state[0]=float('nan')
        with self.assertRaises(ValueError): self.run_requests([self.step()])
        self.assertEqual(self.trace.getvalue(),'')
        self.assertEqual(self.stdout.getvalue(),'')

    def test_invalid_state_preserves_trace_before_validation_failure(self):
        self.model.state=self.model.state[:119]
        with self.assertRaisesRegex(ValueError,'Invalid model state'): self.run_requests([self.step()])
        self.assertIn('"tick":1',self.trace.getvalue())
        self.assertEqual(self.stdout.getvalue(),'')

    def test_output_limit_still_prevents_publication_after_log(self):
        with patch.object(worker,'RESPONSE_LIMIT',1),self.assertRaisesRegex(ValueError,'Oversized response'):
            self.run_requests([self.step()])
        self.assertTrue(self.trace.getvalue().endswith('\n'))
        self.assertEqual(self.stdout.getvalue(),'')

    def test_second_lifetime_still_rejected(self):
        self.run_requests([])
        with self.assertRaisesRegex(RuntimeError,'Only one Model lifetime'):
            worker.model_worker('fake-never-loaded','in-memory-trace',EPOCH)


if __name__=='__main__': unittest.main()
