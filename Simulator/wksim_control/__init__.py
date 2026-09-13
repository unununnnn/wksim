"""Explicit external position control; no ROS or flight-controller side effects."""

from .position_contract import PositionReference, PositionState, PIDReference, PIDState
from .native_thrust import NativeThrustConfig
from .controllers import select_controller


def __getattr__(name):
    # Preserve package-level PID imports without loading PID for UDE/NE callers.
    if name in ('PIDConfig', 'PIDOutput', 'PositionPID'):
        from . import position_pid
        return getattr(position_pid, name)
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')

__all__ = [
    "NativeThrustConfig", "PIDConfig", "PIDOutput", "PIDReference", "PIDState",
    "PositionPID", "select_controller",
    "PositionReference", "PositionState",
]
