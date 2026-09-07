"""Regression: invalid startup telemetry must not hide the primary failure."""
import ast
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
from run_joint_flight import save


class EvidenceTests(unittest.TestCase):
    def test_handoff_readers_never_see_an_incomplete_json_file(self):
        for previous in (None, {'epoch':'old'}):
            with self.subTest(previous=previous), tempfile.TemporaryDirectory() as directory:
                target=Path(directory)/'go.json'
                if previous is not None:
                    target.write_text(json.dumps(previous))
                original_open=Path.open
                original_fdopen=os.fdopen
                observed=[]
                def observe(mode):
                    if 'w' in mode:
                        if target.exists():
                            with original_open(target) as reader:
                                observed.append(reader.read())
                        else:
                            observed.append(None)
                def observe_open(file,mode='r',*args,**kwargs):
                    stream=original_open(file,mode,*args,**kwargs)
                    observe(mode)
                    return stream
                def observe_fdopen(fd,mode='r',*args,**kwargs):
                    stream=original_fdopen(fd,mode,*args,**kwargs)
                    observe(mode)
                    return stream
                with patch.object(Path,'open',new=observe_open), patch('os.fdopen',side_effect=observe_fdopen):
                    save(target,{'epoch':'new'})
                self.assertTrue(observed)
                self.assertEqual([json.loads(value) if value is not None else None for value in observed],
                                 [previous]*len(observed))
                self.assertEqual(json.loads(target.read_text()),{'epoch':'new'})

    def test_preserves_invalid_numbers_without_filling_zero_or_losing_error(self):
        old=REPO/'validation/joint-public-flight-onnyn2l_/source__tools__run_joint_flight.py.txt'
        tree=ast.parse(old.read_text())
        fn=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='save')
        module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
        scope={'json':json,'Path':Path}
        exec(compile(module,str(old),'exec'),scope)
        sample=dict(status='failed',error='primary diagnostic',state=dict(position=[1.,2.,3.],
                    global_position=[float('nan'),float('inf'),-float('inf')]))
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'result.json'
            with self.assertRaises(ValueError):
                scope['save'](target,sample)
            save(target,sample)
            data=json.loads(target.read_text(),parse_constant=lambda value: self.fail('Nonstandard JSON number'))
            self.assertEqual(data['error'],'primary diagnostic')
            self.assertEqual(data['state']['position'],[1.,2.,3.])
            self.assertEqual(data['state']['global_position'],[
                {'nonfinite_number':'nan'},{'nonfinite_number':'inf'},{'nonfinite_number':'-inf'}])


if __name__=='__main__': unittest.main()
