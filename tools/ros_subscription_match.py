"""Read actual RCL matched counts on the project's installed ROS Humble."""
import ctypes
import hashlib
from pathlib import Path


class MatchedPublishers:
    def __init__(self):
        library = Path('/opt/ros/humble/lib/librcl.so')
        header = Path('/opt/ros/humble/include/rcl/rcl/subscription.h')
        self.identity = dict(api='rcl_subscription_get_publisher_count',
            sources_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in (library, header, Path(__file__))})
        self.library = ctypes.CDLL(str(library))
        self.count_function = self.library.rcl_subscription_get_publisher_count
        self.count_function.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)]
        self.count_function.restype = ctypes.c_int
        self.topic_function = self.library.rcl_subscription_get_topic_name
        self.topic_function.argtypes = [ctypes.c_void_p]
        self.topic_function.restype = ctypes.c_char_p

    def count(self, subscription):
        expected_topic = subscription.topic_name.encode('utf-8')
        with subscription.handle:
            pointer = subscription.handle.pointer
            if not pointer or self.topic_function(pointer) != expected_topic:
                raise RuntimeError('RCL subscription handle/topic identity differs')
            count = ctypes.c_size_t()
            result = self.count_function(pointer, ctypes.byref(count))
            if result != 0:
                raise RuntimeError('RCL matched publisher count failed: ' + str(result))
            return count.value
