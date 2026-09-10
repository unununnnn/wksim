"""External, bounded, read-only /proc thread sampler for one joint run.

Purpose: separate per-thread execution from runqueue waiting for the run's
supervisor, the arducopter FC and the model processes, so an AP-side wait
(e.g. the 9.584750 ms peak seen in run 15) can be decomposed into compute,
runnable-queue delay and other blocking — without claiming an AP root cause
up front. schedstat runqueue time is only time spent runnable-but-waiting; it
is NOT all off-CPU time, and this sampler never conflates them. The original
/proc/sys/kernel/sched_schedstats value is recorded in the header; when
schedstats collection is disabled, zero runqueue values are reported as
unavailable, never as "no waiting".

Discipline (same verification style as tools/sample_joint_startup.py):
- targets come only from the run's own children.json identities plus the
  run's status.json supervisor identity; the status epoch/run_id must match
  the epoch directory name and config.json run_id; at startup the live
  /proc identity must equal the recorded pid/pgid/start_ticks AND argv
  exactly (recorded identity.argv is authoritative);
- every batch re-verifies each PID's start_ticks/pgid before AND after
  reading its threads; a change retires the PID and drops its rows from that
  batch; a reused PID is never followed;
- per-TID start_ticks are kept in every row, and a TID's stat is re-read
  after schedstat: inconsistent reads are dropped, not sampled;
- read-only: no affinity/priority changes, no attach, no signals, and the
  system sched_schedstats switch is never touched;
- hard bounds: integer rate 1..1000 Hz, finite duration <= 40 s, sample cap
  and thread-row cap;
- output is a fresh 'x'-mode directory with samples.jsonl + result.json;
  every failure is written to header/close records; originals never deleted.

Usage (on the WSL host, while the run is live):
  python3 -B tools/sample_joint_threads.py --run <run-or-epoch-dir> --output <new-dir>
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Simulator.wksim_runtime.evidence import json_identity

DEFAULT_TARGETS = ("supervisor", "arducopter-fc", "arducopter-model", "px4-model")
MAX_DURATION_S = 40.0
MAX_RATE_HZ = 1000
MAX_SAMPLES = 400000
MAX_THREAD_ROWS = 4_000_000

SCHEDSTAT_SWITCH = Path("/proc/sys/kernel/sched_schedstats")


def _stat_fields(root, pid, tid=None):
    path = root / str(pid) / ("stat" if tid is None else f"task/{tid}/stat")
    fields = path.read_text().rsplit(")", 1)[1].split()
    return {"state": fields[0], "pgid": int(fields[2]), "utime_ticks": int(fields[11]),
            "stime_ticks": int(fields[12]), "start_ticks": int(fields[19])}


def _schedstat(root, pid, tid):
    fields = (root / str(pid) / f"task/{tid}/schedstat").read_text().split()
    return {"run_ns": int(fields[0]), "runqueue_ns": int(fields[1]),
            "timeslices": int(fields[2])}


class ThreadSampler:
    def __init__(self, run, output, *, rate_hz=100, duration_s=MAX_DURATION_S,
                 targets=DEFAULT_TARGETS, proc_root=Path("/proc"), identity=json_identity,
                 schedstat_switch=SCHEDSTAT_SWITCH):
        if sys.platform != "linux" and str(proc_root) == "/proc":
            raise OSError("ThreadSampler requires Linux /proc")
        if type(rate_hz) is not int or not 1 <= rate_hz <= MAX_RATE_HZ:
            raise ValueError("rate_hz must be an integer 1..1000")
        if (type(duration_s) not in (int, float) or isinstance(duration_s, bool)
                or not math.isfinite(duration_s) or not 0 < duration_s <= MAX_DURATION_S):
            raise ValueError(f"duration_s must be finite within (0, {MAX_DURATION_S}]")
        self.run = Path(run).resolve()
        self.output = Path(output)
        self.rate_hz = rate_hz
        self.duration_s = float(duration_s)
        self.proc_root = Path(proc_root)
        self.identity = identity
        self.schedstat_switch = Path(schedstat_switch)
        for name in targets:
            if not isinstance(name, str) or not name:
                raise ValueError("target names must be non-empty strings")
        self.target_names = list(targets)
        if not self.target_names or len(set(self.target_names)) != len(self.target_names):
            raise ValueError('targets must be nonempty and unique')

    def _locate(self):
        """Accept a run root or its single epoch directory; return (root, epoch)."""
        run = self.run
        if (run / "children.json").is_file():
            if (run.parent.parent / "status.json").is_file() and (run.parent.parent / "config.json").is_file():
                return run.parent.parent, run
            raise ValueError("epoch directory requires status.json and config.json beside it")
        epochs = [p for p in (run / "epochs").iterdir() if p.is_dir()] if (run / "epochs").is_dir() else []
        if len(epochs) == 1 and (epochs[0] / "children.json").is_file():
            return run, epochs[0]
        raise ValueError("run directory must contain status.json plus one epoch's children.json")

    def _verify_run_identity(self, run_root, epoch_dir):
        status = json.loads((run_root / "status.json").read_text())
        config = json.loads((run_root / "config.json").read_text())
        if status.get("run_id") != config.get("run_id"):
            raise ValueError("status run_id differs from config")
        if status.get("epoch") != epoch_dir.name:
            raise ValueError("status epoch differs from the epoch directory")
        if epoch_dir.parent.parent.resolve() != run_root:
            raise ValueError("epoch directory is not inside the run root")
        return status, config

    def _verify_target(self, expected, name):
        """Exact identity: pid/pgid/start_ticks AND full argv equality."""
        actual = self.identity(expected["pid"])
        if actual is None:
            raise ValueError(f"target {name} exited before sampling")
        if any(actual[key] != expected[key] for key in ("pid", "pgid", "start_ticks")):
            raise ValueError(f"target {name} identity differs (pid reuse refused)")
        if actual.get("argv") != expected.get("argv"):
            raise ValueError(f"target {name} argv differs from the recorded identity")

    def _targets(self, epoch_dir):
        children = json.loads((epoch_dir / "children.json").read_text())
        targets = {}
        for name in self.target_names:
            if name == "supervisor":
                expected = json.loads((epoch_dir.parent.parent / "status.json")
                                      .read_text())["supervisor"]
            else:
                if name not in children:
                    raise ValueError(f"target {name} not in children.json")
                expected = children[name]["identity"]
            self._verify_target(expected, name)
            targets[name] = dict(expected)
        return targets

    def _read_thread(self, pid, tid):
        """stat -> schedstat -> stat again; inconsistent reads are dropped."""
        before = _stat_fields(self.proc_root, pid, tid)
        counters = _schedstat(self.proc_root, pid, tid)
        after = _stat_fields(self.proc_root, pid, tid)
        if any(before[key] != after[key] for key in ('start_ticks','pgid')):
            raise ValueError("thread identity changed during the read")
        return dict(tid=tid, pid=pid, start_ticks=before["start_ticks"],
                    state=after["state"], utime_ticks=after["utime_ticks"],
                    stime_ticks=after["stime_ticks"], **counters)

    def sample(self):
        self.output.mkdir(exist_ok=False)  # x semantics: never overwrite.
        result = {"schema": "wksim.joint-thread-sampler.v2",
                  "run_id": None, "epoch": None,
                  "rate_hz": self.rate_hz, "duration_s": self.duration_s,
                  "sampler_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "status": "failed",
                  "scope": "schedstat runqueue time is runnable-wait only, not all off-CPU",
                  "samples": 0, "thread_rows": 0, "maximum_batch_ns": 0}
        samples_path = self.output / "samples.jsonl"
        sampler_cpu_start = time.thread_time_ns()
        header_written = False
        with samples_path.open("x", encoding="utf-8") as stream:
            try:
                run_root, epoch_dir = self._locate()
                status, config = self._verify_run_identity(run_root, epoch_dir)
                result["run_id"] = status["run_id"]
                result["epoch"] = status["epoch"]
                try:
                    result['host_boot_id'] = (self.proc_root/'sys/kernel/random/boot_id').read_text().strip()
                except OSError:
                    result['host_boot_id'] = None
                result['clock_ticks_per_second'] = os.sysconf('SC_CLK_TCK') if hasattr(os,'sysconf') else None
                targets = self._targets(epoch_dir)
                result["targets"] = targets
                try:
                    result["sched_schedstats_original"] = self.schedstat_switch.read_text().strip()
                except OSError as error:
                    result["sched_schedstats_original"] = f"unreadable: {error!r}"
                result["runqueue_counters_valid"] = result["sched_schedstats_original"] == "1"
                stream.write(json.dumps({"kind": "header", **result,
                                         "started_monotonic_ns": time.monotonic_ns()},
                                        allow_nan=False) + "\n")
                header_written = True
                live = dict(targets)
                deadline = time.monotonic() + self.duration_s
                period = 1.0 / self.rate_hz
                while time.monotonic() < deadline and live:
                    batch = {"kind": "sample", "monotonic_ns": time.monotonic_ns(),
                             "run_id": result["run_id"], "epoch": result["epoch"],
                             "threads": []}
                    for name, expected in list(live.items()):
                        pid = expected["pid"]
                        try:
                            before = _stat_fields(self.proc_root, pid)
                            if before['state'] in ('Z','X','x'):
                                raise ValueError('process exited')
                            if (before["start_ticks"] != expected["start_ticks"]
                                    or before["pgid"] != expected["pgid"]):
                                raise ValueError("identity changed")
                            rows = []
                            for task in (self.proc_root / str(pid) / "task").iterdir():
                                if not task.name.isdecimal():
                                    continue
                                try:
                                    rows.append(self._read_thread(pid, int(task.name)))
                                except (OSError, ValueError, IndexError):
                                    continue  # Thread exited or raced; drop the row.
                            after = _stat_fields(self.proc_root, pid)
                            if after['state'] in ('Z','X','x'):
                                raise ValueError('process exited mid-batch')
                            if (after["start_ticks"] != expected["start_ticks"]
                                    or after["pgid"] != expected["pgid"]):
                                raise ValueError("identity changed mid-batch")
                        except (OSError, ValueError, IndexError) as error:
                            stream.write(json.dumps(
                                {"kind": "target_retired", "target": name,
                                 "reason": repr(error),
                                 "monotonic_ns": time.monotonic_ns()}) + "\n")
                            del live[name]
                            continue
                        for row in rows:
                            row["target"] = name
                        batch["threads"].extend(rows)
                    result["thread_rows"] += len(batch["threads"])
                    if result["thread_rows"] > MAX_THREAD_ROWS:
                        raise RuntimeError("thread row cap reached")
                    batch['read_completed_monotonic_ns'] = time.monotonic_ns()
                    batch['read_duration_ns'] = batch['read_completed_monotonic_ns']-batch['monotonic_ns']
                    result['maximum_batch_ns'] = max(result['maximum_batch_ns'],batch['read_duration_ns'])
                    stream.write(json.dumps(batch, allow_nan=False) + "\n")
                    result["samples"] += 1
                    if result["samples"] >= MAX_SAMPLES:
                        raise RuntimeError("sample cap reached")
                    time.sleep(max(0.0, period - (time.monotonic_ns()
                                                  - batch["monotonic_ns"]) / 1e9))
                result["status"] = "sampled"
                result["stop_reason"] = ("all targets retired" if not live
                                         else "duration reached")
            except BaseException as error:
                result["error"] = repr(error)
                if not header_written:
                    stream.write(json.dumps({'kind':'header',**result,
                        'started_monotonic_ns':time.monotonic_ns()},allow_nan=False)+'\n')
                stream.write(json.dumps({"kind": "error", "error": repr(error),
                                         "monotonic_ns": time.monotonic_ns()}) + "\n")
            result["sampler_thread_cpu_ns"] = time.thread_time_ns() - sampler_cpu_start
            stream.write(json.dumps({"kind": "close", "status": result["status"],
                                     "stop_reason": result.get("stop_reason"),
                                     "samples": result["samples"],
                                     "thread_rows": result["thread_rows"],
                                     "sampler_thread_cpu_ns": result["sampler_thread_cpu_ns"],
                                     "finished_monotonic_ns": time.monotonic_ns()},
                                    allow_nan=False) + "\n")
        result["samples_sha256"] = hashlib.sha256(samples_path.read_bytes()).hexdigest()
        with (self.output / "result.json").open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=1, allow_nan=False)
            stream.write("\n")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rate-hz", type=int, default=100)
    parser.add_argument("--duration-s", type=float, default=MAX_DURATION_S)
    parser.add_argument("--target", action="append", default=None,
                        help="target name; repeatable; default: supervisor + arducopter-fc + models")
    args = parser.parse_args()
    sampler = ThreadSampler(args.run, args.output, rate_hz=args.rate_hz,
                            duration_s=args.duration_s,
                            targets=args.target or list(DEFAULT_TARGETS))
    result = sampler.sample()
    print(json.dumps({k: result.get(k) for k in
                      ("status", "stop_reason", "samples", "error")}))
    return 0 if result["status"] == "sampled" else 1


if __name__ == "__main__":
    sys.exit(main())
