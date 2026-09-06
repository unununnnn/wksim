"""Regression: invalid startup telemetry must not hide the primary failure."""
import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
from run_joint_flight import save


class EvidenceTests(unittest.TestCase):
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
