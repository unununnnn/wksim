"""Read-only scheduling snapshot for the children owned by one wksim run.

Purpose: capture the *owned* child processes (those recorded in a run's
children-start.json) immediately before and immediately after a timed
experiment, so a timing anomaly is not attributed to WSL boot or thread
scheduling behaviour by assumption. This is a diagnostic capture only; it
does not schedule, measure or judge anything.

Discipline (read-only, evidence-preserving):
- only processes whose live /proc identity matches the recorded ``pid`` AND
  ``pgid`` AND ``start_ticks`` are sampled. A mismatch, a reused PID or a
  disappeared process is recorded as ``unavailable`` with a reason; it is
  never reported as zero and never as a pass;
- each process identity is re-read before and after its thread inventory; a
  process whose identity changes during the read has that inventory discarded
  and is marked ``unavailable``;
- each thread's ``stat`` is read before and after its ``schedstat`` /
  ``sched`` / ``status``; if a thread's identity (start_ticks/pgid) changes,
  every metric from that thread is discarded (set to null), the thread is
  marked ``unavailable`` and the process becomes ``partial`` — an unstable
  row is never presented as captured data;
- the children file is hashed over its raw bytes, then decoded for parsing, so
  a CRLF file is not silently normalised before hashing;
- ``/proc/<tid>/schedstat`` runqueue/timeslice counters are only effective
  when ``/proc/sys/kernel/sched_schedstats`` is ``1``; otherwise the effective
  values are null with a disabled reason while the raw reading and the always
  valid exec-time (sum_exec_runtime) are retained;
- ``/proc/<tid>/sched`` ``prio`` is renamed ``kernel_prio`` because it is the
  kernel-internal priority, not ``sched_getparam``'s RT priority. The explicit
  ``rt_priority`` and ``policy`` come from the thread's ``stat`` fields
  (fields 40/41), and are null when the line is too short;
- a metric that cannot be read is ``null`` plus an entry in ``missing``; a
  missing value is never reported as 0;
- ``/proc/<tid>/status`` is exposed as ``proc_status`` so it cannot collide
  with the thread's own ``status`` verdict (captured/unavailable);
- no priority, nice, affinity, scheduler policy or kernel switch is written,
  no signal is sent, and no process is started or stopped;
- output is a single new JSON file created exclusively (mode ``x``); an
  existing file is never overwritten and no result is deleted.

This tool does not integrate with the runner, does not poll in the
background, and emits no performance verdict.

Usage (on the WSL host, once before and once after the timed section):
  python3 -B tools/capture_owned_scheduling.py \
      --children <run>/children-start.json \
      --output <run>/owned-scheduling-before.json --phase before
  python3 -B tools/capture_owned_scheduling.py \
      --children <run>/children-start.json \
      --output <run>/owned-scheduling-after.json --phase after
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

SCHEMA = "wksim.owned-scheduling-snapshot.v1"
SCOPE = (
    "read-only diagnostic snapshot; owned children matched by exact "
    "pid/pgid/start_ticks; thread metrics discarded on identity change; "
    "schedstat runqueue counters effective only when sched_schedstats=1; "
    "missing metrics are null, never 0; no performance verdict"
)
MAX_PID = 2 ** 31
MAX_START_TICKS = 2 ** 63
# Index of rt_priority (stat field 40) and policy (field 41) after the comm
# field, i.e. field_number - 3.
STAT_RT_PRIORITY_INDEX = 37
STAT_POLICY_INDEX = 38


def _require_int(value, field, minimum, maximum):
    """Reject non-int, bool, negative and out-of-range identity fields."""
    if type(value) is not int or isinstance(value, bool):
        raise ValueError(f"{field} must be a plain integer, got {value!r}")
    if not minimum <= value <= maximum:
        raise ValueError(f"{field} out of bounds: {value!r}")
    return value


def _split_stat(text):
    """Return (comm, fields-after-comm) for a /proc stat line."""
    open_paren = text.index("(")
    close_paren = text.rindex(")")
    comm = text[open_paren + 1:close_paren]
    return comm, text[close_paren + 1:].split()


def _parse_status(text):
    """Parse a /proc status file into {key: value-string}."""
    if text is None:
        return None
    fields = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def _parse_kernel_prio(text):
    """Return the kernel-internal 'prio' from a /proc/<tid>/sched file."""
    if text is None:
        return None
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if not sep or key.strip() != "prio":
            continue
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _parse_int_fields(text, count=3):
    if text is None:
        return None
    parts = text.split()
    if len(parts) < count:
        return None
    try:
        return [int(part) for part in parts[:count]]
    except ValueError:
        return None


def _system_now():
    """Wall/monotonic/boot clock snapshot; boottime is None where absent."""
    try:
        boottime_ns = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    except (AttributeError, OSError, ValueError):
        boottime_ns = None
    return {"wall_utc": datetime.now(timezone.utc).isoformat(),
            "monotonic_ns": time.monotonic_ns(),
            "boottime_ns": boottime_ns}


def _default_clock_ticks():
    try:
        return os.sysconf("SC_CLK_TCK")
    except (AttributeError, OSError, ValueError):
        return None


class ProcReader:
    """Read-only access to a proc tree; missing files become None, not 0."""

    def __init__(self, root):
        self.root = Path(root)

    def read_text(self, *parts):
        for part in parts:
            if (not isinstance(part, str) or not part or part in (".", "..")
                    or "/" in part or "\\" in part or "\x00" in part):
                raise ValueError(f"unsafe proc path component: {part!r}")
        try:
            return (self.root.joinpath(*parts)).read_text(encoding="utf-8",
                                                          errors="replace")
        except (OSError, ValueError):
            return None

    def identity(self, pid):
        """Live identity of a process, or None if vanished/unreadable."""
        text = self.read_text(str(pid), "stat")
        if text is None:
            return None
        try:
            comm, fields = _split_stat(text)
            return {"pid": pid, "comm": comm, "state": fields[0],
                    "pgid": int(fields[2]), "num_threads": int(fields[17]),
                    "start_ticks": int(fields[19])}
        except (IndexError, ValueError):
            return None

    def list_threads(self, pid):
        """Decimal TIDs under task/, or None when the directory is unreadable."""
        try:
            entries = list((self.root / str(pid) / "task").iterdir())
        except OSError:
            return None
        tids = []
        for entry in entries:
            name = entry.name
            if name.isdecimal() and 0 < int(name) <= MAX_PID:
                tids.append(int(name))
        return sorted(tids)

    def _read_schedstat(self, pid, tid, schedstats_raw):
        text = self.read_text(str(pid), "task", str(tid), "schedstat")
        fields = _parse_int_fields(text)
        if fields is None:
            return None, ["schedstat"]
        run_ns, runqueue_ns, timeslices = fields
        valid = schedstats_raw == "1"
        if valid:
            reason = None
        elif schedstats_raw is None:
            reason = "sched_schedstats_unreadable"
        else:
            reason = "sched_schedstats_disabled"
        entry = {
            "run_ns": run_ns,
            "runqueue_ns": runqueue_ns if valid else None,
            "timeslices": timeslices if valid else None,
            "raw": {"run_ns": run_ns, "runqueue_ns": runqueue_ns,
                    "timeslices": timeslices},
            "runqueue_counters_valid": valid,
            "runqueue_invalid_reason": reason,
        }
        missing = [] if valid else ["schedstat.runqueue_ns", "schedstat.timeslices"]
        return entry, missing

    def _read_sched(self, pid, tid):
        text = self.read_text(str(pid), "task", str(tid), "sched")
        if text is None:
            return None, ["sched"]
        prio = _parse_kernel_prio(text)
        if prio is None:
            return None, ["sched.kernel_prio"]
        return {"kernel_prio": prio}, []

    def _read_proc_status(self, pid, tid):
        text = self.read_text(str(pid), "task", str(tid), "status")
        status = _parse_status(text)
        if status is None:
            return None, ["status"]
        entry = {
            "cpus_allowed_list": status.get("Cpus_allowed_list"),
            "voluntary_ctxt_switches": status.get("voluntary_ctxt_switches"),
            "nonvoluntary_ctxt_switches": status.get("nonvoluntary_ctxt_switches"),
        }
        missing = [f"status.{key}" for key in entry if entry[key] is None]
        return entry, missing

    def read_thread(self, pid, tid, schedstats_raw="1"):
        """Read one thread and re-verify its identity; discard if unstable."""
        record = {"tid": tid, "status": "unavailable",
                  "unavailable_reason": None, "start_ticks": None,
                  "comm": None, "stat": None, "schedstat": None, "sched": None,
                  "proc_status": None, "missing": [], "read_consistent": False}
        before_text = self.read_text(str(pid), "task", str(tid), "stat")
        if before_text is None:
            record["unavailable_reason"] = "thread_stat_unreadable"
            record["missing"].append("stat")
            return record
        try:
            comm, before = _split_stat(before_text)
            before_start = int(before[19])
            before_pgid = int(before[2])
        except (IndexError, ValueError):
            record["unavailable_reason"] = "thread_stat_unreadable"
            record["missing"].append("stat")
            return record
        record["comm"] = comm
        record["start_ticks"] = before_start

        schedstat, schedstat_missing = self._read_schedstat(pid, tid, schedstats_raw)
        sched, sched_missing = self._read_sched(pid, tid)
        proc_status, status_missing = self._read_proc_status(pid, tid)

        after_text = self.read_text(str(pid), "task", str(tid), "stat")
        try:
            _, after = _split_stat(after_text) if after_text else (None, None)
            after_start, after_pgid = int(after[19]), int(after[2])
        except (IndexError, ValueError, TypeError):
            after_start = after_pgid = None
        if (after_start, after_pgid) != (before_start, before_pgid):
            # Identity is not stable: every metric read for this thread is
            # untrusted, so it is discarded rather than reported with the
            # earlier values.
            record["unavailable_reason"] = "thread_identity_changed"
            record["missing"] = ["thread_identity_changed"]
            return record

        missing = list(schedstat_missing) + list(sched_missing) + list(status_missing)
        try:
            stat = {"state": after[0], "pgid": after_pgid,
                    "priority": int(after[15]), "nice": int(after[16]),
                    "rt_priority": None, "policy": None,
                    "utime_ticks": int(after[11]), "stime_ticks": int(after[12])}
        except (IndexError, ValueError):
            stat = None
            missing.append("stat_fields")
        else:
            if len(after) > STAT_POLICY_INDEX:
                try:
                    stat["policy"] = int(after[STAT_POLICY_INDEX])
                except ValueError:
                    missing.append("stat.policy")
                try:
                    stat["rt_priority"] = int(after[STAT_RT_PRIORITY_INDEX])
                except ValueError:
                    missing.append("stat.rt_priority")
            else:
                missing += ["stat.policy", "stat.rt_priority"]

        record.update({"status": "captured", "read_consistent": True,
                       "stat": stat, "schedstat": schedstat, "sched": sched,
                       "proc_status": proc_status, "missing": missing})
        return record


class OwnedSchedulingCapture:
    def __init__(self, children, output, *, phase="unspecified",
                 proc_root=Path("/proc"), reader=None, clock_ticks=None,
                 now=_system_now):
        if reader is None and sys.platform != "linux" and str(Path(proc_root)) == "/proc":
            raise OSError("capture requires a Linux /proc; pass --proc-root in tests")
        if not isinstance(phase, str) or not phase.strip():
            raise ValueError("phase must be a non-empty string")
        self.children = Path(children)
        self.output = Path(output)
        self.phase = phase.strip()
        self.proc_root = Path(proc_root)
        self.reader = reader if reader is not None else ProcReader(self.proc_root)
        self.clock_ticks = clock_ticks if clock_ticks is not None else _default_clock_ticks()
        self.now = now
        self.schedstats_raw = None

    def _parse_children(self):
        try:
            raw = self.children.read_bytes()
        except OSError as error:
            raise ValueError(f"cannot read children file: {error!r}")
        # Hash the raw bytes so CRLF is not normalised before hashing.
        self.children_sha256 = hashlib.sha256(raw).hexdigest()
        try:
            children = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"children file is not UTF-8 JSON: {error!r}")
        if not isinstance(children, dict) or not children:
            raise ValueError("children file must be a non-empty object")
        expected = {}
        for role, entry in children.items():
            if not isinstance(role, str) or not role:
                raise ValueError(f"invalid child role: {role!r}")
            if not isinstance(entry, dict) or not isinstance(entry.get("identity"), dict):
                raise ValueError(f"{role}: missing identity object")
            identity = entry["identity"]
            expected[role] = {
                "pid": _require_int(identity.get("pid"), f"{role}.pid", 1, MAX_PID),
                "pgid": _require_int(identity.get("pgid"), f"{role}.pgid", 1, MAX_PID),
                "start_ticks": _require_int(identity.get("start_ticks"),
                                            f"{role}.start_ticks", 0, MAX_START_TICKS),
            }
        return children, expected

    def _host(self):
        def raw(*parts):
            return self.reader.read_text(*parts)

        boot_id = raw("sys", "kernel", "random", "boot_id")
        boot_id = boot_id.strip() if boot_id is not None else None
        uptime_text = raw("uptime")
        uptime_seconds = None
        if uptime_text:
            try:
                uptime_seconds = float(uptime_text.split()[0])
            except (IndexError, ValueError):
                uptime_seconds = None
        def knob(*parts):
            value = raw(*parts)
            return value.strip() if value is not None else None

        return {
            "boot_id": boot_id,
            "uptime_seconds": uptime_seconds,
            "clock_ticks_per_second": self.clock_ticks,
            "sched_rt_runtime_us": knob("sys", "kernel", "sched_rt_runtime_us"),
            "sched_rt_period_us": knob("sys", "kernel", "sched_rt_period_us"),
            "sched_schedstats": knob("sys", "kernel", "sched_schedstats"),
        }

    @staticmethod
    def _identity_problem(expected, actual, phase):
        if actual is None:
            return f"vanished_{phase}"
        if actual.get("state") in ("Z", "X", "x"):
            return f"exited_{phase}"
        if (actual.get("pid") != expected["pid"]
                or actual.get("pgid") != expected["pgid"]
                or actual.get("start_ticks") != expected["start_ticks"]):
            return f"identity_mismatch_{phase}"
        return None

    def _unavailable(self, expected, reason, discarded=0, before=None, after=None):
        entry = {"status": "unavailable", "unavailable_reason": reason,
                 "expected": dict(expected), "threads": [],
                 "thread_rows_discarded": discarded}
        if before is not None:
            entry["identity_before"] = before
        if after is not None:
            entry["identity_after"] = after
        return entry

    def _capture_proc(self, expected):
        pid = expected["pid"]
        started_ns = self.now()["monotonic_ns"]
        before = self.reader.identity(pid)
        problem = self._identity_problem(expected, before, "before_read")
        if problem:
            return self._unavailable(expected, problem, before=before)
        tids = self.reader.list_threads(pid)
        if tids is None:
            return self._unavailable(expected, "thread_inventory_unreadable",
                                     before=before)
        threads = [self.reader.read_thread(pid, tid, self.schedstats_raw)
                   for tid in tids]
        after = self.reader.identity(pid)
        problem = self._identity_problem(expected, after, "after_read")
        if problem:
            return self._unavailable(expected, problem, discarded=len(threads),
                                     before=before, after=after)
        unavailable = [row for row in threads if row["status"] != "captured"]
        status = "partial" if unavailable else "captured"
        entry = {
            "status": status,
            "expected": dict(expected),
            "identity_before": before,
            "identity_after": after,
            "captured_monotonic_ns": started_ns,
            "read_duration_ns": self.now()["monotonic_ns"] - started_ns,
            "thread_count": len(threads),
            "threads_captured": len(threads) - len(unavailable),
            "threads_unavailable": len(unavailable),
            "threads": threads,
        }
        if status == "partial":
            entry["partial_reason"] = "thread_rows_unavailable"
        return entry

    def capture(self):
        children, expected = self._parse_children()
        host = self._host()
        self.schedstats_raw = host["sched_schedstats"]
        procs = {role: self._capture_proc(entry)
                 for role, entry in expected.items()}
        counts = {"captured": 0, "partial": 0, "unavailable": 0}
        for proc in procs.values():
            counts[proc["status"]] += 1
        result = {
            "schema": SCHEMA,
            "phase": self.phase,
            "scope": SCOPE,
            "children": {"path": str(self.children),
                         "sha256": self.children_sha256,
                         "roles": len(children)},
            "output": str(self.output),
            "captured": self.now(),
            "host": host,
            "procs": procs,
            "summary": {"requested": len(expected), **counts},
            "performance_verdict": "not_evaluated",
            "sampler_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        }
        self.output.parent.mkdir(parents=True, exist_ok=True)
        with self.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False, sort_keys=True)
            stream.write("\n")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--children", type=Path, required=True,
                        help="children-start.json recording owned identities")
    parser.add_argument("--output", type=Path, required=True,
                        help="new JSON file; refuses to overwrite")
    parser.add_argument("--phase", default="unspecified",
                        help="label for this capture (e.g. before/after)")
    parser.add_argument("--proc-root", type=Path, default=Path("/proc"),
                        help=argparse.SUPPRESS)
    args = parser.parse_args()
    capture = OwnedSchedulingCapture(args.children, args.output,
                                     phase=args.phase, proc_root=args.proc_root)
    result = capture.capture()
    print(json.dumps({"output": result["output"], "phase": result["phase"],
                      **result["summary"],
                      "performance_verdict": result["performance_verdict"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
