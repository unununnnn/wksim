"""Diagnostic intervals must not change physical/clock ordering or hide errors."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from Simulator.wksim_runtime.loop_timing import LoopTiming
from Simulator.wksim_runtime.joint_rate import RateUnmet


class LoopTimingTests(unittest.TestCase):
    def test_disabled_reads_no_clocks_and_emits_nothing(self):
        def forbidden(*a,**k):raise AssertionError('disabled probe performed work')
        p=LoopTiming(False,forbidden,forbidden,forbidden)
        p.start();p.mark('physics');p.finish(250,complete=False)

    def test_intended_pacing_alone_does_not_trigger_slow_record(self):
        wall=iter((0,8_000_000,8_001_000));cpu=iter((0,100,500));rows=[]
        p=LoopTiming(True,lambda *a,**k:rows.append(k),lambda:next(wall),lambda:next(cpu))
        p.start();p.mark('pacing');p.mark('physics');p.finish(1,complete=True)
        self.assertEqual(rows,[])
        p.finish(250,complete=True)
        self.assertEqual(rows[0]['stages']['pacing']['wall_ns'],8_000_000)
        self.assertEqual(rows[0]['stages']['physics']['thread_cpu_ns'],400)

    def test_partial_slow_interval_preserves_raw_cpu_measurement(self):
        wall=iter((3_000_000,));cpu=iter((3_000_010,));rows=[]
        p=LoopTiming(True,lambda *a,**k:rows.append(k),lambda:next(wall),lambda:next(cpu))
        p.start((0,0));p.mark('clock_publish');p.finish(17,complete=False)
        self.assertFalse(rows[0]['complete'])
        self.assertEqual(rows[0]['stages']['clock_publish']['thread_cpu_ns'],3_000_010)


def advance_fixture(enabled, *, tick=0, failure=None, fail_record=False, untimed=False):
    source=Path(__file__).resolve().parents[1]/'Simulator/wksim_runtime/joint_runtime.py'
    tree=ast.parse(source.read_text())
    fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='advance')
    fn.body=[ast.copy_location(ast.Global(names=n.names),n) if isinstance(n,ast.Nonlocal) else n
             for n in fn.body]
    events=[];records=[];result={}
    clock=NS(tick=tick,phase='stepping' if untimed else 'running',synchronized=True,snapshot=lambda:{'tick':clock.tick})
    def pacing(*a):
        events.append('pacing')
        if failure=='pacing':raise RateUnmet(100_000_001)
    def physics():
        events.append('physics');clock.tick+=1;return {'state':'unchanged'}
    def group_end(*a):
        events.append('group_end')
        if failure=='group_end':raise RateUnmet(100_000_002)
    def record(*a,**k):
        if fail_record:raise OSError('diagnostic disk failure')
        records.append(k)
    counter=iter(range(0,100_000_000,1_000_000))
    scope=dict(loop_timing=LoopTiming(enabled,record,lambda:next(counter),lambda:next(counter)),
        clock=clock,physics_wait_started=None,pending_task_reanchor=False,
        rate=NS(anchor={},latched=False,group=None if untimed else True,begin_group=pacing,end_group=group_end),
        lifecycle=NS(phase='paused' if untimed else 'running'),physics_health=lambda:None,
        physics=NS(advance=physics),publisher=NS(publish=lambda c:events.append('clock')),
        record_clock=lambda value:events.append(('clock_evidence',value)),
        view=NS(emit=lambda *a:events.append('view')),time=NS(monotonic=lambda:10,monotonic_ns=lambda:10_000_000_000),result=result,json=json,
        record_rate=lambda kind,**fields:events.append((kind,fields)))
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(source),'exec'),scope)
    return scope['advance'],events,records,result


class AdvanceOrderTests(unittest.TestCase):
    def test_existing_untimed_end_classification_is_preserved(self):
        fn,events,records,result=advance_fixture(False,tick=3,untimed=True)
        fn()
        end=next(fields for item in events if isinstance(item,tuple) and item[0]=='untimed_group_end'
                 for fields in [item[1]])
        self.assertEqual(end['classification'],'bootstrap')

    def test_disabled_and_enabled_keep_operation_order_and_payload(self):
        traces=[]
        for enabled in (False,True):
            fn,events,records,result=advance_fixture(enabled)
            self.assertEqual(fn(),{'state':'unchanged'})
            traces.append(events)
        self.assertEqual(traces[0],traces[1])
        self.assertEqual(traces[0],['pacing','physics','clock',('clock_evidence','{"tick":1}\n')])

    def test_group_end_failure_remains_primary_if_diagnostic_write_fails(self):
        fn,events,records,result=advance_fixture(True,tick=3,failure='group_end',fail_record=True)
        with self.assertRaises(RateUnmet) as caught:fn()
        self.assertEqual(caught.exception.lateness_ns,100_000_002)
        self.assertNotIn('view',events)
        self.assertEqual(result['evidence_errors'][0]['stream'],'runtime-timing')

    def test_pacing_failure_does_not_advance_physics(self):
        fn,events,records,result=advance_fixture(True,failure='pacing')
        with self.assertRaises(RateUnmet):fn()
        self.assertEqual(events,['pacing'])
        self.assertFalse(records[0]['complete'])

    def test_diagnostic_failure_after_success_is_not_silenced(self):
        fn,events,records,result=advance_fixture(True,fail_record=True)
        with self.assertRaisesRegex(OSError,'diagnostic disk'):fn()
        self.assertTrue(result['evidence_errors'])


if __name__=='__main__':unittest.main()
