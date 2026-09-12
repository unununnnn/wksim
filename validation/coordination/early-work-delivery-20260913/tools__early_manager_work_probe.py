"""Opt-in bounded early-manager-work segmentation probe (diagnostic only).

Measures wall + current-thread CPU of explicit manager hotspots during the
first WINDOW_NS (10 wall seconds) from the FIRST rate anchor's wall_ns.
The 2-wall-second steady_after boundary (joint_rate.py:152) is recorded as a
warmup/steady marker ONLY; it never stops sampling.  This module changes no
scheduling: wrapped actions keep their exact call counts, order, arguments,
return values, and exception propagation, and the 1 ms / 4-tick / no-catchup /
100 ms / readiness / health gates are untouched.  It is not a second pacer.

Discipline:
- zero clock reads and zero samples before the first anchor (window unset);
- past the 10 s cutoff calls pass through with a single wall read, no sample;
- a call straddling the cutoff is recorded with crossing=True;
- samples are bounded (default 32768) with an explicit truncated flag and a
  dropped counter; diagnostic errors are bounded (default 1024) with explicit
  total/dropped counters; nothing is written to disk per tick;
- every sampled call re-verifies the anchor epoch AND segment id (regions
  exactly like wrapped calls): a change in either is a diagnostic error,
  never a mixed sample;
- regions carry real tick/epoch readers: end_tick is the reader's real value
  at close, and Region.end() is idempotent (a repeated end never appends a
  second sample);
- cancellation semantics are preserved: KeyboardInterrupt/SystemExit/
  InterruptedError from a diagnostic read propagate when the action itself
  succeeded; only while the action's OWN exception is already propagating is
  any diagnostic failure (of any type) listed separately instead;
- read order is symmetric: at both boundaries wall is read before thread CPU
  and the tick/epoch readers run OUTSIDE the CPU interval; the end-side
  readers also run outside the wall interval.  The start-side readers sit
  inside the wall interval, so wall samples include a small constant
  start-side read overhead that CPU samples do not -- declared, not hidden;
- end-of-call reads that fail or go non-monotonic are recorded in
  ``diagnostic_errors`` (explicit, no invalid sample) and never mask an
  in-flight action exception;
- phases are sequential hotspot segments: their sums are NOT a closure of the
  window, and uncovered gaps are declared, never hidden;
- no zero-overhead claim: two wall + two thread-CPU reads per sampled call,
  one wall read per post-cutoff call.
"""

import time


WINDOW_NS = 10_000_000_000          # fixed 10 wall seconds from the first anchor
WARMUP_NS = 2_000_000_000           # steady_after boundary (joint_rate.py:152)
MAX_SAMPLES = 32768
MAX_DIAGNOSTIC_ERRORS = 1024
CANCEL_TYPES = (KeyboardInterrupt, SystemExit, InterruptedError)
PHASES = frozenset((
    "manager_health", "rate_begin_group", "physics_advance",
    "clock_publication_log", "post_advance_readiness_summary",
))


def _explicit_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


class Region:
    """One open region token from :meth:`EarlyManagerWorkProbe.begin`.

    Carries the real tick/epoch readers; ``end()`` is idempotent.
    """

    __slots__ = ("_probe", "_phase", "_tick_of", "_epoch_of", "_segment_of",
                 "_start_ns", "_start_tick", "_cpu_start", "_closed")

    def __init__(self, probe, phase, tick_of, epoch_of, segment_of,
                 start_ns, start_tick, cpu_start):
        self._probe = probe
        self._phase = phase
        self._tick_of = tick_of
        self._epoch_of = epoch_of
        self._segment_of = segment_of
        self._start_ns = start_ns
        self._start_tick = start_tick
        self._cpu_start = cpu_start
        self._closed = False

    @property
    def closed(self):
        return self._closed

    def end(self, *, outcome="ok"):
        """Close the region exactly once; a repeated end is a no-op and never
        appends a second sample.  Diagnostic read failures follow the probe's
        cancellation/masking contract (see module docstring)."""
        if self._closed:
            return
        self._closed = True
        self._probe._finish(self._phase, self._start_ns, self._start_tick,
                            self._cpu_start, outcome,
                            action_failed=(outcome != "ok"),
                            tick_of=self._tick_of, epoch_of=self._epoch_of,
                            segment_of=self._segment_of)


