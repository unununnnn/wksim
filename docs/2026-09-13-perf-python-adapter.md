# Python ownership boundary for the perf recorder

`Simulator/wksim_runtime/perf_capture.py` provides explicit start/stop calls to
the reviewed C recorder. It binds `void **` as `POINTER(c_void_p)`, checks the
original process and native thread before each operation, and keeps the library
and handle alive when native cleanup retains ownership. A nonzero return always
raises, including when stop has already consumed the handle. A failed start can
be cleaned up but can never become a successful capture.

The caller supplies an absolute library path and exact SHA256. The adapter
requires the reviewed WSL kernel and absent output paths. The launcher must
keep the verified library stable during loading and retain source/build identity;
the hash check is not an atomic loader or a substitute for deployment admission.
There is no destructor, periodic Python callback or model/controller dependency.

[Native admission receipts](../validation/coordination/perf-python-native-admission-20260913-01/run-receipt.json)
record nine mocked boundary tests on Linux and actual calls through the shared
library. The normal sample retained 12 SWITCH records / 6 pairs. A wrong-thread
Python stop was refused; its owner then stopped successfully, retaining 4
records / 2 pairs. Both raw captures passed the independent consumer with
`--require-kernel-counter`. The shared library was built from the accepted
recorder source with `-Wall -Wextra -Werror`; no binary is published here.

The [isolated output collision](../validation/coordination/perf-python-native-admission-20260913-01/collision2-receipt.json)
returned `stop: create raw: output_exists (errno 17)`. The existing bytes were
preserved, the handle was consumed, and FD/thread counts remained 4/1. No metadata
is created when exclusive raw creation fails, so this case makes no counter claim.
The earlier collision script incorrectly expected a metadata file; its failed
receipt is retained. The original short collision case also lacked a switch pair
and is not used to isolate EEXIST.

The actual successful captures used the process main thread. The Python guard,
not C's EPERM branch, rejected the foreign-thread call. Mock tests cover retained
handles; prior recorder-native tests cover its failure paths. Each runtime check
used fresh two-WSL prechecks and same-boot cleanup; compilation and later capture
may occur on separate boots, with the library hash and kernel checked again.

This validates the calling boundary. Whole-duration overhead, actual MIXED window
binding, deployment admission and flight acceptance remain unfinished. These
captures do not satisfy MIXED, G6 or Full.
