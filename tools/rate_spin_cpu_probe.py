"""Opt-in spin CPU probe: adjacent pacing reads near each group's release edge.

``JointRateSpinCpuProbe`` subclasses the REAL ``JointRateTimingProbe`` (which
itself subclasses ``JointRate``) and adds ONE observation: for adjacent pacing
clock reads inside the final ~1 ms before each group's ``earliest_start_ns``,
the wall gap versus the CURRENT-THREAD CPU gap of the same read pair.

Contract (enforced, not narrated):
- parent ``JointRate`` / ``JointRateTimingProbe`` / the runner are unchanged;
  health/sleep call counts, arguments, exception objects, lateness/anchor/
  period logic all come from ``super()`` untouched;
- constructor is parent-compatible plus one injected ``thread_now``;
- pairs straddling a health or sleep call are excluded and the retained
  previous observation is cleared (boundary pollution is never counted);
- pairs retained when the closing read lands in the window; a pair whose
  opening read precedes the window is kept and marked ``crossing``;
- external callback time (health/sleep) is never counted as spin;
- per group only scalars are kept (counts + one max-gap record); no per-poll
  dicts, no disk writes, no unbounded lists;
- after the parent's begin completes or fails (its ``rate_timing_probe``
  record is already emitted), exactly one ``rate_spin_cpu_probe`` record is
  emitted, diagnostic-only;
- a thread-CPU read failure is listed (bounded) and disables CPU sampling for
  the rest of the group; it never masks the business exception in flight;
  cancellation types (KeyboardInterrupt/SystemExit/InterruptedError)
  propagate;
- no wall-minus-CPU OS/FC attribution; no zero-overhead claim: one extra
  thread-CPU read per pacing clock read while ``begin_group`` is active.
"""

import time

from Simulator.wksim_runtime.joint_rate_probe import JointRateTimingProbe


SPIN_WINDOW_NS = 1_000_000
BIG_GAP_NS = 10_000
MAX_RECORD_ERRORS = 32
CANCEL_TYPES = (KeyboardInterrupt, SystemExit, InterruptedError)


class _SpinWindow:
    """Per-group scalar aggregates; allocated once per begin_group."""

    __slots__ = ("start_tick", "window_lo_ns", "earliest_ns", "prev_wall_ns",
                 "prev_cpu_ns", "pairs_observed", "pairs_valid",
                 "pairs_invalid_cpu", "excluded_boundary_crossings",
                 "big_gap_count", "max_gap", "cpu_errors", "cpu_disabled",
                 "in_boundary", "release_crossed", "release_crossing",
                 "release_lateness_ns")

    def __init__(self, start_tick, earliest_ns):
        self.start_tick = start_tick
        self.window_lo_ns = earliest_ns - SPIN_WINDOW_NS
        self.earliest_ns = earliest_ns
        self.prev_wall_ns = None
        self.prev_cpu_ns = None
        self.pairs_observed = 0
        self.pairs_valid = 0
        self.pairs_invalid_cpu = 0
        self.excluded_boundary_crossings = 0
        self.big_gap_count = 0
        self.max_gap = None
        self.cpu_errors = 0
        self.cpu_disabled = False
        self.in_boundary = False
        self.release_crossed = False
        self.release_crossing = None
        self.release_lateness_ns = None

    def clear_previous(self):
        """A health/sleep boundary intervened: drop the retained read."""
        if self.prev_wall_ns is not None:
            self.excluded_boundary_crossings += 1
        self.prev_wall_ns = None
        self.prev_cpu_ns = None

    def observe(self, wall_ns, cpu_ns):
        """One adjacent-read pair (prev -> current).  A pair counts when the
        closing read lands in the window, OR when it is the FIRST read at or
        past the release edge and the opening read precedes it -- that
        release-crossing pair is the single most important measurement and is
        kept with ``crosses_release`` and its lateness.  After it, no further
        pairs are collected.  A first read already past the edge has no
        comparable previous point and forms no pair.  Reads inside a
        health/sleep boundary never form pairs and never refresh the retained
        read."""
        if self.in_boundary or self.release_crossed:
            return
        prev_wall, prev_cpu = self.prev_wall_ns, self.prev_cpu_ns
        self.prev_wall_ns = wall_ns
        self.prev_cpu_ns = cpu_ns
        if prev_wall is None:
            return
        crosses_release = wall_ns >= self.earliest_ns
        if crosses_release:
            if prev_wall >= self.earliest_ns:
                return  # already past the edge: nothing comparable
            self.release_crossed = True
            self.release_lateness_ns = wall_ns - self.earliest_ns
        elif wall_ns < self.window_lo_ns:
            return  # outside the window entirely; not a pair we report
        self.pairs_observed += 1
        crossing = prev_wall < self.window_lo_ns
        gap_wall = wall_ns - prev_wall
        gap_cpu = None
        cpu_ok = (not self.cpu_disabled and cpu_ns is not None
                  and prev_cpu is not None and cpu_ns >= prev_cpu)
        if cpu_ok:
            gap_cpu = cpu_ns - prev_cpu
            self.pairs_valid += 1
        else:
            self.pairs_invalid_cpu += 1
        if gap_wall >= BIG_GAP_NS:
            self.big_gap_count += 1
        if cpu_ok and (self.max_gap is None
                       or gap_wall > self.max_gap["gap_wall_ns"]):
            # The max complete pair over ALL valid pairs; the dict is built
            # only when the candidate actually wins.
            self.max_gap = dict(gap_wall_ns=gap_wall, gap_cpu_ns=gap_cpu,
                                prev_wall_ns=prev_wall, wall_ns=wall_ns,
                                prev_cpu_ns=prev_cpu, cpu_ns=cpu_ns,
                                crossing=crossing,
                                crosses_release=crosses_release)
        if crosses_release:
            self.release_crossing = dict(
                gap_wall_ns=gap_wall,
                gap_cpu_ns=gap_cpu,
                prev_wall_ns=prev_wall,
                wall_ns=wall_ns,
                prev_cpu_ns=prev_cpu,
                cpu_ns=cpu_ns,
                lateness_ns=self.release_lateness_ns)


