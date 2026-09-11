"""Explicit opt-in timing diagnostics for :mod:`joint_rate`.

This module is never imported by the production runtime.  The probe adds
clock reads, callback wrappers, sample aggregation, and an extra record event;
its timings are diagnostic evidence, not production performance.
"""
from dataclasses import asdict, dataclass
import time

from .joint_rate import JointRate, RateUnmet


INSTRUMENTATION_OVERHEAD = (
    "opt-in probe overhead: extra monotonic clock reads, health/sleep wrapper "
    "dispatch, sample aggregation, and rate_timing_probe recording; not a "
    "production performance measurement"
)


@dataclass(frozen=True)
class TimingSample:
    """Closed, non-negative nanosecond accounting for one begin attempt."""

    outcome: str
    start_tick: int
    end_tick: int
    entry_ns: int
    initial_health_end_ns: int
    terminal_ns: int
    ideal_start_ns: int
    earliest_start_ns: int
    entry_to_initial_health_ns: int
    loop_health_ns: int
    loop_health_calls: int
    sleep_requested_ns: int
    sleep_elapsed_ns: int
    sleep_calls: int
    sleep_max_overshoot_ns: int
    final_spin_other_ns: int
    release_excess_ns: int
    observed_elapsed_ns: int
    phase_total_ns: int

    def as_dict(self):
        result = asdict(self)
        result["instrumentation_overhead"] = INSTRUMENTATION_OVERHEAD
        return result


@dataclass
class _ActiveSample:
    entry_ns: int
    initial_health_end_ns: int | None = None
    loop_health_ns: int = 0
    loop_health_calls: int = 0
    sleep_requested_ns: int = 0
    sleep_elapsed_ns: int = 0
    sleep_calls: int = 0
    sleep_max_overshoot_ns: int = 0


class JointRateTimingProbe(JointRate):
    """A deliberately explicit diagnostic subclass of :class:`JointRate`.

    The parent implementation performs the complete pacing contract.  This
    subclass only wraps ``health`` and ``sleep`` while ``begin_group`` is
    executing, then emits one closed ``rate_timing_probe`` record.  Construct
    this class directly; constructing ``JointRate`` remains untouched.
    """

    def __init__(self, epoch, requested_rate, record,
                 now=time.monotonic_ns, sleep=time.sleep):
        self._raw_now = now
        self._raw_sleep = sleep
        self._last_observed_ns = None
        self._active = None
        self.timings = []
        super().__init__(epoch, requested_rate, record,
                         now=self._probe_now, sleep=self._probe_sleep)

    def _probe_now(self):
        value = self._raw_now()
        if self._last_observed_ns is not None and value < self._last_observed_ns:
            raise ValueError("Timing probe requires a monotonic clock")
        self._last_observed_ns = value
        return value

    @staticmethod
    def _delta(later, earlier):
        value = later - earlier
        if value < 0:
            raise ValueError("Timing probe observed a negative duration")
        return value

    def _probe_sleep(self, seconds):
        active = self._active
        if active is None:
            return self._raw_sleep(seconds)
        requested_ns = round(seconds * 1e9)
        before = self._probe_now()
        self._raw_sleep(seconds)
        after = self._probe_now()
        elapsed_ns = self._delta(after, before)
        active.sleep_requested_ns += requested_ns
        active.sleep_elapsed_ns += elapsed_ns
        active.sleep_calls += 1
        active.sleep_max_overshoot_ns = max(
            active.sleep_max_overshoot_ns,
            max(0, elapsed_ns - requested_ns),
        )

    def _planned_edges(self):
        if self.anchor is None:
            return 0, 0
        ideal = self.anchor["wall_ns"] + self.completed * self.period_ns
        earliest = max(
            ideal,
            ideal if self.previous_start is None else self.previous_start + self.period_ns,
        )
        return ideal, earliest

    def _finish_sample(self, active, outcome, tick, terminal_ns, ideal, earliest):
        initial_end = active.initial_health_end_ns
        if initial_end is None:
            initial_end = active.entry_ns
        entry_to_initial = self._delta(initial_end, active.entry_ns)
        observed = self._delta(terminal_ns, active.entry_ns)
        final_other = (
            observed
            - entry_to_initial
            - active.loop_health_ns
            - active.sleep_elapsed_ns
        )
        if final_other < 0:
            raise ValueError("Timing probe phase accounting is not closed")
        phase_total = (
            entry_to_initial
            + active.loop_health_ns
            + active.sleep_elapsed_ns
            + final_other
        )
        sample = TimingSample(
            outcome=outcome,
            start_tick=tick,
            end_tick=tick + 4,
            entry_ns=active.entry_ns,
            initial_health_end_ns=initial_end,
            terminal_ns=terminal_ns,
            ideal_start_ns=ideal,
            earliest_start_ns=earliest,
            entry_to_initial_health_ns=entry_to_initial,
            loop_health_ns=active.loop_health_ns,
            loop_health_calls=active.loop_health_calls,
            sleep_requested_ns=active.sleep_requested_ns,
            sleep_elapsed_ns=active.sleep_elapsed_ns,
            sleep_calls=active.sleep_calls,
            sleep_max_overshoot_ns=active.sleep_max_overshoot_ns,
            final_spin_other_ns=final_other,
            release_excess_ns=max(0, terminal_ns - earliest),
            observed_elapsed_ns=observed,
            phase_total_ns=phase_total,
        )
        self.timings.append(sample)
        self.record("rate_timing_probe", **sample.as_dict())

    def begin_group(self, tick, health):
        entry = self._probe_now()
        active = _ActiveSample(entry_ns=entry)
        ideal, earliest = self._planned_edges()
        self._active = active
        outcome = "rejected"
        try:
            def measured_health():
                before = self._probe_now()
                try:
                    health()
                finally:
                    after = self._probe_now()
                    elapsed = self._delta(after, before)
                    if active.initial_health_end_ns is None:
                        active.initial_health_end_ns = after
                    else:
                        active.loop_health_ns += elapsed
                        active.loop_health_calls += 1

            super().begin_group(tick, measured_health)
            outcome = "started"
        except RateUnmet:
            outcome = "rate_unmet"
            raise
        finally:
            terminal = self._last_observed_ns
            if outcome == "started" and self.group is not None:
                terminal = self.group["actual_start_ns"]
                ideal = self.group["ideal_start_ns"]
                earliest = self.group["earliest_start_ns"]
            if terminal is None:
                terminal = entry
            self._active = None
            self._finish_sample(active, outcome, tick, terminal, ideal, earliest)
