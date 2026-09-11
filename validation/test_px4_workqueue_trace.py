"""Portable unit tests for tools/check_px4_workqueue_trace.py extraction/parsing logic.

These exercise the verbatim-source slicer and the stderr trace parser without compiling —
the C++ compile/run is the WSL tool's job. A real-source extraction test runs only when the
candidate tree is reachable (WSL); everything else runs anywhere.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.check_px4_workqueue_trace import extract_blocks, parse_traces

HELPERS = """namespace {
bool wksim_wait_trace() { return true; }
long long wksim_wall_ns() { return 0; }
} // namespace
"""
ADD = """
void WorkQueue::Add(WorkItem *item)
{
	work_lock();
	_q.push(item);
	work_unlock();
	SignalWorkerThread();
}
"""
SIGNAL = """
void WorkQueue::SignalWorkerThread()
{
	int sem_val;
	if (px4_sem_getvalue(&_process_lock, &sem_val) == 0 && sem_val <= 0) {
		px4_sem_post(&_process_lock);
	}
}
"""

# Order inside Run: copy name -> Run() (item may self-delete) -> WORK trace uses the copy ->
# relock -> lockstep unregister -> work_unlock -> QUEUE trace. This is the invariant under test.
GOOD_RUN = """	while (!should_exit()) {
		WorkItem *work = _q.pop();
		char item_name[96] {};
		if (trace) { snprintf(item_name, sizeof(item_name), "%s", work->ItemName()); }
		work_unlock();
		work->RunPreamble();
		work->Run();
		if (trace) { fprintf(stderr, "WKSIM_PX4_WORK %s", item_name); }
		work_lock();
		if (_q.empty()) {
			px4_lockstep_unregister_component(_lockstep_component);
			_lockstep_component = -1;
		}
		work_unlock();
		if (trace) { fprintf(stderr, "WKSIM_PX4_QUEUE"); }
	}
"""


def source_with_run(run_body):
    return HELPERS + ADD + SIGNAL + "\nvoid WorkQueue::Run()\n{\n" + run_body + "\n}\n"


class ExtractTests(unittest.TestCase):
    def test_extracts_four_blocks_with_provenance(self):
        blocks = extract_blocks(source_with_run(GOOD_RUN))
        self.assertEqual(set(blocks), {'helpers', 'Add', 'SignalWorkerThread', 'Run'})
        for block in blocks.values():
            self.assertLessEqual(block['start'], block['end'])
        self.assertIn('wksim_wait_trace', blocks['helpers']['text'])
        self.assertTrue(blocks['Run']['text'].startswith('void WorkQueue::Run()'))

    def test_rejects_item_access_after_run(self):
        # The WORK trace must use the copied name, never the possibly-deleted item, after Run().
        bad = GOOD_RUN.replace('fprintf(stderr, "WKSIM_PX4_WORK %s", item_name)',
                               'fprintf(stderr, "WKSIM_PX4_WORK %s", work->ItemName())')
        with self.assertRaises(AssertionError):
            extract_blocks(source_with_run(bad))

    def test_rejects_queue_trace_before_unregister(self):
        # Moving the QUEUE trace ahead of the lockstep unregister breaks the ordering invariant.
        bad = GOOD_RUN.replace(
            'if (_q.empty()) {\n\t\t\tpx4_lockstep_unregister_component(_lockstep_component);\n\t\t\t_lockstep_component = -1;\n\t\t}\n\t\twork_unlock();\n\t\tif (trace) { fprintf(stderr, "WKSIM_PX4_QUEUE"); }',
            'if (trace) { fprintf(stderr, "WKSIM_PX4_QUEUE"); }\n\t\tif (_q.empty()) {\n\t\t\tpx4_lockstep_unregister_component(_lockstep_component);\n\t\t\t_lockstep_component = -1;\n\t\t}\n\t\twork_unlock();')
        with self.assertRaises(AssertionError):
            extract_blocks(source_with_run(bad))

    def test_rejects_component_reset_after_unlock(self):
        bad = GOOD_RUN.replace(
            '\t\t\t_lockstep_component = -1;\n\t\t}\n\t\twork_unlock();',
            '\t\t}\n\t\twork_unlock();\n\t\t_lockstep_component = -1;')
        with self.assertRaises(AssertionError):
            extract_blocks(source_with_run(bad))


class ParseTests(unittest.TestCase):
    def test_parse_work_and_queue(self):
        stderr = ('WKSIM_PX4_WORK {"duration_ns":3110758,"item":"wq_smoke_item"}\n'
                  'WKSIM_PX4_QUEUE {"duration_ns":3185353,"items":1}\n')
        traces = parse_traces(stderr)
        self.assertEqual(traces['work'][0]['item'], 'wq_smoke_item')
        self.assertEqual(traces['queue'][0]['items'], 1)

    def test_parse_preserves_two_batch_ready_order(self):
        stderr = ('WKSIM_PX4_QUEUE {"ready_mono_ns":100,"items":1}\n'
                  'WKSIM_PX4_QUEUE {"ready_mono_ns":200,"items":1}\n')
        queues = parse_traces(stderr)['queue']
        self.assertEqual([row['ready_mono_ns'] for row in queues], [100, 200])


REAL = Path('/root/wksim-px4-component-ZNq7Mp/src/platforms/common/px4_work_queue/WorkQueue.cpp')


@unittest.skipUnless(REAL.is_file(), 'candidate tree reachable only in WSL')
class RealSourceTests(unittest.TestCase):
    def test_real_blocks_and_provenance(self):
        blocks = extract_blocks(REAL.read_text())
        self.assertTrue(blocks['Add']['text'].startswith('void WorkQueue::Add('))
        self.assertTrue(blocks['SignalWorkerThread']['text'].startswith('void WorkQueue::SignalWorkerThread('))
        self.assertIn('WKSIM_PX4_WORK', blocks['Run']['text'])
        self.assertIn('WKSIM_PX4_QUEUE', blocks['Run']['text'])


if __name__ == '__main__':
    unittest.main()
