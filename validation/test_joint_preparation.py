"""File lifecycle checks; no namespaces, flight stacks, ROS or UE are launched."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from Simulator.wksim_runtime.joint_runtime import joint_run_files


class JointPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.config={'kind':'joint_scene','run_id':'prepared-test','value':1}
        self.directory,self.session=joint_run_files(self.config,self.root,prepare=True)

    def consume(self,config=None,directory=None):
        return joint_run_files(config or self.config,self.root,use_prepared_run=directory or self.directory)

    def test_once_and_exact_identity(self):
        self.assertEqual(set(p.name for p in self.directory.iterdir()),
                         {'config.json','session.json','preparation.json','epochs','actions','action-results'})
        directory,session=self.consume()
        self.assertEqual((directory,session),(self.directory,self.session))
        self.assertEqual(json.loads((directory/'execution.started.json').read_text())['state'],'consumed')
        with self.assertRaises(ValueError): self.consume()

    def test_config_change_and_wrong_directory(self):
        with self.assertRaises(ValueError): self.consume(dict(self.config,value=2))
        with self.assertRaises(ValueError): self.consume(directory=self.root/'other')
        self.assertFalse((self.directory/'execution.started.json').exists())
        self.consume(dict(reversed(list(self.config.items()))))

    def test_existing_actions_and_epochs(self):
        for name in ('epochs','actions','action-results'):
            with self.subTest(name=name):
                path=self.directory/name/'existing'
                path.write_text('evidence')
                with self.assertRaises(ValueError): self.consume()
                path.unlink()

    def test_malformed_missing_and_foreign_identity(self):
        for name in ('session.json','preparation.json','config.json'):
            path=self.directory/name
            original=path.read_text()
            for value in ('{','[]','null','{}'):
                path.write_text(value)
                with self.assertRaises(ValueError): self.consume()
            path.unlink()
            with self.assertRaises((ValueError,OSError)): self.consume()
            path.write_text(original)
        path=self.directory/'session.json'
        path.write_text(json.dumps(dict(self.session,instance_id='0'*32)))
        with self.assertRaises(ValueError): self.consume()

    def test_symlink_files_and_directory(self):
        target=self.root/'target'
        target.write_text('{}')
        probe=self.root/'probe'
        try: probe.symlink_to(target)
        except OSError as error: self.skipTest(str(error))
        probe.unlink()
        path=self.directory/'session.json'
        original=path.read_text();path.unlink();path.symlink_to(target)
        with self.assertRaises(ValueError): self.consume()
        path.unlink();path.write_text(original)
        alias=self.root/'alias';alias.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):
            joint_run_files(self.config,alias,use_prepared_run=alias/self.config['run_id'])

    @unittest.skipUnless(hasattr(os,'geteuid') and os.geteuid()==0,'requires Linux root to change ownership')
    def test_foreign_file_ownership(self):
        path=self.directory/'session.json'
        os.chown(path,65534,-1)
        try:
            with self.assertRaises(ValueError): self.consume()
        finally: os.chown(path,os.geteuid(),-1)

    def test_default_remains_fresh_and_random(self):
        with self.assertRaises(FileExistsError): joint_run_files(self.config,self.root)
        other=dict(self.config,run_id='ordinary')
        directory,session=joint_run_files(other,self.root)
        self.assertNotEqual(session['instance_id'],self.session['instance_id'])
        self.assertFalse((directory/'preparation.json').exists())


if __name__=='__main__': unittest.main()
