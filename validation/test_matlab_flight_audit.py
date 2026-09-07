"""Reject corrupted copies of real MATLAB flight evidence; never start a flight."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
from audit_matlab_flight import audit, check_sources

ARCHIVE=REPO/'validation/matlab-retained-sources-20260907'
SOURCE=REPO/'validation/matlab-flight-px4-20260907-run3'


@unittest.skipUnless(sys.platform=='win32' and (SOURCE/'report.json').is_file(),
                     'retained real Windows MATLAB/UE evidence required')
class MatlabAuditTamper(unittest.TestCase):
    def test_archive_requires_exact_retained_bytes_and_evidence_identity(self):
        report=json.loads((SOURCE/'report.json').read_text(encoding='utf-8'))
        launch=report['launch'];directory=SOURCE/'console/jobs'/launch['job_id']/'runs'/launch['run_id']
        formal=json.loads((directory/'result.json').read_text(encoding='utf-8'))
        owner=REPO/'validation/migration-resume-20260907'
        with tempfile.TemporaryDirectory(prefix='matlab-source-copy-',dir=owner) as temporary:
            archive=Path(temporary).resolve()
            self.assertTrue(archive.is_relative_to(owner.resolve()) and archive!=owner.resolve())
            shutil.copytree(ARCHIVE,archive,dirs_exist_ok=True)
            result=check_sources(SOURCE,directory,report,formal,archive)
            self.assertEqual(result['mode'],'retained-source-audit')
            self.assertFalse(result['current_checkout_accepted'])
            manifest=json.loads((archive/'manifest.json').read_text(encoding='utf-8'))
            entry=manifest['runs'][formal['run_id']]
            item=next(iter(entry['sources'].values()));path=archive/item['archive_path']
            original=path.read_bytes();path.write_bytes(original+b'changed')
            with self.assertRaisesRegex(ValueError,'Retained source bytes differ'):
                check_sources(SOURCE,directory,report,formal,archive)
            path.write_bytes(original)
            entry['formal_result_sha256']='0'*64
            (archive/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Retained archive evidence identity differs'):
                check_sources(SOURCE,directory,report,formal,archive)

    def test_repeated_start_and_changed_terminal_artifact_are_rejected(self):
        owner=REPO/'validation/migration-resume-20260907'
        with tempfile.TemporaryDirectory(prefix='matlab-audit-copy-',dir=owner) as temporary:
            root=Path(temporary).resolve()
            self.assertTrue(root.is_relative_to(owner.resolve()) and root!=owner.resolve())
            shutil.copytree(SOURCE,root,dirs_exist_ok=True,copy_function=os.link)
            self.assertEqual(audit(root,source_archive=ARCHIVE)['status'],'pass')
            path=root/'launch-requests.jsonl';text=path.read_text(encoding='utf-8')
            start=next(line for line in text.splitlines() if json.loads(line)['method']=='start')
            path.unlink()  # Break the copy's hard link before altering evidence.
            path.write_text(text+start+'\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Unexpected MATLAB writes'):audit(root,source_archive=ARCHIVE)
            path.write_text(text,encoding='utf-8')
            report=root/'reconnect-result.json';value=json.loads(report.read_text(encoding='utf-8'))
            value['result']['raw_json']='{}'
            report.unlink();report.write_text(json.dumps(value),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'MATLAB report did not pass'):audit(root,source_archive=ARCHIVE)


if __name__=='__main__':unittest.main()
