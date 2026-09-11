"""Actual worker function with fake Model/in-memory pipes; no native resource."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
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

    def test_initial_state_read_is_one_shot_audited_and_never_steps(self):
        self.model.initial_state=lambda: [2.5]*120
        request=dict(version=1,epoch=EPOCH,initial=True)
        snapshot=dict(version=1,epoch=EPOCH,snapshot=True)
        self.run_requests([request,snapshot])
        initial=dict(version=1,epoch=EPOCH,tick=0,state=[2.5]*120,initial=True)
        frozen=dict(version=1,epoch=EPOCH,tick=0,state=None)
        self.assertEqual(self.stdout.getvalue(),
                         ''.join(self.original_encoded(r)+'\n' for r in (initial,frozen)))
        self.assertEqual(self.model.ticks,0)
        # The sidecar sink is patched onto the same in-memory trace here; the
        # row carries the explicit flag plus the exact accepted request bytes.
        expected=dict(**initial,input=self.original_encoded(request)+'\n',request=request)
        self.assertEqual(self.trace.getvalue(),self.original_encoded(expected)+'\n')

    def test_second_initial_state_request_fails_closed(self):
        self.model.initial_state=lambda: [2.5]*120
        request=dict(version=1,epoch=EPOCH,initial=True)
        self.stdin.write(self.original_encoded(request)+'\n'+self.original_encoded(request)+'\n')
        self.stdin.seek(0)
        with self.assertRaisesRegex(ValueError,'already observed'):
            worker.model_worker('fake-never-loaded','in-memory-trace',EPOCH)
        initial=dict(version=1,epoch=EPOCH,tick=0,state=[2.5]*120,initial=True)
        self.assertEqual(self.stdout.getvalue(),self.original_encoded(initial)+'\n')

    def test_missing_initial_state_method_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,'initial-state ABI'):
            self.run_requests([dict(version=1,epoch=EPOCH,initial=True)])
        self.assertEqual(self.stdout.getvalue(),'')
        self.assertTrue(self.model.closed)

    def test_initial_state_after_step_fails_closed_in_loop(self):
        self.model.initial_state=lambda: [2.5]*120
        self.stdin.write(''.join(self.original_encoded(r)+'\n'
                                 for r in (self.step(),dict(version=1,epoch=EPOCH,initial=True))))
        self.stdin.seek(0)
        with self.assertRaisesRegex(ValueError,'tick zero'):
            worker.model_worker('fake-never-loaded','in-memory-trace',EPOCH)
        self.assertEqual(self.model.ticks,1)

    def test_invalid_initial_state_has_no_sidecar_or_response(self):
        self.model.initial_state=lambda: [2.5]*119
        with self.assertRaisesRegex(ValueError,'Invalid initial model state'):
            self.run_requests([dict(version=1,epoch=EPOCH,initial=True)])
        self.assertEqual(self.trace.getvalue(),'')
        self.assertEqual(self.stdout.getvalue(),'')
        self.assertTrue(self.model.closed)


class AsyncEvidenceIdentity(unittest.TestCase):
    def setUp(self):
        self.model=FakeModel()
        self.started=patch.object(worker,'_started',False)
        self.started.start()
        self.addCleanup(self.started.stop)
        self.model_patch=patch.object(worker,'Model',lambda path:self.model)
        self.model_patch.start()
        self.addCleanup(self.model_patch.stop)

    def run_worker(self, library, trace):
        request=dict(version=1,epoch=EPOCH,tick=1,commands=[0.0]*16)
        stdin=io.StringIO(worker.encoded(request)+'\n')
        stdout=io.StringIO()
        with patch.object(worker,'sys',SimpleNamespace(stdin=stdin,stdout=stdout)):
            worker.model_worker(library, trace, EPOCH, async_evidence=True)

    def test_writer_sidecar_records_closed_stream_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            library=root/'model.so'
            library.write_bytes(b'model-library')
            trace=root/'truth.jsonl'
            self.run_worker(library, trace)

            summary=json.loads((root/'truth.jsonl.writer.json').read_text())
            self.assertEqual(summary['epoch'],EPOCH)
            self.assertEqual(summary['truth_trace_sha256'],
                             hashlib.sha256(trace.read_bytes()).hexdigest())
            self.assertEqual(summary['model_library'],str(library.resolve()))
            self.assertEqual(summary['model_library_sha256'],
                             hashlib.sha256(library.read_bytes()).hexdigest())
            if hasattr(worker.os,'sched_setscheduler'):
                self.assertEqual(summary['writer_scheduler'],dict(
                    available=True,policy='SCHED_OTHER',priority=0,
                    actual_policy=worker.os.SCHED_OTHER,actual_priority=0))
            self.assertTrue(summary['complete'])
            self.assertFalse(summary['alive'])
            self.assertTrue(summary['closed'])
            self.assertIsNone(summary['error'])

    def test_digest_failure_does_not_publish_sidecar(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            library=root/'model.so'
            library.write_bytes(b'model-library')
            trace=root/'truth.jsonl'
            with patch.object(worker,'_sha256_file',side_effect=OSError('digest failed')):
                with self.assertRaisesRegex(OSError,'digest failed'):
                    self.run_worker(library, trace)
            self.assertFalse((root/'truth.jsonl.writer.json').exists())


if __name__=='__main__': unittest.main()
