"""Offline GNSS outage decisions for 1 ms authority ticks; no I/O or FC control.

HIL_GPS timestamps are original, epoch-relative simulation microseconds in this
contract (not Unix time). A decision authorizes a candidate; it is not send proof.
"""
from dataclasses import asdict, dataclass
import re


def _integer(value, name, maximum=2**53 - 1, minimum=0):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Invalid " + name)


def _identity(run_id, epoch, vehicle_id):
    for name, value in (("run_id", run_id), ("epoch", epoch)):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
            raise ValueError("Invalid " + name)
    _integer(vehicle_id, "vehicle_id", 255, 1)


@dataclass(frozen=True)
class GnssEventPlan:
    """One stop-new-GPS interval, inclusive start and exclusive end."""
    run_id: str
    epoch: str
    vehicle_id: int
    start_tick: int
    end_tick: int

    def __post_init__(self):
        _identity(self.run_id, self.epoch, self.vehicle_id)
        _integer(self.start_tick, "start_tick")
        _integer(self.end_tick, "end_tick")
        if self.end_tick <= self.start_tick:
            raise ValueError("end_tick must follow start_tick")

    def active(self, tick):
        _integer(tick, "tick")
        return self.start_tick <= tick < self.end_tick


@dataclass(frozen=True)
class GnssSample:
    """Immutable original candidate, before any fault/output decision.

    source_tick is acquisition time, never arrival time. gps is exactly the 13
    arguments returned by px4_mavlink.gps_arguments, including original quality
    and time. This module neither imports pymavlink nor modifies those arguments.
    """
    run_id: str
    epoch: str
    vehicle_id: int
    sequence: int
    source_tick: int
    gps: tuple

    def __post_init__(self):
        _identity(self.run_id, self.epoch, self.vehicle_id)
        _integer(self.sequence, "sequence")
        _integer(self.source_tick, "source_tick")
        if type(self.gps) is not tuple or len(self.gps) != 13:
            raise ValueError("gps must contain exactly 13 immutable HIL_GPS arguments")
        # time, fix, lat, lon, alt, eph, epv, vel, vn, ve, vd, cog, satellites
        bounds = ((0, 2**64-1), (0, 8), (-900000000, 900000000),
                  (-1800000000, 1800000000), (-2**31, 2**31-1),
                  (0, 65535), (0, 65535), (0, 65535),
                  (-32768, 32767), (-32768, 32767), (-32768, 32767),
                  (0, 65535), (0, 255))
        for index, (value, (low, high)) in enumerate(zip(self.gps, bounds)):
            _integer(value, "gps[" + str(index) + "]", high, low)
        if 36000 <= self.gps[11] < 65535:
            raise ValueError("cog must be 0..35999 or unknown (65535)")


@dataclass(frozen=True)
class GnssDecision:
    run_id: str
    epoch: str
    vehicle_id: int
    tick: int
    sample: GnssSample
    plan: GnssEventPlan | None
    max_age_ticks: int
    event_active: bool
    source_fix_3d: bool
    accepted: bool
    reason: str
    outbound_gps: tuple | None

    def record(self):
        """JSON-compatible provenance; outbound is planned, not actual send proof."""
        return asdict(self)


class GnssEventController:
    @property
    def identity(self):
        """Current immutable run/epoch/vehicle binding for the send boundary."""
        return self._run_id, self._epoch, self._vehicle_id

    def __init__(self, run_id, epoch, vehicle_id, *, max_age_ticks, plan=None):
        _identity(run_id, epoch, vehicle_id)
        _integer(max_age_ticks, "max_age_ticks")
        self._run_id, self._epoch, self._vehicle_id = run_id, epoch, vehicle_id
        self._max_age_ticks = max_age_ticks
        self._retired_epochs = set()
        self._clear()
        if plan is not None:
            self.schedule(plan)

    def _clear(self):
        self._plan = None
        self._last_tick = self._last_sequence = self._last_source_tick = self._last_time_us = -1

    def schedule(self, plan):
        if not isinstance(plan, GnssEventPlan):
            raise ValueError("Expected GnssEventPlan")
        if (plan.run_id, plan.epoch, plan.vehicle_id) != (self._run_id, self._epoch, self._vehicle_id):
            raise ValueError("Foreign plan")
        if self._plan is not None or plan.start_tick <= self._last_tick:
            raise ValueError("Duplicate or late plan")
        self._plan = plan

    def reset(self, epoch):
        """Bind a never-used epoch; clear the old plan and all sample cursors.

        Re-applying a fault requires a new explicit plan for the new epoch.
        Retired epoch identifiers remain denied so old packets cannot return.
        """
        _identity(self._run_id, epoch, self._vehicle_id)
        if epoch == self._epoch or epoch in self._retired_epochs:
            raise ValueError("Reset requires a fresh epoch")
        self._retired_epochs.add(self._epoch)
        self._epoch = epoch
        self._clear()

    def decide(self, sample, *, tick):
        """Reject stale/replayed inputs; never cache/replay a previous GPS fix.

        A fresh invalid fix is forwarded unchanged outside the outage. 3D fix
        here describes source quality only, not estimator/mission readiness.
        Rejected candidates do not change cursors. Valid suppressed candidates
        do, ensuring recovery needs a new acquisition, sequence and source time.
        """
        _integer(tick, "tick")
        if not isinstance(sample, GnssSample):
            raise ValueError("Expected GnssSample")
        active = self._plan is not None and self._plan.active(tick)
        reason = None
        if (sample.run_id, sample.epoch, sample.vehicle_id) != (self._run_id, self._epoch, self._vehicle_id):
            reason = "foreign_identity"
        elif tick < self._last_tick:
            reason = "backward_tick"
        elif (sample.sequence <= self._last_sequence or sample.source_tick <= self._last_source_tick
              or sample.gps[0] <= self._last_time_us):
            reason = "duplicate_or_old_source"
        elif sample.source_tick > tick or sample.gps[0] > sample.source_tick * 1000:
            reason = "future_source"
        elif (tick - sample.source_tick > self._max_age_ticks
              or tick * 1000 - sample.gps[0] > self._max_age_ticks * 1000):
            reason = "stale_source"
        accepted = reason is None
        outbound = None
        fix_3d = sample.gps[1] >= 3
        if accepted:
            self._last_tick, self._last_sequence = tick, sample.sequence
            self._last_source_tick, self._last_time_us = sample.source_tick, sample.gps[0]
            reason = "signal_loss" if active else ("pass" if fix_3d else "invalid_fix")
            if not active:
                outbound = sample.gps
        return GnssDecision(self._run_id, self._epoch, self._vehicle_id,
                            tick, sample, self._plan, self._max_age_ticks,
                            active, fix_3d, accepted, reason, outbound)