class JointRateSpinCpuProbe(JointRateTimingProbe):
    """Parent-compatible constructor plus an injected thread clock."""

    def __init__(self, epoch, requested_rate, record,
                 now=time.monotonic_ns, sleep=time.sleep,
                 thread_now=time.thread_time_ns):
        if not callable(thread_now):
            raise ValueError("thread_now must be callable")
        self._thread_now = thread_now
        self._spin = None
        self._spin_record_errors = []
        self._spin_record_error_total = 0
        super().__init__(epoch, requested_rate, record, now=now, sleep=sleep)

    def _note_record_failure(self, message):
        self._spin_record_error_total += 1
        if len(self._spin_record_errors) < MAX_RECORD_ERRORS:
            self._spin_record_errors.append(message)

    # ---- pacing-read observation -------------------------------------------------
    def _probe_now(self):
        value = super()._probe_now()
        spin = self._spin
        if spin is None:
            return value
        if spin.cpu_disabled:
            spin.observe(value, None)
            return value
        try:
            cpu = self._thread_now()
        except CANCEL_TYPES:
            raise
        except Exception:
            # Ordinary CPU sampling failure: list it and stop CPU sampling for
            # the rest of this group; wall observation continues.
            spin.cpu_errors += 1
            spin.cpu_disabled = True
            spin.observe(value, None)
            return value
        # CPU values must be plain non-negative ints: bool/str/float/negative
        # or a backwards step is listed and disables this group's CPU
        # sampling instead of raising at the comparison site.
        if (type(cpu) is not int or cpu < 0
                or (spin.prev_cpu_ns is not None and cpu < spin.prev_cpu_ns)):
            spin.cpu_errors += 1
            spin.cpu_disabled = True
            spin.observe(value, None)
            return value
        spin.observe(value, cpu)
        return value

    def _probe_sleep(self, seconds):
        spin = self._spin
        if spin is not None:
            # Sleep boundary: exclude the whole span.  Clear before (the pair
            # ending at the boundary entry stays clean), flag during (the
            # parent's before/after reads form no pair), clear after (the
            # retained read restarts post-sleep).
            spin.clear_previous()
            spin.in_boundary = True
        try:
            return super()._probe_sleep(seconds)
        finally:
            if spin is not None:
                spin.in_boundary = False
                spin.clear_previous()

    # ---- group lifecycle ------------------------------------------------------------
    def begin_group(self, tick, health):
        def observed_health():
            spin = self._spin
            if spin is not None:
                # Health boundary: same exclusion discipline as sleep; the flag
                # also covers any clock reads the health body itself performs.
                spin.clear_previous()
                spin.in_boundary = True
            try:
                health()
            finally:
                if spin is not None:
                    spin.in_boundary = False
                    spin.clear_previous()

        _, earliest = self._planned_edges()
        self._spin = _SpinWindow(tick, earliest)
        outcome = "rejected"
        error = None
        try:
            super().begin_group(tick, observed_health)
            outcome = "started"
        except BaseException as exc:
            error = exc
            outcome = ("rate_unmet" if type(error).__name__ == "RateUnmet"
                       else "error")
        spin, self._spin = self._spin, None
        # The parent's rate_timing_probe record is already emitted at this
        # point (its finally ran); ours follows, diagnostic-only.  A
        # cancellation from our own record keeps the business exception in
        # flight and is listed separately; only on business success does the
        # cancellation itself propagate.
        try:
            self._finish_spin_record(spin, outcome, earliest)
        except CANCEL_TYPES as cancel:
            self._note_record_failure(repr(cancel))
            if error is None:
                raise
        except Exception as record_error:
            self._note_record_failure(repr(record_error))
        if error is not None:
            raise error

    def _finish_spin_record(self, spin, outcome, earliest):
        fields = dict(
            diagnostic="rate_spin_cpu_probe",
            classification="diagnostic_only",
            production_performance=False,
            outcome=outcome,
            start_tick=spin.start_tick,
            end_tick=spin.start_tick + 4,
            earliest_start_ns=earliest,
            window_lo_ns=spin.window_lo_ns,
            window_ns=SPIN_WINDOW_NS,
            pairs_observed=spin.pairs_observed,
            pairs_valid=spin.pairs_valid,
            pairs_invalid_cpu=spin.pairs_invalid_cpu,
            excluded_boundary_crossings=spin.excluded_boundary_crossings,
            big_gap_count=spin.big_gap_count,
            big_gap_threshold_ns=BIG_GAP_NS,
            max_gap=spin.max_gap,
            release_crossed=spin.release_crossed,
            release_crossing=spin.release_crossing,
            release_lateness_ns=spin.release_lateness_ns,
            cpu_errors=spin.cpu_errors,
            cpu_disabled=spin.cpu_disabled,
            instrumentation_overhead=(
                "one extra current-thread CPU read per pacing clock read while "
                "begin_group is active; per-group scalars only; no per-poll "
                "allocation, no disk writes; wall minus thread CPU is not an "
                "OS/FC attribution"),
        )
        self.record("rate_spin_cpu_probe", **fields)
