"""Identity boundary tests, not simulated flight or control behavior."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import joint_control_candidate as candidate


class CandidateTests(unittest.TestCase):
    def test_source_install_and_manifest_tampering_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary); repo=base/'repo'; root=base/'candidate'; package=repo/'package'
            for directory in (package/'prometheus_control',root/'src/prometheus_control/prometheus_control',
                              root/'install/prometheus_control'/candidate.PYTHON/'prometheus_control'):
                directory.mkdir(parents=True)
                (directory/'__init__.py').write_text('')
                (directory/'node.py').write_text('VALUE = 1\n')
            for directory in (package,root/'src/prometheus_control'):
                (directory/'scripts').mkdir()
                (directory/'src').mkdir()
                for name in ('CMakeLists.txt','package.xml','scripts/prometheus_control_node','src/rc_take.cpp'):
                    (directory/name).write_text('fixture\n')
            transport=root/'install/prometheus_control/lib/libwksim_rc_take.so'
            transport.parent.mkdir(parents=True)
            transport.write_bytes(b'fixture transport\n')
            (repo/'tools').mkdir()
            (repo/'tools/build-joint-control.sh').write_text('fixture build\n')
            (root/'build.log').write_text('fixture completed\n')
            with patch.object(candidate,'REPO',repo),patch.object(candidate,'PACKAGE',package),\
                    patch.object(candidate,'root_path',return_value=root):
                manifest=root/'build.json'; manifest.write_text(json.dumps(candidate.snapshot(root)))
                checksum=candidate.digest(manifest)
                self.assertEqual(candidate.check(manifest,checksum)['version'],1)
                with self.assertRaises(ValueError): candidate.check(manifest,'0'*64)
                installed=root/'install/prometheus_control'/candidate.PYTHON/'prometheus_control/node.py'
                installed.write_text('VALUE = 2\n')
                with self.assertRaises(ValueError): candidate.check(manifest,checksum)
                installed.write_text('VALUE = 1\n')
                extra=installed.with_name('shadow.so');extra.write_bytes(b'not a permitted Python source')
                with self.assertRaises(ValueError): candidate.check(manifest,checksum)
                extra.unlink()
                transport.write_bytes(b'tampered transport\n')
                with self.assertRaises(ValueError): candidate.check(manifest,checksum)

    def test_candidate_root_policy(self):
        for value in ('relative','/tmp/candidate','/root/wksim-ap-clock-stop-x','/root/wksim-joint-control-../x'):
            with self.subTest(value=value),self.assertRaises(ValueError): candidate.root_path(value)


if __name__=='__main__': unittest.main()
