"""The probe preserves exact writes and exceptions; it must not flush buffered data."""
import io
import json
from types import SimpleNamespace
import unittest
from Simulator.wksim_runtime.write_timing import WriteTiming


class WriteTimingTests(unittest.TestCase):
    def probe(self,wall=(100,2_000_100),cpu=(10,20)):
        sink=io.StringIO(); w=iter(wall);c=iter(cpu)
        return WriteTiming(sink,'a'*32,lambda:4,wall=lambda:next(w),cpu=lambda:next(c)),sink

    def test_preserves_payload_and_records_actual_write(self):
        probe,sink=self.probe();stream=io.StringIO();line='{"tick":4}\n'
        self.assertEqual(probe.write(stream,'wire',line),len(line))
        self.assertEqual(stream.getvalue(),line)
        row=json.loads(sink.getvalue());self.assertEqual(row['wall_ns'],2_000_000)
        self.assertEqual(row['thread_cpu_ns'],10);self.assertEqual(row['characters'],len(line))
        self.assertEqual(row['tick'],4)

    def test_fast_write_does_not_emit_a_sample(self):
        probe,sink=self.probe(wall=(1,100));probe.write(io.StringIO(),'rate','abc')
        self.assertEqual(sink.getvalue(),'');self.assertEqual(probe.summary()['calls'],{'rate':1})

    def test_failure_is_retained_and_propagated(self):
        probe,sink=self.probe()
        def fail(text):raise OSError('disk full')
        with self.assertRaisesRegex(OSError,'disk full'):probe.write(SimpleNamespace(write=fail),'wire','abc')
        self.assertIn('disk full',json.loads(sink.getvalue())['error'])

    def test_raw_offset_observation_does_not_flush(self):
        probe,sink=self.probe()
        class File(io.StringIO):
            buffer=SimpleNamespace(raw=SimpleNamespace(tell=lambda:65536))
            def flush(self):raise AssertionError('probe must not flush')
            def tell(self):raise AssertionError('text tell may flush')
        probe.write(File(),'wire','abc')
        self.assertEqual(json.loads(sink.getvalue())['raw_file_offset'],65536)


if __name__=='__main__':unittest.main()
