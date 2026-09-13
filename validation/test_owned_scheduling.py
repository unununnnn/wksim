"""Pure tests for the read-only owned-scheduling snapshot tool.

These tests use a temporary /proc-shaped directory and an injected clock, so
they exercise only the tool's parsing, identity re-verification and
exclusive-output logic. They are NOT native evidence: no real process is
sampled and no performance conclusion may be drawn from them.
"""
import hashlib
import json
from pathlib import Path

import pytest

from tools.capture_owned_scheduling import (
    OwnedSchedulingCapture,
    ProcReader,
    _split_stat,
)


class FakeClock:
    def __init__(self):
        self.ticks = 0

    def __call__(self):
        self.ticks += 1
        return {"wall_utc": "2026-09-13T00:00:00+00:00",
                "monotonic_ns": self.ticks * 1_000_000,
                "boottime_ns": None}


def stat_line(pid, comm, state, pgid, priority, nice, num_threads, start_ticks,
              utime, stime, rt_priority=0, policy=0, full=True):
    # After ')' the fields are indexed from 0: state(0), pgrp(2), utime(11),
    # stime(12), priority(15), nice(16), num_threads(17), starttime(19),
    # rt_priority(37, stat field 40), policy(38, stat field 41).
    fields = [state, 1, pgid, pgid, 0, 0, 4194304, 0, 0, 0, 0,
              utime, stime, 0, 0, priority, nice, num_threads, 0, start_ticks]
    if full:
        fields += [0] * 17
        fields.append(rt_priority)
        fields.append(policy)
    return f"{pid} ({comm}) " + " ".join(str(value) for value in fields) + "\n"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_bytes(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def build_proc_tree(tmp_path, procs, *, host=True, schedstats="1"):
    proc = tmp_path / "proc"
    (proc / "task").mkdir(parents=True, exist_ok=True)
    if host:
        write(proc / "sys/kernel/random/boot_id", "boot-abc\n")
        write(proc / "uptime", "42.5 100.0\n")
        write(proc / "sys/kernel/sched_rt_runtime_us", "950000\n")
        write(proc / "sys/kernel/sched_rt_period_us", "1000000\n")
        write(proc / "sys/kernel/sched_schedstats", schedstats + "\n")
    for spec in procs:
        pid = spec["pid"]
        directory = proc / str(pid)
        (directory / "task").mkdir(parents=True, exist_ok=True)
        threads = spec.get("threads", [])
        write(directory / "stat", stat_line(
            pid, spec.get("comm", "worker"), spec.get("state", "R"),
            spec["pgid"], spec.get("priority", -10), spec.get("nice", -10),
            spec.get("num_threads", max(1, len(threads))), spec["start_ticks"],
            spec.get("utime", 1), spec.get("stime", 2),
            spec.get("rt_priority", 0), spec.get("policy", 0),
            spec.get("full", True)))
        write(directory / "status",
              f"Name:\t{spec.get('comm', 'worker')}\nTgid:\t{pid}\nPid:\t{pid}\n"
              "Cpus_allowed_list:\t0-7\nvoluntary_ctxt_switches:\t5\n"
              "nonvoluntary_ctxt_switches:\t1\n")
        for thread in threads:
            tid = thread["tid"]
            thread_dir = directory / "task" / str(tid)
            write(thread_dir / "stat", stat_line(
                tid, thread.get("comm", "worker"), thread.get("state", "S"),
                spec["pgid"], thread.get("priority", -10), thread.get("nice", -10),
                1, thread.get("start_ticks", spec["start_ticks"]),
                thread.get("utime", 10), thread.get("stime", 20),
                thread.get("rt_priority", 0), thread.get("policy", 0),
                thread.get("full", True)))
            if thread.get("status", True):
                write(thread_dir / "status",
                      f"Cpus_allowed_list:\t{thread.get('cpus', '0-7')}\n"
                      "voluntary_ctxt_switches:\t3\n"
                      "nonvoluntary_ctxt_switches:\t0\n")
            schedstat = thread.get("schedstat", (100, 200, 3))
            if schedstat is not None:
                run, runqueue, slices = schedstat
                write(thread_dir / "schedstat", f"{run} {runqueue} {slices}\n")
            sched = thread.get("sched", "policy : 1\nprio : 59\n")
            if sched is not None:
                write(thread_dir / "sched", sched)
    return proc


def make_children(tmp_path, entries, *, crlf=False):
    text = json.dumps(entries, indent=2)
    path = tmp_path / "children-start.json"
    if crlf:
        write_bytes(path, text.replace("\n", "\r\n").encode("utf-8"))
    else:
        write(path, text)
    return path


def capture(proc, children_path, tmp_path, output="snapshot.json", **kwargs):
    api = OwnedSchedulingCapture(
        children_path, tmp_path / output, proc_root=proc, clock_ticks=100,
        now=FakeClock(), **kwargs)
    return api.capture()


def two_role_children(tmp_path, **kwargs):
    return make_children(tmp_path, {
        "worker-a": {"identity": {"pid": 100, "pgid": 100, "start_ticks": 500,
                                  "argv": ["/usr/bin/python3", "-m", "worker"]}},
        "fc": {"identity": {"pid": 200, "pgid": 200, "start_ticks": 501,
                            "argv": ["/opt/fc"]}},
    }, **kwargs)


def two_role_tree(tmp_path, **kwargs):
    return build_proc_tree(tmp_path, [
        {"pid": 100, "pgid": 100, "start_ticks": 500, "comm": "worker",
         "threads": [
             {"tid": 100, "comm": "worker", "start_ticks": 500, "state": "R",
              "schedstat": (111, 222, 3), "cpus": "0-3", "rt_priority": 40,
              "policy": 1, "sched": "policy : 1\nprio : 59\n"},
             {"tid": 101, "comm": "wk-thread", "start_ticks": 500, "state": "S",
              "schedstat": (7, 8, 1), "cpus": "2", "rt_priority": 0,
              "policy": 0, "sched": "policy : 0\nprio : 120\n"},
         ]},
        {"pid": 200, "pgid": 200, "start_ticks": 501, "comm": "fc",
         "threads": [{"tid": 200, "comm": "fc", "start_ticks": 501,
                      "schedstat": (1, 2, 1)}]},
    ], **kwargs)


def test_normal_capture_records_threads_and_host(tmp_path):
    proc = two_role_tree(tmp_path)
    result = capture(proc, two_role_children(tmp_path), tmp_path, phase="before")

    assert result["schema"] == "wksim.owned-scheduling-snapshot.v1"
    assert result["phase"] == "before"
    assert result["summary"] == {"requested": 2, "captured": 2, "partial": 0,
                                 "unavailable": 0}
    assert result["performance_verdict"] == "not_evaluated"

    worker = result["procs"]["worker-a"]
    assert worker["status"] == "captured"
    assert worker["expected"] == {"pid": 100, "pgid": 100, "start_ticks": 500}
    assert worker["identity_before"]["start_ticks"] == 500
    assert worker["thread_count"] == 2
    assert worker["threads_captured"] == 2
    assert worker["threads_unavailable"] == 0
    threads = {row["tid"]: row for row in worker["threads"]}

    fifo = threads[100]
    assert fifo["status"] == "captured"
    assert fifo["stat"]["state"] == "R"
    assert fifo["stat"]["rt_priority"] == 40
    assert fifo["stat"]["policy"] == 1
    assert fifo["sched"] == {"kernel_prio": 59}
    assert "priority" not in fifo["sched"]
    assert fifo["schedstat"]["run_ns"] == 111
    assert fifo["schedstat"]["runqueue_ns"] == 222
    assert fifo["schedstat"]["timeslices"] == 3
    assert fifo["schedstat"]["raw"] == {"run_ns": 111, "runqueue_ns": 222,
                                        "timeslices": 3}
    assert fifo["schedstat"]["runqueue_counters_valid"] is True
    assert fifo["schedstat"]["runqueue_invalid_reason"] is None
    assert fifo["proc_status"]["cpus_allowed_list"] == "0-3"
    assert fifo["missing"] == []
    assert fifo["read_consistent"] is True

    cfs = threads[101]
    assert cfs["sched"] == {"kernel_prio": 120}
    assert cfs["stat"]["rt_priority"] == 0
    assert cfs["stat"]["policy"] == 0

    assert result["host"]["boot_id"] == "boot-abc"
    assert result["host"]["uptime_seconds"] == 42.5
    assert result["host"]["clock_ticks_per_second"] == 100
    assert result["host"]["sched_rt_runtime_us"] == "950000"
    assert result["host"]["sched_rt_period_us"] == "1000000"
    assert result["host"]["sched_schedstats"] == "1"


def test_disappeared_process_is_unavailable_not_zero(tmp_path):
    proc = two_role_tree(tmp_path)
    children = make_children(tmp_path, {
        "gone": {"identity": {"pid": 999, "pgid": 999, "start_ticks": 1}}})
    result = capture(proc, children, tmp_path)

    entry = result["procs"]["gone"]
    assert entry["status"] == "unavailable"
    assert entry["unavailable_reason"] == "vanished_before_read"
    assert entry["threads"] == []
    assert result["summary"] == {"requested": 1, "captured": 0, "partial": 0,
                                 "unavailable": 1}
    assert "identity_before" not in entry


def test_pid_reuse_start_ticks_mismatch_is_refused(tmp_path):
    proc = build_proc_tree(tmp_path, [
        {"pid": 100, "pgid": 100, "start_ticks": 9999, "state": "R",
         "threads": [{"tid": 100, "start_ticks": 9999}]}])
    children = make_children(tmp_path, {
        "worker-a": {"identity": {"pid": 100, "pgid": 100, "start_ticks": 500}}})
    result = capture(proc, children, tmp_path)

    entry = result["procs"]["worker-a"]
    assert entry["status"] == "unavailable"
    assert entry["unavailable_reason"] == "identity_mismatch_before_read"
    assert entry["identity_before"]["start_ticks"] == 9999
    assert entry["threads"] == []


@pytest.mark.parametrize("override", [
    {"pid": 0}, {"pid": -1}, {"pid": True}, {"pid": "100"},
    {"pid": 1.5}, {"pid": 2 ** 40}, {"pid": None},
    {"pid": 100, "pgid": 0}, {"pid": 100, "start_ticks": -1},
])
def test_out_of_bounds_identity_is_rejected(tmp_path, override):
    proc = two_role_tree(tmp_path)
    identity = {"pid": 100, "pgid": 100, "start_ticks": 500}
    identity.update(override)
    children = make_children(tmp_path, {"worker-a": {"identity": identity}})

    with pytest.raises(ValueError):
        capture(proc, children, tmp_path)
    assert not (tmp_path / "snapshot.json").exists()


def test_malformed_children_identity_is_rejected(tmp_path):
    proc = two_role_tree(tmp_path)
    children = make_children(tmp_path, {"worker-a": {"argv": ["x"]}})
    with pytest.raises(ValueError):
        capture(proc, children, tmp_path)


@pytest.mark.parametrize("parts", [
    ("..", "etc", "passwd"), ("a/b",), ("a\\b",), ("",), ("/",), ("\x00",),
])
def test_proc_reader_refuses_unsafe_path_components(tmp_path, parts):
    with pytest.raises(ValueError):
        ProcReader(tmp_path).read_text(*parts)


def test_crlf_children_file_hashes_raw_bytes(tmp_path):
    proc = two_role_tree(tmp_path)
    children = two_role_children(tmp_path, crlf=True)
    raw = children.read_bytes()
    assert b"\r\n" in raw
    lf_hash = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()

    result = capture(proc, children, tmp_path)

    assert result["children"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["children"]["sha256"] != lf_hash
    assert result["children"]["roles"] == 2
    assert result["procs"]["worker-a"]["status"] == "captured"


def test_missing_fields_are_null_never_zero(tmp_path):
    proc = build_proc_tree(tmp_path, [
        {"pid": 300, "pgid": 300, "start_ticks": 700, "comm": "bare",
         "threads": [{"tid": 300, "start_ticks": 700, "status": False,
                      "schedstat": None, "sched": None}]}])
    children = make_children(tmp_path, {
        "bare": {"identity": {"pid": 300, "pgid": 300, "start_ticks": 700}}})
    result = capture(proc, children, tmp_path)

    thread = result["procs"]["bare"]["threads"][0]
    assert thread["status"] == "captured"
    assert thread["stat"] is not None
    assert thread["schedstat"] is None
    assert thread["sched"] is None
    assert thread["proc_status"] is None
    assert thread["schedstat"] != 0
    assert {"schedstat", "sched", "status"} <= set(thread["missing"])
    assert thread["read_consistent"] is True


def test_missing_host_knobs_are_null(tmp_path):
    proc = build_proc_tree(tmp_path, [
        {"pid": 300, "pgid": 300, "start_ticks": 700,
         "threads": [{"tid": 300, "start_ticks": 700,
                      "schedstat": (11, 22, 1)}]}], host=False)
    children = make_children(tmp_path, {
        "bare": {"identity": {"pid": 300, "pgid": 300, "start_ticks": 700}}})
    result = capture(proc, children, tmp_path)

    assert result["host"]["boot_id"] is None
    assert result["host"]["uptime_seconds"] is None
    assert result["host"]["sched_rt_runtime_us"] is None
    assert result["host"]["sched_schedstats"] is None
    schedstat = result["procs"]["bare"]["threads"][0]["schedstat"]
    assert schedstat["run_ns"] == 11
    assert schedstat["runqueue_ns"] is None
    assert schedstat["runqueue_counters_valid"] is False
    assert schedstat["runqueue_invalid_reason"] == "sched_schedstats_unreadable"


def test_schedstats_disabled_keeps_exec_and_nulls_runqueue(tmp_path):
    proc = build_proc_tree(tmp_path, [
        {"pid": 300, "pgid": 300, "start_ticks": 700,
         "threads": [{"tid": 300, "start_ticks": 700,
                      "schedstat": (111, 222, 9)}]}], schedstats="0")
    children = make_children(tmp_path, {
        "bare": {"identity": {"pid": 300, "pgid": 300, "start_ticks": 700}}})
    result = capture(proc, children, tmp_path)

    schedstat = result["procs"]["bare"]["threads"][0]["schedstat"]
    assert schedstat["run_ns"] == 111          # sum_exec_runtime stays valid
    assert schedstat["runqueue_ns"] is None
    assert schedstat["runqueue_ns"] != 0
    assert schedstat["timeslices"] is None
    assert schedstat["raw"] == {"run_ns": 111, "runqueue_ns": 222,
                                "timeslices": 9}
    assert schedstat["runqueue_counters_valid"] is False
    assert schedstat["runqueue_invalid_reason"] == "sched_schedstats_disabled"
    assert "schedstat.runqueue_ns" in result["procs"]["bare"]["threads"][0]["missing"]


def test_kernel_prio_is_not_rt_priority(tmp_path):
    proc = build_proc_tree(tmp_path, [
        {"pid": 300, "pgid": 300, "start_ticks": 700,
         "threads": [{"tid": 300, "start_ticks": 700, "rt_priority": 40,
                      "policy": 1, "sched": "policy : 1\nprio : 59\n"}]}])
    children = make_children(tmp_path, {
        "bare": {"identity": {"pid": 300, "pgid": 300, "start_ticks": 700}}})
    result = capture(proc, children, tmp_path)

    thread = result["procs"]["bare"]["threads"][0]
    assert thread["sched"] == {"kernel_prio": 59}
    assert "priority" not in thread["sched"]
    assert thread["stat"]["rt_priority"] == 40
    assert thread["stat"]["policy"] == 1


def test_short_stat_leaves_rt_priority_and_policy_null(tmp_path):
    proc = build_proc_tree(tmp_path, [
        {"pid": 300, "pgid": 300, "start_ticks": 700,
         "threads": [{"tid": 300, "start_ticks": 700, "full": False}]}])
    children = make_children(tmp_path, {
        "bare": {"identity": {"pid": 300, "pgid": 300, "start_ticks": 700}}})
    result = capture(proc, children, tmp_path)

    thread = result["procs"]["bare"]["threads"][0]
    assert thread["stat"]["rt_priority"] is None
    assert thread["stat"]["policy"] is None
    assert thread["stat"]["rt_priority"] != 0
    assert {"stat.policy", "stat.rt_priority"} <= set(thread["missing"])


def test_output_is_exclusive_and_never_overwrites(tmp_path):
    proc = two_role_tree(tmp_path)
    children = two_role_children(tmp_path)
    output = tmp_path / "snapshot.json"

    capture(proc, children, tmp_path)
    first_bytes = output.read_bytes()
    with pytest.raises(FileExistsError):
        capture(proc, children, tmp_path)
    assert output.read_bytes() == first_bytes


class FlippingReader(ProcReader):
    """Return a changed identity after the first read, simulating reuse."""

    def __init__(self, root, flip_after):
        super().__init__(root)
        self.calls = 0
        self.flip_after = flip_after

    def identity(self, pid):
        self.calls += 1
        row = super().identity(pid)
        if row is not None and self.calls > self.flip_after:
            row = dict(row, start_ticks=row["start_ticks"] + 1)
        return row


def test_identity_change_after_read_discards_thread_rows(tmp_path):
    proc = build_proc_tree(tmp_path, [
        {"pid": 100, "pgid": 100, "start_ticks": 500,
         "threads": [{"tid": 100, "start_ticks": 500},
                     {"tid": 101, "start_ticks": 500}]}])
    children = make_children(tmp_path, {
        "worker-a": {"identity": {"pid": 100, "pgid": 100, "start_ticks": 500}}})
    api = OwnedSchedulingCapture(
        children, tmp_path / "snapshot.json", proc_root=proc, clock_ticks=100,
        now=FakeClock(), reader=FlippingReader(proc, flip_after=1))
    result = api.capture()

    entry = result["procs"]["worker-a"]
    assert entry["status"] == "unavailable"
    assert entry["unavailable_reason"] == "identity_mismatch_after_read"
    assert entry["threads"] == []
    assert entry["thread_rows_discarded"] == 2
    assert result["performance_verdict"] == "not_evaluated"


class ThreadFlipReader(ProcReader):
    """Change one thread's start_ticks between its before/after stat reads."""

    def __init__(self, root, tid):
        super().__init__(root)
        self.tid = str(tid)
        self.stat_reads = 0

    def read_text(self, *parts):
        text = super().read_text(*parts)
        if (len(parts) == 4 and parts[1] == "task" and parts[2] == self.tid
                and parts[3] == "stat" and text is not None):
            self.stat_reads += 1
            if self.stat_reads == 2:
                comm, fields = _split_stat(text)
                fields = list(fields)
                fields[19] = str(int(fields[19]) + 7)
                text = f"{parts[0]} ({comm}) " + " ".join(fields) + "\n"
        return text


def test_thread_identity_change_discards_untrusted_metrics(tmp_path):
    proc = build_proc_tree(tmp_path, [
        {"pid": 100, "pgid": 100, "start_ticks": 500,
         "threads": [{"tid": 100, "start_ticks": 500, "rt_priority": 40,
                      "policy": 1, "schedstat": (111, 222, 3),
                      "sched": "policy : 1\nprio : 59\n"},
                     {"tid": 101, "start_ticks": 500}]}])
    children = make_children(tmp_path, {
        "worker-a": {"identity": {"pid": 100, "pgid": 100, "start_ticks": 500}}})
    api = OwnedSchedulingCapture(
        children, tmp_path / "snapshot.json", proc_root=proc, clock_ticks=100,
        now=FakeClock(), reader=ThreadFlipReader(proc, tid=100))
    result = api.capture()

    entry = result["procs"]["worker-a"]
    assert entry["status"] == "partial"
    assert entry["partial_reason"] == "thread_rows_unavailable"
    assert entry["threads_captured"] == 1
    assert entry["threads_unavailable"] == 1
    rows = {row["tid"]: row for row in entry["threads"]}

    flipped = rows[100]
    assert flipped["status"] == "unavailable"
    assert flipped["unavailable_reason"] == "thread_identity_changed"
    assert flipped["read_consistent"] is False
    # Untrusted metrics must not survive in any usable/zero form.
    for key in ("stat", "schedstat", "sched", "proc_status"):
        assert flipped[key] is None
    assert flipped["missing"] == ["thread_identity_changed"]

    stable = rows[101]
    assert stable["status"] == "captured"
    assert stable["stat"] is not None
    assert result["summary"] == {"requested": 1, "captured": 0, "partial": 1,
                                 "unavailable": 0}


class ChurnReader(ProcReader):
    """Report a thread that vanishes before it can be read."""

    def list_threads(self, pid):
        return super().list_threads(pid) + [424242]


def test_thread_churn_is_partial_not_pid_reuse(tmp_path):
    proc = build_proc_tree(tmp_path, [
        {"pid": 100, "pgid": 100, "start_ticks": 500,
         "threads": [{"tid": 100, "start_ticks": 500},
                     {"tid": 101, "start_ticks": 500}]}])
    children = make_children(tmp_path, {
        "worker-a": {"identity": {"pid": 100, "pgid": 100, "start_ticks": 500}}})
    api = OwnedSchedulingCapture(
        children, tmp_path / "snapshot.json", proc_root=proc, clock_ticks=100,
        now=FakeClock(), reader=ChurnReader(proc))
    result = api.capture()

    entry = result["procs"]["worker-a"]
    assert entry["status"] == "partial"
    assert "unavailable_reason" not in entry
    rows = {row["tid"]: row for row in entry["threads"]}
    assert rows[424242]["status"] == "unavailable"
    assert rows[424242]["unavailable_reason"] == "thread_stat_unreadable"
    assert rows[100]["status"] == "captured"
    assert rows[101]["status"] == "captured"


class CounterGrowingReader(ProcReader):
    """Grow ordinary counters/nice fields; identity itself is unchanged."""

    def __init__(self, root):
        super().__init__(root)
        self.calls = 0

    def identity(self, pid):
        self.calls += 1
        row = super().identity(pid)
        if row is not None and self.calls > 1:
            row = dict(row, num_threads=row["num_threads"] + 5,
                       comm=row["comm"] + "-grown")
        return row


def test_counter_growth_is_not_pid_reuse(tmp_path):
    proc = build_proc_tree(tmp_path, [
        {"pid": 100, "pgid": 100, "start_ticks": 500,
         "threads": [{"tid": 100, "start_ticks": 500}]}])
    children = make_children(tmp_path, {
        "worker-a": {"identity": {"pid": 100, "pgid": 100, "start_ticks": 500}}})
    api = OwnedSchedulingCapture(
        children, tmp_path / "snapshot.json", proc_root=proc, clock_ticks=100,
        now=FakeClock(), reader=CounterGrowingReader(proc))
    result = api.capture()

    entry = result["procs"]["worker-a"]
    assert entry["status"] == "captured"
    assert entry["identity_after"]["start_ticks"] == 500
    assert (entry["identity_after"]["num_threads"]
            != entry["identity_before"]["num_threads"])
    assert entry["identity_after"]["comm"].endswith("-grown")


def test_output_records_children_hash(tmp_path):
    proc = two_role_tree(tmp_path)
    children = two_role_children(tmp_path)
    result = capture(proc, children, tmp_path)
    assert len(result["children"]["sha256"]) == 64
    assert result["children"]["roles"] == 2
    assert len(result["sampler_sha256"]) == 64