class EarlyManagerWorkProbe:
    """Bounded in-memory segmentation recorder; see module docstring."""

    def __init__(self, *, monotonic_ns=time.monotonic_ns,
                 thread_time_ns=time.thread_time_ns, max_samples=MAX_SAMPLES,
                 max_diagnostic_errors=MAX_DIAGNOSTIC_ERRORS):
        if not callable(monotonic_ns) or not callable(thread_time_ns):
            raise ValueError("clock providers must be callable")
        if type(max_samples) is not int or max_samples <= 0:
            raise ValueError("max_samples must be a positive integer")
        if type(max_diagnostic_errors) is not int or max_diagnostic_errors <= 0:
            raise ValueError("max_diagnostic_errors must be a positive integer")
        self._monotonic_ns = monotonic_ns
        self._thread_time_ns = thread_time_ns
        self._max_samples = max_samples
        self._max_diagnostic_errors = max_diagnostic_errors
        self._window = None
        self._epoch = None
        self._segment = None
        self._samples = []
        self._truncated = False
        self._dropped = 0
        self._diagnostic_errors = []
        self._diagnostic_error_total = 0
        self._diagnostic_error_dropped = 0

    @property
    def window(self):
        return self._window

    @property
    def truncated(self):
        return self._truncated

    @property
    def diagnostic_errors(self):
        return list(self._diagnostic_errors)

    @property
    def diagnostic_error_total(self):
        return self._diagnostic_error_total

    def set_window(self, *, anchor_wall_ns, epoch, segment):
        """Latch the fixed 10 s window ONCE, bound to the anchor identity."""
        if type(anchor_wall_ns) is not int:
            raise ValueError("anchor_wall_ns must be an integer (ns)")
        _explicit_text(epoch, "epoch")
        if isinstance(segment, bool) or type(segment) is not int:
            raise ValueError("segment must be an integer segment id")
        if self._window is not None:
            raise ValueError("the measurement window is already latched")
        self._window = (anchor_wall_ns, anchor_wall_ns + WINDOW_NS)
        self._epoch = epoch
        self._segment = segment

    # ---- shared finalization -------------------------------------------------
    def _record_diagnostic_error(self, phase, error):
        self._diagnostic_error_total += 1
        if len(self._diagnostic_errors) < self._max_diagnostic_errors:
            self._diagnostic_errors.append(dict(phase=phase, error=repr(error)))
        else:
            self._diagnostic_error_dropped += 1

    def _finish(self, phase, start_ns, start_tick, cpu_start, outcome, *,
                action_failed, tick_of, epoch_of, segment_of):
        """Finalize one sampled call.  End-side read order: wall, thread CPU,
        then tick, then epoch -- the tick/epoch readers sit OUTSIDE both
        measured intervals.  A diagnostic failure while the action's own
        exception is propagating is recorded (never masks it); with a
        successful action, cancellation-type failures propagate."""
        window = self._window
        try:
            end_ns = self._monotonic_ns()
            cpu_end = self._thread_time_ns()
            end_tick = tick_of()
            if epoch_of() != self._epoch:
                raise ValueError("epoch changed during the measurement window")
            if segment_of() != self._segment:
                raise ValueError("segment changed during the measurement window")
            cpu_ns = cpu_end - cpu_start
            if end_ns < start_ns:
                raise ValueError("wall clock moved backwards during a sampled call")
            if cpu_ns < 0:
                raise ValueError("thread CPU moved backwards during a sampled call")
        except BaseException as error:
            if action_failed:
                self._record_diagnostic_error(phase, error)
                return
            if isinstance(error, CANCEL_TYPES):
                raise
            self._record_diagnostic_error(phase, error)
            return
        sample = dict(
            phase=phase, start_tick=start_tick, end_tick=end_tick,
            start_ns=start_ns, end_ns=end_ns, thread_cpu_ns=cpu_ns,
            wall_ns=end_ns - start_ns,
            crossing=end_ns >= window[1],
            warmup=start_ns < window[0] + WARMUP_NS,
            outcome=outcome)
        if len(self._samples) < self._max_samples:
            self._samples.append(sample)
        else:
            self._truncated = True
            self._dropped += 1

    def _start(self, phase, tick_of):
        """Common gate; start-side read order wall -> thread CPU -> tick."""
        window = self._window
        if window is None:
            return None
        start_ns = self._monotonic_ns()
        if start_ns >= window[1]:
            return None
        cpu_start = self._thread_time_ns()
        start_tick = tick_of()
        return start_ns, start_tick, cpu_start

    # ---- callable wrapping ----------------------------------------------------
    def wrap(self, phase, tick_of, epoch_of, segment_of, action, *args, **kwargs):
        """Run ``action`` exactly once with identical semantics.

        ``tick_of``/``epoch_of`` are zero-arg callables returning the current
        authority tick / epoch.  The action's return value and exception
        OBJECT propagate unchanged; an exceptional action is still finalized
        (outcome='error') before its exception continues.  Start-side reader
        failures propagate before the action runs (explicit, not silent).
        """
        if phase not in PHASES:
            raise ValueError(f"unknown early-work phase: {phase!r}")
        if not (callable(tick_of) and callable(epoch_of)
                and callable(segment_of) and callable(action)):
            raise ValueError("tick_of, epoch_of, segment_of and action must be callable")
        started = self._start(phase, tick_of)
        if started is None:
            return action(*args, **kwargs)
        start_ns, start_tick, cpu_start = started
        outcome = "ok"
        try:
            return action(*args, **kwargs)
        except BaseException:
            outcome = "error"
            raise
        finally:
            self._finish(phase, start_ns, start_tick, cpu_start, outcome,
                         action_failed=(outcome != "ok"),
                         tick_of=tick_of, epoch_of=epoch_of, segment_of=segment_of)

    # ---- explicit region boundaries (zero allocation when disabled) ----------
    def begin(self, phase, tick_of, epoch_of, segment_of):
        """Open a region; returns None when unsampled (single wall read only)."""
        if phase not in PHASES:
            raise ValueError(f"unknown early-work phase: {phase!r}")
        if not (callable(tick_of) and callable(epoch_of) and callable(segment_of)):
            raise ValueError("tick_of, epoch_of and segment_of must be callable")
        started = self._start(phase, tick_of)
        if started is None:
            return None
        start_ns, start_tick, cpu_start = started
        return Region(self, phase, tick_of, epoch_of, segment_of,
                      start_ns, start_tick, cpu_start)

    # ---- final record ------------------------------------------------------------
    def report(self, *, source_sha256, identity):
        """Final record; written only after all native cleanup by the caller."""
        ticks = [sample["start_tick"] for sample in self._samples]
        return dict(
            diagnostic="early_manager_work_probe",
            diagnostic_only=True,
            production_performance=False,
            source_sha256=source_sha256,
            identity=dict(identity),
            anchor_epoch=self._epoch,
            anchor_segment=self._segment,
            window_ns=WINDOW_NS,
            warmup_ns=WARMUP_NS,
            window=(None if self._window is None else dict(
                anchor_wall_ns=self._window[0],
                cutoff_wall_ns=self._window[1],
                warmup_after_ns=self._window[0] + WARMUP_NS)),
            samples=list(self._samples),
            truncated=self._truncated,
            dropped=self._dropped,
            max_samples=self._max_samples,
            diagnostic_errors=list(self._diagnostic_errors),
            diagnostic_error_total=self._diagnostic_error_total,
            diagnostic_error_dropped=self._diagnostic_error_dropped,
            diagnostic_clean=self._diagnostic_error_total == 0,
            coverage=dict(
                first_sample_tick=(min(ticks) if ticks else None),
                last_sample_tick=(max(ticks) if ticks else None),
                phases=sorted(PHASES),
                closure="not_closed",
                closure_note=("phases are sequential hotspot segments; uncovered "
                              "gaps between them and any untracked manager work "
                              "are expected and are never summed into a window "
                              "closure claim"),
                instrumentation_overhead=(
                    "two wall + two thread-CPU clock reads per sampled call, "
                    "one wall read per post-cutoff call; zero reads before the "
                    "first anchor; per-tick disk writes: none; start-side "
                    "tick/epoch reads sit inside the wall interval only, "
                    "end-side readers sit outside both intervals"),
            ),
        )
