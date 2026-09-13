"""partition_callback_tail v2: interval localization of the begin() late tail.

Supersedes callback_partition.py (v1, preserved) with these corrections:

1. A rejected/rate_unmet attempt may legitimately end before the release edge
   (terminal < earliest): the late window is then EMPTY - window_ns=0,
   terminal_is_release=False, tail clamped to 0, not an error.  A started
   attempt must still reach the edge.
2. Call counts and cumulative durations must be non-negative; zero calls
   require zero cumulative and None fields; with exactly one call the last
   interval (and the requested value for sleep) must equal the cumulative.
3. Last loop-health/sleep intervals must start at or after
   initial_health_end_ns (both callbacks follow the initial health call).
4. Same-thread callbacks cannot overlap: one's after <= the other's before.
   Overlapping records are rejected, never union-accepted.
5. last_sleep_requested_ns <= cumulative sleep_requested_ns (equal on exactly
   one call).

Only the real producer's three outcomes (started/rate_unmet/rejected) are
supported.  Records lacking all five fields stay 'unavailable'.  Interval
localization only; no sleep/OS causality.
"""
from __future__ import annotations

NEW_FIELDS = ("last_sleep_before_ns", "last_sleep_after_ns",
              "last_sleep_requested_ns",
              "last_health_before_ns", "last_health_after_ns")
BASE_INT_FIELDS = ("entry_ns", "terminal_ns", "earliest_start_ns",
                   "initial_health_end_ns", "sleep_calls", "sleep_elapsed_ns",
                   "sleep_requested_ns", "loop_health_calls", "loop_health_ns")
OUTCOMES = ("started", "rate_unmet", "rejected")


class PartitionError(ValueError):
    """Malformed, partial, reversed, overlapping or inconsistent fields."""


def _exact_int(row, key):
    value = row.get(key)
    if type(value) is not int:
        raise PartitionError(f"{key} must be an exact int")
    return value


def _callback(row, prefix, calls_key, total_key, with_requested):
    calls = _exact_int(row, calls_key)
    total = _exact_int(row, total_key)
    if calls < 0 or total < 0:
        raise PartitionError(f"{calls_key}/{total_key} must be non-negative")
    members = ("before", "after", "requested") if with_requested \
        else ("before", "after")
    values = [row.get(f"{prefix}_{member}_ns") for member in members]
    requested_cum = _exact_int(row, "sleep_requested_ns") if with_requested \
        else None
    if requested_cum is not None and requested_cum < 0:
        raise PartitionError("sleep_requested_ns must be non-negative")
    if calls == 0:
        if total != 0:
            raise PartitionError(f"{calls_key}==0 but {total_key}!=0")
        if requested_cum:
            raise PartitionError("sleep_calls==0 but sleep_requested_ns!=0")
        if any(value is not None for value in values):
            raise PartitionError(f"{prefix} fields present with {calls_key}==0")
        return None
    if any(value is None for value in values):
        raise PartitionError(f"{prefix} fields incomplete for {calls_key}>0")
    for value in values:
        if type(value) is not int or value < 0:
            raise PartitionError(f"{prefix} fields must be exact non-negative ints")
    before, after = values[0], values[1]
    if before > after:
        raise PartitionError(f"{prefix} reversed interval")
    if after - before > total:
        raise PartitionError(f"{prefix} last interval exceeds retained total")
    if calls == 1 and after - before != total:
        raise PartitionError(f"{prefix} single call must equal cumulative")
    if with_requested:
        if values[2] > requested_cum:
            raise PartitionError("last_sleep requested exceeds cumulative")
        if calls == 1 and values[2] != requested_cum:
            raise PartitionError("single sleep requested must equal cumulative")
    return before, after


def partition_callback_tail(row):
    """Partition one probe row's late window; see module docstring."""
    if not isinstance(row, dict):
        raise PartitionError("row must be a dict")
    if row.get("outcome") not in OUTCOMES:
        raise PartitionError("unknown outcome")
    if all(key not in row for key in NEW_FIELDS):
        return {"status": "unavailable",
                "reason": "pre-retention record: five callback fields absent"}
    if any(key not in row for key in NEW_FIELDS):
        raise PartitionError("partial callback field set")

    base = {key: _exact_int(row, key) for key in BASE_INT_FIELDS}
    entry, terminal = base["entry_ns"], base["terminal_ns"]
    earliest = base["earliest_start_ns"]
    initial_health_end = base["initial_health_end_ns"]
    if not entry <= initial_health_end <= terminal:
        raise PartitionError("entry/initial_health/terminal not ordered")
    failed = row["outcome"] != "started"
    if not failed and terminal < earliest:
        raise PartitionError("started attempt did not reach the release edge")

    sleep = _callback(row, "last_sleep", "sleep_calls", "sleep_elapsed_ns",
                      True)
    health = _callback(row, "last_health", "loop_health_calls",
                       "loop_health_ns", False)
    for name, values in (("last_sleep", sleep), ("last_health", health)):
        if values is None:
            continue
        if not (entry <= values[0] and values[1] <= terminal):
            raise PartitionError(f"{name} interval outside begin attempt")
        if values[0] < initial_health_end:
            raise PartitionError(f"{name} starts before initial health end")
    if sleep is not None and health is not None and not (
            sleep[1] <= health[0] or health[1] <= sleep[0]):
        raise PartitionError("same-thread callbacks overlap")

    window_lo = max(earliest, initial_health_end)
    window_ns = max(0, terminal - window_lo)

    def in_window(values):
        if values is None:
            return None
        if window_ns == 0:
            return 0
        lo, hi = max(values[0], window_lo), min(values[1], terminal)
        return max(0, hi - lo)

    sleep_in_window = in_window(sleep)
    health_in_window = in_window(health)
    callback_union_ns = (sleep_in_window or 0) + (health_in_window or 0)

    completed_afters = [values[1] for values in (sleep, health)
                        if values is not None]
    if not completed_afters:
        tail_after_last_callback_ns = None
    elif window_ns == 0:
        tail_after_last_callback_ns = 0
    else:
        tail_after_last_callback_ns = terminal - max(window_lo,
                                                     max(completed_afters))
    tail_ns = tail_after_last_callback_ns or 0
    unattributed_ns = window_ns - callback_union_ns - tail_ns
    if unattributed_ns < 0:
        raise PartitionError("partition does not close")

    return {
        "status": "failed_attempt" if failed else "ok",
        "outcome": row["outcome"],
        "window_ns": window_ns,
        "sleep_in_window_ns": sleep_in_window,
        "health_in_window_ns": health_in_window,
        "callback_union_ns": callback_union_ns,
        "tail_after_last_callback_ns": tail_after_last_callback_ns,
        "unattributed_ns": unattributed_ns,
        "closure_exact":
            callback_union_ns + tail_ns + unattributed_ns == window_ns,
        "terminal_is_release": not failed,
        "coverage": ("completed callbacks only; any callback in flight at "
                     "failure is unobserved" if failed else
                     "window fully partitioned into callback union, tail and "
                     "unattributed parts"),
        "localization_only": True,
    }
