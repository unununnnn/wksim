import json
from pathlib import Path
import unittest
from tools.analyze_px4_component_trace import parse,analyze


class NativeTraceTests(unittest.TestCase):
    def send(self,**changes):
        value=dict(start_mono_ns=100,end_mono_ns=150,poll_ns=20,prepare_ns=5,
                   component_ns=20,send_ns=5,pret=1,revents=1,hrt_us=9388000)
        value.update(changes)
        return 'WKSIM_PX4_SEND '+json.dumps(value)

    def test_exact_stages_and_real_clock(self):
        self.assertEqual(parse(self.send(),1)['component_ns'],20)
        for change in ({'end_mono_ns':151},{'start_mono_ns':0},{'poll_ns':True},
                       {'component_ns':-1},{'pret':0}):
            with self.assertRaises(ValueError):parse(self.send(**change),1)

    def test_timeout_does_not_invent_other_stages(self):
        row=parse(self.send(end_mono_ns=120,prepare_ns=0,component_ns=0,send_ns=0,pret=0,revents=0),2)
        self.assertEqual(row['pret'],0)

    def test_unrelated_log_is_not_a_trace(self):
        self.assertIsNone(parse('INFO [logger] ready',1))

    def test_real_native_barrier_probe(self):
        path=Path(__file__).resolve().parents[1]/'validation/px4-component-barrier-01/on.stderr'
        report=analyze(path)
        self.assertEqual(report['status'],'observed')
        self.assertEqual(report['counts'],dict(send=0,component=1,register=2))


if __name__=='__main__':unittest.main()
