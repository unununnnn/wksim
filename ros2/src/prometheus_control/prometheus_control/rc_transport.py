"""Bounded actual CDR/GID take using Humble's public subscription handle pointer."""
import ctypes as C
from pathlib import Path
from types import SimpleNamespace
from ament_index_python.packages import get_package_prefix
from rclpy.serialization import deserialize_message


class RCTake:
    def __init__(self):
        self.path = Path(get_package_prefix('prometheus_control'))/'lib/libwksim_rc_take.so'
        self.lib = C.CDLL(str(self.path))
        self.lib.wksim_rc_gid_size.restype = C.c_size_t
        self.lib.wksim_rc_take.argtypes = [C.c_void_p, C.c_void_p, C.c_size_t,
            C.POINTER(C.c_size_t), C.c_void_p, C.POINTER(C.c_int64), C.POINTER(C.c_int64)]
        self.lib.wksim_rc_take.restype = C.c_int
        self.buffer = (C.c_ubyte*8192)()
        self.gid = (C.c_ubyte*self.lib.wksim_rc_gid_size())()

    def take(self, subscription):
        size, source, received = C.c_size_t(), C.c_int64(), C.c_int64()
        with subscription.handle:
            status = self.lib.wksim_rc_take(subscription.handle.pointer, self.buffer, len(self.buffer),
                C.byref(size), self.gid, C.byref(source), C.byref(received))
        if status == 0:
            return None
        if status != 1:
            raise ValueError('rc_transport_oversized' if status == -2 else 'rc_transport_take_failed')
        raw = bytes(self.buffer[:size.value])
        return deserialize_message(raw, subscription.msg_type), SimpleNamespace(
            publisher_gid=bytes(self.gid), cdr_hex=raw.hex(),
            source_timestamp=source.value, received_timestamp=received.value)
