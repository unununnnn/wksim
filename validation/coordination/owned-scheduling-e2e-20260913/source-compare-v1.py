"""Read-only delta between two owned-scheduling snapshots.

Input: two snapshots produced by ``tools/capture_owned_scheduling.py`` — one
taken before and one after a timed section. The tool first binds the pair and
only then compares; if the pair cannot be bound, it still writes an explicit
``unbound`` report instead of inventing a comparison.

Binding follows the main session's discipline:
- the two snapshots must reference the same ``children.sha256``;
- both must carry the same non-empty ``host.boot_id``; PID reuse is never
  stitched across a boot change;
- ``after.captured.monotonic_ns`` must be strictly greater than before;
- each role's ``pid``/``pgid``/``start_ticks`` must match across the pair.

Per thread, deltas are only produced for rows that are ``captured`` in BOTH
snapshots and whose ``tid``/``start_ticks`` are unchanged. A thread that
vanished, appeared, was unstable (``partial``), or whose counters were
disabled is reported as ``null`` with a reason — never 0. A negative counter
delta is reported as ``null`` and flagged; it is never clamped. ``runqueue``
and ``timeslice`` deltas require ``sched_schedstats=1`` on both sides.

Priority/policy/affinity changes are recorded as before/after transitions.
``kernel_prio`` (``/proc/<tid>/sched`` ``prio``) is NOT the RT priority and is
kept separate from ``rt_priority`` (``stat`` field 40).

Read-only: inputs are only opened for reading, output is a single new JSON
file created exclusively (mode ``x``). The two-sample total is a difference
between two moments and this tool does not attribute it to any single timed
event; it emits no performance verdict.

Usage:
  python3 -B tools/compare_owned_scheduling.py \
      --before <run>/owned-scheduling-before.json \
      --after <run>/owned-scheduling-after.json \
      --output <run>/owned-scheduling-delta.json
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

SCHEMA = "wksim.owned-scheduling-comparison.v1"
SNAPSHOT_SCHEMA = "wksim.owned-scheduling-snapshot.v1"
SCOPE = (
    "read-only delta between two owned-scheduling snapshots; unstable, "
    "missing or disabled metrics are null with a reason, never 0; negative "
    "deltas are flagged and not clamped; no performance verdict and no single-"
    "event attribution of the two-sample total"
)
CTXT_METRICS = ("voluntary_ctxt_switches", "nonvoluntary_ctxt_switches")
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def _is_hex64(value):
    return isinstance(value, str) and bool(HEX64.match(value))


def _is_plain_int(value, minimum=0):
    """True only for a real int (bool rejected) at or above ``minimum``."""
    return type(value) is int and value >= minimum


def _load_snapshot(path):
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ValueError(f"cannot read snapshot {path}: {error!r}")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"snapshot {path} is not UTF-8 JSON: {error!r}")
    if not isinstance(document, dict) or document.get("schema") != SNAPSHOT_SCHEMA:
        raise ValueError(f"{path}: unexpected snapshot schema "
                         f"{document.get('schema') if isinstance(document, dict) else None!r}")
    for key in ("children", "host", "captured", "procs"):
        if not isinstance(document.get(key), dict):
            raise ValueError(f"{path}: missing {key} object")
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
            "document": document}


def _binding_reasons(before, after):
    reasons = []
    b_children = before["document"]["children"].get("sha256")
    a_children = after["document"]["children"].get("sha256")
    if not _is_hex64(b_children) or not _is_hex64(a_children):
        reasons.append("children_sha256_unavailable")
    elif b_children != a_children:
        reasons.append("children_sha256_mismatch")
    b_boot = before["document"]["host"].get("boot_id")
    a_boot = after["document"]["host"].get("boot_id")
    b_boot_ok = isinstance(b_boot, str) and bool(b_boot.strip())
    a_boot_ok = isinstance(a_boot, str) and bool(a_boot.strip())
    if not b_boot_ok or not a_boot_ok:
        reasons.append("boot_id_unavailable")
    elif b_boot != a_boot:
        reasons.append("boot_id_mismatch")
    b_mono = before["document"]["captured"].get("monotonic_ns")
    a_mono = after["document"]["captured"].get("monotonic_ns")
    if not _is_plain_int(b_mono, 0) or not _is_plain_int(a_mono, 0):
        reasons.append("monotonic_unavailable")
    elif a_mono <= b_mono:
        reasons.append("monotonic_not_increasing")
    return reasons


def _host_schedstats_reason(before, after):
    """None when both hosts report sched_schedstats=1, else a reason string."""
    parts = []
    if before["document"]["host"].get("sched_schedstats") != "1":
        value = before["document"]["host"].get("sched_schedstats")
        parts.append("before=" + (value if isinstance(value, str) and value else "missing"))
    if after["document"]["host"].get("sched_schedstats") != "1":
        value = after["document"]["host"].get("sched_schedstats")
        parts.append("after=" + (value if isinstance(value, str) and value else "missing"))
    if not parts:
        return None
    return "host_sched_schedstats_not_enabled(" + ";".join(parts) + ")"


def _schedstat_valid(row):
    schedstat = row.get("schedstat")
    return bool(schedstat and schedstat.get("runqueue_counters_valid"))


def _runqueue_reason(b_row, a_row):
    parts = []
    if not _schedstat_valid(b_row):
        reason = (b_row.get("schedstat") or {}).get("runqueue_invalid_reason")
        parts.append("before=" + (reason or "unknown"))
    if not _schedstat_valid(a_row):
        reason = (a_row.get("schedstat") or {}).get("runqueue_invalid_reason")
        parts.append("after=" + (reason or "unknown"))
    return "runqueue_counters_invalid(" + ";".join(parts) + ")"


def _as_int(value):
    """Coerce a snapshot field to int without accepting bool/None/garbage."""
    if type(value) is int and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _delta_pair(delta, unavailable, negative, name, before_value, after_value,
                missing_reason):
    if before_value is None or after_value is None:
        delta[name] = None
        unavailable[name] = missing_reason
        return
    value = after_value - before_value
    if value < 0:
        delta[name] = None
        negative.append(name)
        unavailable[name] = "negative_counter_delta"
    else:
        delta[name] = value


def _thread_delta(b_row, a_row, host_reason=None):
    delta = {}
    unavailable = {}
    negative = []

    b_stat = b_row.get("stat")
    a_stat = a_row.get("stat")
    for name in ("utime_ticks", "stime_ticks"):
        if not isinstance(b_stat, dict):
            delta[name] = None
            unavailable[name] = "stat_unavailable_before"
        elif not isinstance(a_stat, dict):
            delta[name] = None
            unavailable[name] = "stat_unavailable_after"
        else:
            _delta_pair(delta, unavailable, negative, name,
                        b_stat.get(name), a_stat.get(name), "stat_metric_missing")

    b_sched = b_row.get("schedstat")
    a_sched = a_row.get("schedstat")
    if not isinstance(b_sched, dict):
        delta["run_ns"] = None
        unavailable["run_ns"] = "schedstat_unavailable_before"
    elif not isinstance(a_sched, dict):
        delta["run_ns"] = None
        unavailable["run_ns"] = "schedstat_unavailable_after"
    else:
        _delta_pair(delta, unavailable, negative, "run_ns",
                    b_sched.get("run_ns"), a_sched.get("run_ns"),
                    "schedstat_run_ns_missing")

    # Waiting/timeslice counters are effective only when BOTH hosts report
    # sched_schedstats=1 AND both row flags agree. A row flag of True that
    # contradicts a disabled/missing host is not trusted. CPU run (run_ns) is
    # always kept.
    rows_valid = _schedstat_valid(b_row) and _schedstat_valid(a_row)
    if host_reason is None and rows_valid:
        _delta_pair(delta, unavailable, negative, "runqueue_ns",
                    b_sched.get("runqueue_ns"), a_sched.get("runqueue_ns"),
                    "runqueue_ns_missing")
        _delta_pair(delta, unavailable, negative, "timeslices",
                    b_sched.get("timeslices"), a_sched.get("timeslices"),
                    "timeslices_missing")
    else:
        parts = []
        if host_reason is not None:
            parts.append(host_reason)
        if not rows_valid:
            parts.append(_runqueue_reason(b_row, a_row))
        reason = ";".join(parts)
        delta["runqueue_ns"] = None
        delta["timeslices"] = None
        unavailable["runqueue_ns"] = reason
        unavailable["timeslices"] = reason

    b_status = b_row.get("proc_status")
    a_status = a_row.get("proc_status")
    for name in CTXT_METRICS:
        if not isinstance(b_status, dict):
            delta[name] = None
            unavailable[name] = "proc_status_unavailable_before"
        elif not isinstance(a_status, dict):
            delta[name] = None
            unavailable[name] = "proc_status_unavailable_after"
        else:
            _delta_pair(delta, unavailable, negative, name,
                        _as_int(b_status.get(name)), _as_int(a_status.get(name)),
                        "ctxt_switches_missing")
    return {"delta": delta, "delta_unavailable": unavailable,
            "negative_counters": sorted(negative)}


def _transitions(b_row, a_row):
    b_stat = b_row.get("stat") if isinstance(b_row.get("stat"), dict) else {}
    a_stat = a_row.get("stat") if isinstance(a_row.get("stat"), dict) else {}
    b_ps = b_row.get("proc_status") if isinstance(b_row.get("proc_status"), dict) else {}
    a_ps = a_row.get("proc_status") if isinstance(a_row.get("proc_status"), dict) else {}
    b_sched = b_row.get("sched") if isinstance(b_row.get("sched"), dict) else {}
    a_sched = a_row.get("sched") if isinstance(a_row.get("sched"), dict) else {}
    pairs = {
        "state": (b_stat.get("state"), a_stat.get("state")),
        "priority": (b_stat.get("priority"), a_stat.get("priority")),
        "nice": (b_stat.get("nice"), a_stat.get("nice")),
        "rt_priority": (b_stat.get("rt_priority"), a_stat.get("rt_priority")),
        "policy": (b_stat.get("policy"), a_stat.get("policy")),
        "kernel_prio": (b_sched.get("kernel_prio"), a_sched.get("kernel_prio")),
        "cpus_allowed_list": (b_ps.get("cpus_allowed_list"),
                              a_ps.get("cpus_allowed_list")),
    }
    transitions = {name: {"before": before, "after": after,
                          "changed": before != after}
                   for name, (before, after) in pairs.items()}
    transitions["kernel_prio"]["note"] = (
        "kernel-internal prio (CFS 120+nice, RT 99-rt_priority); NOT the "
        "RT/FIFO sched priority, compare rt_priority instead")
    return transitions


def _compare_threads(b_proc, a_proc, host_reason=None):
    compared = []
    unavailable = []
    b_rows = {}
    a_rows = {}
    for row in b_proc.get("threads", []):
        tid = row.get("tid")
        if _is_plain_int(tid, 1):
            b_rows[tid] = row
        else:
            unavailable.append({"tid": tid, "status": "unavailable",
                                "unavailable_reason": "thread_tid_invalid_before"})
    for row in a_proc.get("threads", []):
        tid = row.get("tid")
        if _is_plain_int(tid, 1):
            a_rows[tid] = row
        else:
            unavailable.append({"tid": tid, "status": "unavailable",
                                "unavailable_reason": "thread_tid_invalid_after"})
    for tid in sorted(set(b_rows) | set(a_rows)):
        b_row = b_rows.get(tid)
        a_row = a_rows.get(tid)
        if b_row is None:
            unavailable.append({"tid": tid, "status": "unavailable",
                                "unavailable_reason": "thread_added_after"})
            continue
        if a_row is None:
            unavailable.append({"tid": tid, "status": "unavailable",
                                "unavailable_reason": "thread_vanished_after",
                                "start_ticks": b_row.get("start_ticks")})
            continue
        b_start = b_row.get("start_ticks")
        a_start = a_row.get("start_ticks")
        if not _is_plain_int(b_start, 0) or not _is_plain_int(a_start, 0):
            # A missing/invalid lifetime on either side cannot prove the same
            # thread, so it is never matched (no None == None stitching).
            unavailable.append({"tid": tid, "status": "unavailable",
                                "unavailable_reason": "thread_identity_unavailable",
                                "start_ticks_before": b_start,
                                "start_ticks_after": a_start})
            continue
        if b_start != a_start:
            unavailable.append({"tid": tid, "status": "unavailable",
                                "unavailable_reason": "thread_reuse_not_stitched",
                                "start_ticks_before": b_start,
                                "start_ticks_after": a_start})
            continue
        if b_row.get("status") != "captured":
            unavailable.append({"tid": tid, "status": "unavailable",
                                "unavailable_reason": "thread_unavailable_before",
                                "before_reason": b_row.get("unavailable_reason"),
                                "start_ticks": b_start})
            continue
        if a_row.get("status") != "captured":
            unavailable.append({"tid": tid, "status": "unavailable",
                                "unavailable_reason": "thread_unavailable_after",
                                "after_reason": a_row.get("unavailable_reason"),
                                "start_ticks": a_start})
            continue
        entry = {"tid": tid, "status": "compared", "start_ticks": b_start,
                 "comm": b_row.get("comm")}
        entry.update(_thread_delta(b_row, a_row, host_reason))
        entry["transitions"] = _transitions(b_row, a_row)
        compared.append(entry)
    return compared, unavailable


def _valid_identity(identity):
    """pid/pgid/start_ticks must be plain ints; missing values prove nothing."""
    return (isinstance(identity, dict)
            and _is_plain_int(identity.get("pid"), 1)
            and _is_plain_int(identity.get("pgid"), 1)
            and _is_plain_int(identity.get("start_ticks"), 0))


def _compare_role(role, b_proc, a_proc, host_reason=None):
    if b_proc is None:
        return {"role": role, "status": "unavailable",
                "unavailable_reason": "role_added_after"}, [], []
    if a_proc is None:
        return {"role": role, "status": "unavailable",
                "unavailable_reason": "role_removed_after"}, [], []
    b_identity = b_proc.get("expected")
    a_identity = a_proc.get("expected")
    if not _valid_identity(b_identity) or not _valid_identity(a_identity):
        return ({"role": role, "status": "unavailable",
                 "unavailable_reason": "identity_unavailable",
                 "expected_before": b_identity,
                 "expected_after": a_identity}, [], [])
    if any(b_identity.get(key) != a_identity.get(key)
           for key in ("pid", "pgid", "start_ticks")):
        return ({"role": role, "status": "unavailable",
                 "unavailable_reason": "identity_mismatch",
                 "expected_before": b_identity,
                 "expected_after": a_identity}, [], [])
    if b_proc.get("status") == "unavailable" or a_proc.get("status") == "unavailable":
        return ({"role": role, "status": "unavailable",
                 "unavailable_reason": "process_unavailable",
                 "before_status": b_proc.get("status"),
                 "before_reason": b_proc.get("unavailable_reason"),
                 "after_status": a_proc.get("status"),
                 "after_reason": a_proc.get("unavailable_reason"),
                 "expected": b_identity}, [], [])
    compared, unavailable = _compare_threads(b_proc, a_proc, host_reason)
    partial = (b_proc.get("status") == "partial"
               or a_proc.get("status") == "partial")
    entry = {"role": role, "status": "partial" if partial else "compared",
             "unavailable_reason": None,
             "before_status": b_proc.get("status"),
             "after_status": a_proc.get("status"),
             "expected": b_identity,
             "threads_compared": len(compared),
             "threads_unavailable": len(unavailable),
             "compared_threads": compared,
             "unavailable_threads": unavailable}
    if partial:
        entry["partial_reason"] = "process_partial_in_one_snapshot"
    return entry, compared, unavailable


class SnapshotComparison:
    def __init__(self, before, after, output):
        self.before = _load_snapshot(before)
        self.after = _load_snapshot(after)
        self.output = Path(output)

    def compare(self):
        b_doc = self.before["document"]
        a_doc = self.after["document"]
        b_meta = {"path": self.before["path"], "sha256": self.before["sha256"],
                  "phase": b_doc.get("phase"),
                  "children_sha256": b_doc["children"].get("sha256"),
                  "boot_id": b_doc["host"].get("boot_id"),
                  "monotonic_ns": b_doc["captured"].get("monotonic_ns")}
        a_meta = {"path": self.after["path"], "sha256": self.after["sha256"],
                  "phase": a_doc.get("phase"),
                  "children_sha256": a_doc["children"].get("sha256"),
                  "boot_id": a_doc["host"].get("boot_id"),
                  "monotonic_ns": a_doc["captured"].get("monotonic_ns")}
        reasons = _binding_reasons(self.before, self.after)
        bound = not reasons
        roles = {}
        compared = unavailable = 0
        if bound:
            b_procs = b_doc["procs"]
            a_procs = a_doc["procs"]
            host_reason = _host_schedstats_reason(self.before, self.after)
            for role in sorted(set(b_procs) | set(a_procs)):
                entry, role_compared, role_unavailable = _compare_role(
                    role, b_procs.get(role), a_procs.get(role), host_reason)
                roles[role] = entry
                compared += len(role_compared)
                unavailable += len(role_unavailable)
        b_mono = b_meta["monotonic_ns"]
        a_mono = a_meta["monotonic_ns"]
        monotonic_delta = (a_mono - b_mono
                           if _is_plain_int(b_mono, 0) and _is_plain_int(a_mono, 0)
                           else None)
        result = {
            "schema": SCHEMA,
            "scope": SCOPE,
            "before": b_meta,
            "after": a_meta,
            "binding": {
                "status": "bound" if bound else "unbound",
                "reasons": reasons,
                "children_sha256": b_meta["children_sha256"],
                "boot_id": b_meta["boot_id"],
                "monotonic_delta_ns": monotonic_delta,
                "roles": len(roles),
            },
            "roles": roles,
            "summary": {
                "roles": len(roles),
                "threads_compared": compared,
                "threads_unavailable": unavailable,
            },
            "performance_verdict": "not_evaluated",
            "attribution": "not_evaluated",
            "attribution_note": ("two-sample total difference; not attributed "
                                 "to any single timed event"),
            "comparator_sha256": hashlib.sha256(
                Path(__file__).read_bytes()).hexdigest(),
        }
        if not bound:
            result["summary"]["unbound_reason"] = reasons
        self.output.parent.mkdir(parents=True, exist_ok=True)
        with self.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False, sort_keys=True)
            stream.write("\n")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="new JSON file; refuses to overwrite")
    args = parser.parse_args()
    result = SnapshotComparison(args.before, args.after, args.output).compare()
    print(json.dumps({"output": str(args.output),
                      "binding": result["binding"]["status"],
                      "reasons": result["binding"]["reasons"],
                      **result["summary"],
                      "performance_verdict": result["performance_verdict"]}))
    return 0 if result["binding"]["status"] == "bound" else 1


if __name__ == "__main__":
    sys.exit(main())
