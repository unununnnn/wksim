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
    down = -float(height)
    # The pre-feedback flat-ground path supplied +0.0.  Canonicalize either
    # signed zero so enabling the accepted scene does not change that input.
    if down == 0.0:
        down = 0.0
    return [down] + [0.0] * (TERRAIN15_SIZE - 1)


STATE120_SIZE = 120
STACK_BODIES = {"arducopter": "uav1", "px4": "uav2"}


class TerrainFeedback:
    """Manages independent per-stack ContactObservers for terrain feedback."""

    STACK_BODIES = STACK_BODIES

    def __init__(self, epoch, scene_source=None, expected_sha256=None, observers=None):
        from .contact_observer import ContactObserver, DEFAULT_SCENE_PATH, FROZEN_SCENE_SHA256
        self.epoch = epoch
        self.scene_source = DEFAULT_SCENE_PATH if scene_source is None else scene_source
        self.expected_sha256 = FROZEN_SCENE_SHA256 if expected_sha256 is None else expected_sha256
        if observers is not None:
            if not isinstance(observers, dict) or set(observers) != set(self.STACK_BODIES):
                raise ValueError("Observers must exactly match the supported stacks")
            self.observers = dict(observers)
        else:
            self.observers = {
                stack: ContactObserver(
                    scene_source=self.scene_source,
                    run_epoch=self.epoch,
                    expected_sha256=self.expected_sha256,
                )
                for stack in self.STACK_BODIES
            }

    def query_terrain(self, stack, tick, prior_state):
        """Derive ENU query point from prior 120-state, query support height, and return Terrain15D."""
        if stack not in self.STACK_BODIES:
            raise ValueError(f"Unknown stack {stack}; expected one of {set(self.STACK_BODIES)}")
        observer = self.observers[stack]
        if observer.frozen:
            raise RuntimeError(f"ContactObserver for {stack} is frozen ({observer.freeze_reason})")
        if (not isinstance(prior_state, (list, tuple)) or len(prior_state) != STATE120_SIZE
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in prior_state)):
            raise ValueError(f"Expected 120 finite numeric values in prior state for {stack}")
        query_point = vehicle60_to_enu_query_point(prior_state[:VEHICLE60_SIZE])
        body_id = self.STACK_BODIES[stack]
        result = observer.observe_step(tick, body_id, query_point, epoch=self.epoch)
        if result.get("freeze") or result.get("status") != "ok":
            raise RuntimeError(f"ContactObserver for {stack} froze at tick {tick}: {result.get('reason')}")
        height = result.get("terrain_height_enu_m")
        if (isinstance(height, bool) or not isinstance(height, (int, float))
                or not math.isfinite(height)):
            raise ValueError(f"Invalid terrain height for {stack} at tick {tick}: {height}")
        return support_height_to_terrain15d(height)

    def manifest(self):
        sample_obs = next(iter(self.observers.values()))
        return {
            "schema": "wksim.terrain-feedback-manifest.v1",
            "scene_id": sample_obs.scene.scene_id,
            "scene_hash": sample_obs.scene.scene_sha256,
            "epoch": self.epoch,
            "mapping": "state[k-1].Vehicle60 -> world ENU support height -> terrain[k].Terrain15D",
            "worker_trace_field": "terrain",
            "stacks": {
                stack: {
                    "body_id": self.STACK_BODIES[stack],
                }
                for stack in self.STACK_BODIES
            },
        }
