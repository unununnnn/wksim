"""Direct kernel parentage liveness guard for joint task workers (Linux only).

joint_task workers are direct Popen children of the joint supervisor. The
existing health check re-reads /proc/<pid>/stat and cmdline on every pump via
json_identity and compares only start_ticks. On Linux the kernel parentage is
sufficient and cheaper: os.getppid() changes exactly when the parent exits and
the child is reparented (init or a subreaper), and a reused PID can never
become this process's parent again — getppid is set at fork and only ever
moves away from a dead parent.

DirectParentGuard performs the strict identity check once at startup
(getppid, then the real json_identity pid/pgid/start_ticks comparison, then
getppid again to close the startup race) and a pure getppid comparison on
every call. Results are never cached and no call frequency or deadline is
relaxed. The failure semantics stay exactly those of the original check:
RuntimeError('Joint supervisor retired; no automatic task recovery').
"""
import os
import sys

FAILURE = 'Joint supervisor retired; no automatic task recovery'


def _integer(value, name, low):
    if not isinstance(value, int) or isinstance(value, bool) or value < low:
        raise ValueError(f'parent identity field {name} must be an integer >= {low}')
    return value


class DirectParentGuard:
    """Callable liveness guard bound to the direct parent process identity."""

    def __init__(self, expected):
        if sys.platform != 'linux':
            raise OSError('DirectParentGuard requires Linux (/proc and getppid)')
        if not isinstance(expected, dict):
            raise TypeError('expected parent identity must be a dict')
        pid = _integer(expected.get('pid'), 'pid', 1)
        pgid = _integer(expected.get('pgid'), 'pgid', 1)
        start_ticks = _integer(expected.get('start_ticks'), 'start_ticks', 0)
        if os.getppid() != pid:
            raise RuntimeError(FAILURE)
        from .evidence import json_identity
        identity = json_identity(pid)
        if (identity is None or identity.get('pid') != pid
                or identity.get('pgid') != pgid or identity.get('start_ticks') != start_ticks):
            raise RuntimeError(FAILURE)
        # Startup race: the parent may have exited between the two checks.
        if os.getppid() != pid:
            raise RuntimeError(FAILURE)
        self._pid = pid

    def __call__(self):
        if os.getppid() != self._pid:
            raise RuntimeError(FAILURE)
