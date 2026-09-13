"""Pure offline tests for tools/map_reference_blocks.py.

Builds a synthetic SLX-shaped ZIP (real temp files) and checks the structural
extraction: typed I/O SIDs, the 6DOF library-linked reference block, and the
library integrator SIDs. No MATLAB, no model run, no vendor source copied.
"""
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile
from unittest.mock import patch
import sys

from tools import map_reference_blocks as mrb

ROOT_XML = '''<?xml version="1.0" encoding="utf-8"?>
<System>
  <Block BlockType="Inport" Name="inPWMs" SID="10053"><P Name="PortDimensions">16</P></Block>
  <Block BlockType="Inport" Name="TerrainIn15d" SID="12106"><P Name="Port">2</P></Block>
  <Block BlockType="SubSystem" Name="6DOF1" SID="12216"><PortCounts in="5" out="9"/></Block>
  <Block BlockType="SubSystem" Name="SensorOutput" SID="12217"/>
  <Block BlockType="Outport" Name="HILSensor30d" SID="10427"/>
  <Block BlockType="Outport" Name="HILGPS30d" SID="10428"/>
  <Block BlockType="Outport" Name="VehileInfo60d" SID="10429"/>
</System>
'''

SIXDOF_XML = '''<?xml version="1.0" encoding="utf-8"?>
<System>
  <Block BlockType="Reference" Name="Custom Variable Mass 6DOF (Quaternion)" SID="12216:1138">
    <PortCounts in="5" out="9"/>
    <P Name="SourceBlock">shared6dof/6DOF (Euler Angles)</P>
    <P Name="SourceType">6DOF EoM (Body Axis)</P>
  </Block>
</System>
'''

# A subsystem whose internal boundary outport reuses the root outport name; the
# mapper must pick the root-level port, not this internal one.
SENSOR_XML = '''<?xml version="1.0" encoding="utf-8"?>
<System>
  <Block BlockType="Outport" Name="VehileInfo60d" SID="12218:1345"/>
</System>
'''

LIB_ROOT_XML = '''<?xml version="1.0" encoding="utf-8"?>
<System><Block BlockType="SubSystem" Name="6DOF (Euler Angles)" SID="61"/></System>
'''

LIB_61_XML = '''<?xml version="1.0" encoding="utf-8"?>
<System>
  <Block BlockType="Integrator" Name="p,q,r " SID="61:17"/>
  <Block BlockType="Integrator" Name="ub,vb,wb" SID="61:56"/>
  <Block BlockType="Integrator" Name="xe,ye,ze" SID="61:26"/>
</System>
'''


def _write_slx(path, members):
    with zipfile.ZipFile(path, 'w') as zf:
        for name, text in members.items():
            zf.writestr(name, text)


class MapReferenceBlocksTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.model = self.root / 'Exp1_MinModelTemp.slx'
        _write_slx(self.model, {
            'simulink/systems/system_root.xml': ROOT_XML,
            'simulink/systems/system_12216.xml': SIXDOF_XML,
            'simulink/systems/system_12218.xml': SENSOR_XML,
        })
        self.library = self.root / 'shared6dof.slx'
        _write_slx(self.library, {
            'simulink/systems/system_root.xml': LIB_ROOT_XML,
            'simulink/systems/system_61.xml': LIB_61_XML,
        })

    def test_io_sids_and_paths(self):
        result = mrb.map_reference_blocks(self.model, {'shared6dof': self.library})
        io = result['io']
        self.assertEqual(io['inPWMs']['sid'], '10053')
        self.assertEqual(io['TerrainIn15d']['sid'], '12106')
        self.assertEqual(io['VehileInfo60d']['sid'], '10429')
        self.assertEqual(io['VehileInfo60d']['path'], 'Exp1_MinModelTemp/VehileInfo60d')
        self.assertEqual(io['VehileInfo60d']['block_type'], 'Outport')

    def test_sixdof_reference_block(self):
        result = mrb.map_reference_blocks(self.model, {'shared6dof': self.library})
        ref = result['sixdof']['reference']
        self.assertEqual(ref['sid'], '12216:1138')
        self.assertEqual(ref['source_block'], 'shared6dof/6DOF (Euler Angles)')
        self.assertEqual(result['sixdof']['subsystem'], {'name': '6DOF1', 'sid': '12216'})

    def test_library_integrators_collected(self):
        result = mrb.map_reference_blocks(self.model, {'shared6dof': self.library})
        integrators = {i['name']: i['sid'] for i in result['libraries']['shared6dof']['integrators']}
        self.assertEqual(integrators, {'p,q,r': '61:17', 'ub,vb,wb': '61:56', 'xe,ye,ze': '61:26'})

    def test_missing_io_block_refused(self):
        bad = self.root / 'bad.slx'
        _write_slx(bad, {'simulink/systems/system_root.xml': '<System/>'})
        with self.assertRaises(ValueError):
            mrb.map_reference_blocks(bad, {})

    def test_main_writes_once_then_refuses_overwrite(self):
        out_dir = self.root / 'out'
        argv = ['map_reference_blocks.py', '--model', str(self.model),
                '--library', 'shared6dof=' + str(self.library), '--out-dir', str(out_dir)]
        with patch.object(sys, 'argv', argv):
            self.assertEqual(mrb.main(), 0)
        report = out_dir / 'block-map.json'
        first = report.read_bytes()
        self.assertEqual(json.loads(first)['io']['VehileInfo60d']['sid'], '10429')
        with patch.object(sys, 'argv', argv):
            self.assertEqual(mrb.main(), 2)  # existing report refused
        self.assertEqual(report.read_bytes(), first)  # preserved verbatim


if __name__ == '__main__':
    unittest.main()
