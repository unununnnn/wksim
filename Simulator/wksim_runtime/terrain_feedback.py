"""Pure coordinate mapping for the reviewed vertical terrain-input seam."""
import math


VEHICLE60_SIZE = 60
TERRAIN15_SIZE = 15


def vehicle60_to_enu_query_point(state):
    """Map the previous Vehicle60 NED position to a world ENU query point."""
    if (not isinstance(state, (list, tuple)) or len(state) != VEHICLE60_SIZE
            or any(isinstance(value, bool) or not isinstance(value, (int, float))
                   or not math.isfinite(value) for value in state)):
        raise ValueError("Expected exactly 60 finite numeric Vehicle60 values")
    return [float(state[7]), float(state[6]), -float(state[8])]


def support_height_to_terrain15d(height):
    """Map a world ENU support height to the model's 15-value NED input."""
    if (isinstance(height, bool) or not isinstance(height, (int, float))
            or not math.isfinite(height)):
        raise ValueError("Expected one finite numeric world ENU support height")
    return [-float(height)] + [0.0] * (TERRAIN15_SIZE - 1)
