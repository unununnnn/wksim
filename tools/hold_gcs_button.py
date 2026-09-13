"""One authorized long mouse press on the current owned GCS window; no MAVLink."""
import argparse
import ctypes
from ctypes import wintypes as W
import json
from pathlib import Path
import re
import time


def hold(output, x, y, width, height):
    owned=json.loads((output/'qgc-owned.json').read_text(encoding='utf-8-sig'))
    phase=json.loads((output/'formal/human-handoff.json').read_text())['current']
    if phase['event']!='awaiting_human_qgc_mode' or (output/'report.json').exists():
        raise ValueError('Experiment is not awaiting its GUI release-mode action')
    expected=Path(__file__).resolve().parents[1]/'work/qgc-contained-build/stage/bin/WksimGCS.exe'
    if Path(owned['Path']).resolve()!=expected or not (0<x<width and 0<y<height):
        raise ValueError('Owned executable or observed coordinates differ')
    user=ctypes.WinDLL('user32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    dwm=ctypes.WinDLL('dwmapi',use_last_error=True)
    kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE
    kernel.GetProcessTimes.argtypes=[W.HANDLE,*([ctypes.POINTER(W.FILETIME)]*4)];kernel.GetProcessTimes.restype=W.BOOL
    kernel.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)];kernel.QueryFullProcessImageNameW.restype=W.BOOL
    kernel.CloseHandle.argtypes=[W.HANDLE]
    user.GetForegroundWindow.restype=W.HWND
    user.GetWindowThreadProcessId.argtypes=[W.HWND,ctypes.POINTER(W.DWORD)]
    user.GetWindowTextW.argtypes=[W.HWND,W.LPWSTR,ctypes.c_int]
    user.ScreenToClient.argtypes=[W.HWND,ctypes.POINTER(W.POINT)];user.ScreenToClient.restype=W.BOOL
    user.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];user.PostMessageW.restype=W.BOOL
    user.SetThreadDpiAwarenessContext.argtypes=[W.HANDLE];user.SetThreadDpiAwarenessContext.restype=W.HANDLE
    dwm.DwmGetWindowAttribute.argtypes=[W.HWND,W.DWORD,ctypes.c_void_p,W.DWORD]
    process=kernel.OpenProcess(0x1000,False,owned['Id'])
    if not process:
        raise ctypes.WinError(ctypes.get_last_error())
    previous_dpi=user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    try:
        created,exited,kern,usr=[W.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(process,*map(ctypes.byref,(created,exited,kern,usr))):
            raise ctypes.WinError(ctypes.get_last_error())
        created_ms=((created.dwHighDateTime<<32)|created.dwLowDateTime)//10000-11644473600000
        expected_ms=int(re.fullmatch(r'/Date\((\d+)\)/',owned['StartTime']).group(1))
        image=ctypes.create_unicode_buffer(32768);size=W.DWORD(len(image))
        if not kernel.QueryFullProcessImageNameW(process,0,image,ctypes.byref(size)) or Path(image.value).resolve()!=expected or created_ms!=expected_ms:
            raise ValueError('Owned process path/start time changed')
        window=user.GetForegroundWindow();pid=W.DWORD()
        user.GetWindowThreadProcessId(window,ctypes.byref(pid))
        title=ctypes.create_unicode_buffer(256);user.GetWindowTextW(window,title,len(title))
        if pid.value!=owned['Id'] or title.value!='WksimGCS Daily':
            raise ValueError('Foreground is not the observed owned GCS window')
        rectangle=W.RECT()
        if dwm.DwmGetWindowAttribute(window,9,ctypes.byref(rectangle),ctypes.sizeof(rectangle))!=0:
            raise RuntimeError('Cannot read actual visible window bounds')
        if (rectangle.right-rectangle.left,rectangle.bottom-rectangle.top)!=(width,height):
            raise ValueError('Window size/DPI changed since screenshot; reobserve')
        point=W.POINT(rectangle.left+x,rectangle.top+y)
        if not user.ScreenToClient(window,ctypes.byref(point)):
            raise ctypes.WinError(ctypes.get_last_error())
        position=(point.y<<16)|(point.x&0xffff)
        started=time.monotonic()
        if not user.PostMessageW(window,0x0201,1,position):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            time.sleep(.8)
        finally:
            current=W.DWORD();user.GetWindowThreadProcessId(window,ctypes.byref(current))
            if current.value!=owned['Id'] or not user.PostMessageW(window,0x0202,0,position):
                raise RuntimeError('Could not release the same owned window button')
        record=dict(actor='assistant; user explicitly authorized all confirmations',method='window-directed mouse down/up',
            pid=owned['Id'],created_ms=created_ms,window=int(window),title=title.value,
            screenshot_size=[width,height],screenshot_point=[x,y],client_point=[point.x,point.y],
            held_seconds=time.monotonic()-started,run_id=phase['run_id'],control_epoch=phase['control_epoch'])
        with (output/'authorized-gui-hold.json').open('x',encoding='utf-8') as file:
            json.dump(record,file,indent=2)
        return record
    finally:
        if previous_dpi:
            user.SetThreadDpiAwarenessContext(previous_dpi)
        kernel.CloseHandle(process)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    for name in ('x','y','width','height'):
        parser.add_argument('--'+name,type=int,required=True)
    args=parser.parse_args()
    print(json.dumps(hold(args.output.resolve(),args.x,args.y,args.width,args.height),indent=2))
