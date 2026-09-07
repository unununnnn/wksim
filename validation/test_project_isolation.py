"""Keep active migration entry points independent of sibling working copies."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProjectIsolationTests(unittest.TestCase):
    def test_runtime_configs_use_project_owned_firmware(self):
        expected = '/root/wksim-dependencies/px4-d6f12ad1'
        index = json.loads((ROOT/'Simulator/wksim_runtime/capability-index.json').read_text())
        self.assertEqual(index['resource_locations']['px4_root'], expected)
        for path in (ROOT/'Simulator/wksim_runtime/examples').glob('*.json'):
            config = json.loads(path.read_text())
            if 'px4_root' in config:
                if config.get('runtime_profile')=='independent_quad_dds_v1':
                    from Simulator.wksim_runtime.independent_profile import select_config
                    checked,profile=select_config(config)
                    from pathlib import PurePosixPath
                    pinned=str(PurePosixPath(profile['manifests']['px4']['path']).parent/'src')
                    self.assertEqual(checked['px4_root'], pinned, str(path))
                    self.assertTrue(pinned.startswith('/root/wksim-'))
                else:
                    self.assertEqual(config['px4_root'], expected, str(path))

    def test_active_entry_points_have_no_sibling_absolute_paths(self):
        blocked = ('/opt/aerotwinsim/', '/root/aerotwinsim-', 'build/aesim-')
        for folder in ('tools', 'Simulator/wksim_core', 'Simulator/wksim_runtime', 'Simulator/wksim_console'):
            for path in (ROOT/folder).rglob('*'):
                if path.suffix in ('.py', '.sh', '.ps1'):
                    text = path.read_text(encoding='utf-8-sig')
                    for value in blocked:
                        self.assertNotIn(value, text, str(path))
        build = (ROOT/'tools/build-ue55.ps1').read_text()
        self.assertIn("Join-Path $repo 'work/dependencies/ue55/Content'", build)


if __name__ == '__main__':
    unittest.main()
