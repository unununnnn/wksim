"""Candidate admission rejects foreign roots, changed manifests and extra source files."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import px4_component_candidate as candidate


class ComponentCandidateTests(unittest.TestCase):
    def test_foreign_root_is_rejected_before_reading_parent_or_build(self):
        with patch.object(candidate.land,'check',side_effect=AssertionError('parent accessed')):
            for root in ('/tmp/foreign','/root/wksim-px4-land-ABC123'):
                with self.assertRaises(ValueError):candidate.snapshot(root)

    def test_manifest_hash_and_full_snapshot_are_both_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'component-build.json';value={'schema':'test','binary_sha256':'a'*64}
            path.write_text(json.dumps(value));digest=hashlib.sha256(path.read_bytes()).hexdigest()
            with patch.object(candidate,'snapshot',return_value=value):
                self.assertEqual(candidate.check(path,digest),value)
                with self.assertRaises(ValueError):candidate.check(path,'b'*64)
            with patch.object(candidate,'snapshot',return_value=value|{'binary_sha256':'c'*64}):
                with self.assertRaises(ValueError):candidate.check(path,digest)

    def test_delta_outside_the_allowed_native_files_is_rejected(self):
        with patch.object(candidate.Path,'resolve',lambda self,**kw:self), \
             patch.object(candidate.land,'check',return_value={'source':{'files':{'extra':1}}}), \
             patch.object(candidate,'expected_sources',return_value={}), \
             patch.object(candidate,'source_snapshot',return_value={'files':{'extra':2}}), \
             patch.object(candidate.land,'_linked_libraries',side_effect=AssertionError('ldd reached')):
            with self.assertRaisesRegex(ValueError,'Unexpected native source delta'):
                candidate.snapshot('/root/wksim-px4-component-ABC123')


if __name__=='__main__':unittest.main()
