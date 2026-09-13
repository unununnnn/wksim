import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('pack_validator', HERE / 'validate_pack.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PackChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'pack'
        shutil.copytree(HERE / 'pack', self.root)
        self.manifest = json.loads((self.root / 'manifest.json').read_text())

    def check(self):
        return module.validate(self.root, self.manifest)

    def rewrite_result(self, change):
        path = self.root / 'result.json'
        data = json.loads(path.read_text())
        change(data)
        path.write_text(json.dumps(data))
        self.manifest['files']['result.json'] = module.digest(path)

    def test_retained_pack(self):
        self.assertTrue(self.check()['valid'])
        self.assertFalse(self.check()['full_acceptance'])

    def test_truncated_report_with_updated_hash(self):
        path = self.root / 'group-work-timing.jsonl'
        path.write_bytes(path.read_bytes()[:-100])
        self.manifest['files'][path.name] = module.digest(path)
        self.assertFalse(self.check()['valid'])

    def test_hash_mismatch(self):
        path = self.root / 'rate.jsonl.gz'
        path.write_bytes(path.read_bytes()[:-1])
        self.assertFalse(self.check()['valid'])

    def test_unknown_status(self):
        self.rewrite_result(lambda d: d.update(status='mystery'))
        self.assertFalse(self.check()['valid'])

    def test_duplicate_report(self):
        path = self.root / 'group-work-timing.jsonl'
        rows = path.read_text().splitlines()
        rows[1] = rows[0]
        path.write_text('\n'.join(rows) + '\n')
        self.manifest['files'][path.name] = module.digest(path)
        self.assertFalse(self.check()['valid'])


if __name__ == '__main__':
    unittest.main()
