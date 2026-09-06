"""Controlled evidence-parser fixtures; never a native renderer acceptance."""
from pathlib import Path
import tempfile
import unittest

from tools.validate_operator_http import live_captures, main


class CaptureEvidenceTests(unittest.TestCase):
    def test_requires_exact_ready_identity_live_record_and_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            view=dict(readback_path=str(root/'actor.jsonl'),frames_directory=str(root))
            log=root/'ue.log'
            (root/'frame-0001.png').write_bytes(b'unit fixture; not native image')
            log.write_text('WKSIM_READY run=other vehicle=1\nWKSIM_CAPTURE frame-0001.png sequence=4 sim=1.0 stale=0\n')
            self.assertEqual(live_captures(view,'test'),[])
            log.write_text('WKSIM_READY run=test vehicle=1\n'
                           'WKSIM_CAPTURE frame-0001.png sequence=-1 sim=0.0 stale=1\n'
                           'WKSIM_CAPTURE frame-0002.png sequence=2 sim=0.5 stale=0\n'
                           'WKSIM_CAPTURE frame-0001.png sequence=4 sim=1.0 stale=0\n')
            rows=live_captures(view,'test')
            self.assertEqual(len(rows),1)
            self.assertEqual((rows[0]['sequence'],rows[0]['sim_time_s']),(4,1.0))
            self.assertEqual(len(rows[0]['sha256']),64)

    def test_invalid_dwell_refused_before_creating_output_or_service_access(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'uncreated'
            for value in ('nan','inf','1.9','10.1'):
                with self.subTest(dwell=value), self.assertRaises(SystemExit) as error:
                    main(['--stack','px4','--dwell-s',value,'--evidence',str(path)])
                self.assertEqual(error.exception.code,2)
                self.assertFalse(path.exists())


if __name__=='__main__':
    unittest.main()
