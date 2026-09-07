"""Real Windows read-handle contention; starts no UI, WSL or flight process."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from Simulator.wksim_console.visual import View


@unittest.skipUnless(os.name=='nt','Windows sharing semantics')
class ViewPersistenceTests(unittest.TestCase):
    def test_reader_without_delete_share_does_not_retire_the_view(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);view=View(root,'read-test','/tmp/wksim-read-test/state.sock')
            view._persist()
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,
                                        wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
            kernel.CreateFileW.restype=wintypes.HANDLE
            kernel.CloseHandle.argtypes=[wintypes.HANDLE]
            handle=kernel.CreateFileW(str(root/'view.json'),0x80000000,3,None,3,0x80,None)
            self.assertNotEqual(handle,ctypes.c_void_p(-1).value)
            def release():time.sleep(.06);kernel.CloseHandle(handle)
            thread=threading.Thread(target=release);thread.start()
            original=os.replace;attempts=[]
            def replace(a,b):
                attempts.append(time.monotonic())
                return original(a,b)
            view._state='stale'
            try:
                with patch('Simulator.wksim_console.visual.os.replace',side_effect=replace):view._persist()
            finally:thread.join()
            self.assertGreater(len(attempts),1)
            self.assertEqual(json.loads((root/'view.json').read_text())['state'],'stale')
            self.assertIsNone(view._error)


if __name__=='__main__':unittest.main()
