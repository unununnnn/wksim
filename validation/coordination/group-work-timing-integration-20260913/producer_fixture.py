"""Execute the patched JointPhysics orchestration methods against fakes.

The frozen joint.py source (SHA-256 pinned) is patched in memory by the
sibling ``prepare_group_work_timing_patch`` tool, then ONLY the three
orchestration methods (``advance`` / ``finish_inputs`` / ``_native_wait``)
are AST-extracted and exec'd with a whitelist of fake globals.  The original
module is never imported and its constructor never runs (it opens sockets);
no model library, physics algorithm, socket or subprocess is touched.
``rate_group_start`` / ``rate_group_end`` rows come from the REAL
``JointRate`` driven by a fake monotonic clock (pure Python, no ports).

``produce(census)`` runs one complete four-tick group (ticks 41..44, anchor
at 40) with a simulated 9 ms ArduPilot input wait on tick 43 so the group's
work exceeds the 8 ms period.  ``main`` writes both modes plus their
ordinary-event equivalence proof to a new JSON file (exclusive create).
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

import prepare_group_work_timing_patch as patch_tool  # noqa: E402

from Simulator.wksim_runtime.joint_rate import JointRate  # noqa: E402

EXPECTED_SOURCE_SHA256 = patch_tool.EXPECTED_INPUT_SHA256
EXTRACTED_METHODS = ("advance", "finish_inputs", "_native_wait")
# Global names the extracted methods may resolve; anything else is a NameError.
FAKE_GLOBALS = ("time", "receive_workers", "sensor_fields", "json")

WALL_QUANTUM_NS = 10_000        # each monotonic read costs 10us of fake wall
CPU_QUANTUM_NS = 4_000          # each thread-time read costs 4us of fake cpu
SLOW_TICK = 43
SLOW_WAIT_WALL_NS = 9_000_000   # tick-43 AP input wait -> group work > 8ms
FAST_WAIT_WALL_NS = 50_000
SLOW_WAIT_CPU_NS = 1_000_000
FAST_WAIT_CPU_NS = 20_000


class FakeTime:
    """Deterministic monotonic/thread clock; every read advances it."""

    def __init__(self):
        self.wall_ns = 1_000_000_000
        self.cpu_ns = 500_000_000

    def monotonic_ns(self):
        self.wall_ns += WALL_QUANTUM_NS
        return self.wall_ns

    def thread_time_ns(self):
        self.cpu_ns += CPU_QUANTUM_NS
        return self.cpu_ns

    def monotonic(self):
        return self.monotonic_ns() / 1e9

    def bump_wall(self, ns):
        self.wall_ns += ns

    def bump_cpu(self, ns):
        self.cpu_ns += ns


class FakeClock:
    def __init__(self, epoch):
        self.epoch = epoch
        self.tick = 40
        self.pending = None
        self.phase = "running"
        self.calls = []

    def begin_step(self):
        self.tick += 1
        self.calls.append(("begin_step", self.tick))
        return self.tick

    def commit(self, responses):
        self.calls.append(("commit", self.tick,
                           sorted(responses)))

    def acknowledge_ap(self, frame):
        self.calls.append(("acknowledge_ap", frame))

    def barrier(self, ap_frame, px4_time_us, synchronized):
        self.calls.append(("barrier", ap_frame, px4_time_us, synchronized))


class FakeSocket:
    """Records sends; performs no I/O of any kind."""

    def __init__(self):
        self.sent = []

    def sendto(self, packet, peer):
        self.sent.append((packet, peer))


class FakeMessage:
    def __init__(self, payload):
        self.payload = payload

    def get_msgbuf(self):
        return self.payload


class FakeProtocol:
    def __init__(self):
        self.encoded = []
        self.sent = []

    def hil_sensor_encode(self, timestamp_us, *fields):
        self.encoded.append((timestamp_us, len(fields)))
        return FakeMessage(b"\xfdhil-sensor" + bytes([len(fields)]))

    def send(self, message):
        self.sent.append(message.payload)


def extract_orchestration(patched_bytes):
    """Compile only the three orchestration methods into a bare namespace."""
    tree = ast.parse(patched_bytes, filename="joint.py")
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "JointPhysics":
            methods = {item.name: item for item in node.body
                       if isinstance(item, ast.FunctionDef)}
            break
    else:
        raise ValueError("JointPhysics class not found")
    missing = set(EXTRACTED_METHODS) - set(methods)
    if missing:
        raise ValueError(f"missing methods: {sorted(missing)}")
    body = [methods[name] for name in EXTRACTED_METHODS]
    module = ast.Module(body=body, type_ignores=[])
    namespace = {"__builtins__": __builtins__}
    exec(compile(ast.fix_missing_locations(module), "joint.py", "exec"),
         namespace)
    return {name: namespace[name] for name in EXTRACTED_METHODS}


def produce(census, *, source_path=None):
    """Run one four-tick group; return events, rows and proof fields."""
    if type(census) is not bool:
        raise TypeError("census must be a plain bool")
    source_path = source_path or ROOT / "Simulator" / "wksim_core" / "joint.py"
    source = source_path.read_bytes()
    source_sha = hashlib.sha256(source).hexdigest()
    if source_sha != EXPECTED_SOURCE_SHA256:
        raise ValueError("source is not the frozen joint.py snapshot")
    methods = extract_orchestration(patch_tool.apply_patch(source))

    fake_time = FakeTime()
    epoch = "fixture-epoch-group-work-timing"
    clock = FakeClock(epoch)
    ap = FakeSocket()
    protocol = FakeProtocol()
    wire = []
    started = fake_time.monotonic()

    def record(kind, **data):
        wire.append(dict(kind=kind, epoch=epoch, tick=clock.tick,
                         wall=fake_time.monotonic() - started, **data))

    def health():
        pass

    def receive_workers(requests, epoch_arg, *, health):
        return {name: {"tick": request["tick"],
                       "state": [float(request["tick"]) * 4000.0] +
                                [0.0] * 89}
                for name, (_, request) in requests.items()}

    def sensor_fields(state):
        return {"timestamp": state[0], "imu": {"gyro": [0.0, 0.0, 0.0]}}

    # census=False models the old env-flag-on behaviour (cpu_timing enabled,
    # >2ms / tick%250 sampling kept); census=True lifts both sites to full
    # census.  The oxv29042 field run had the env flag off (0 rows, see
    # mixed-work-overrun-20260913-v2); this fixture compares the two on states.
    physics = types.SimpleNamespace(
        cpu_timing=True, timing_census=census, health=health, clock=clock,
        workers={"arducopter": object(), "px4": object()}, record=record,
        ap=ap, peer=("127.0.0.1", 19002), protocol=protocol,
        pending_ap={"frame": 40, "commands": [0.0] * 16},
        px_time=None, px_commands=[0.0] * 16, states={}, inflight=None,
        terrain_feedback=None)
    for name, function in methods.items():
        setattr(physics, name, types.MethodType(function, physics))

    def wait_ap(source_frame, deadline):
        if clock.tick == SLOW_TICK:
            fake_time.bump_wall(SLOW_WAIT_WALL_NS)
            fake_time.bump_cpu(SLOW_WAIT_CPU_NS)
        else:
            fake_time.bump_wall(FAST_WAIT_WALL_NS)
            fake_time.bump_cpu(FAST_WAIT_CPU_NS)
        # mirror production order: the actuator row is recorded when the
        # actuator packet arrives, i.e. inside the input wait
        record("actuator", stack="arducopter", frame=clock.tick,
               commands=[0.0] * 16)
        return {"frame": clock.tick, "commands": [0.0] * 16}

    def wait_px4(deadline):
        fake_time.bump_wall(FAST_WAIT_WALL_NS)
        fake_time.bump_cpu(FAST_WAIT_CPU_NS)
        physics.px_time = clock.tick * 1000
        record("actuator", stack="px4", frame=clock.tick,
               commands=[0.0] * 16)
        return True

    physics.wait_ap = wait_ap
    physics.wait_px4 = wait_px4
    for function in methods.values():
        function.__globals__["time"] = fake_time
        function.__globals__["receive_workers"] = receive_workers
        function.__globals__["sensor_fields"] = sensor_fields
        function.__globals__["json"] = json

    rate_rows = []

    def rate_record(kind, **fields):
        rate_rows.append(dict(kind=kind, epoch=epoch, tick=clock.tick,
                              issued_monotonic_ns=fake_time.monotonic_ns(),
                              **fields))

    sleeps = []
    rate = JointRate(epoch, 0.5, rate_record, now=fake_time.monotonic_ns,
                     sleep=lambda seconds: sleeps.append(seconds))
    rate.reanchor(40, "fixture")
    rate.begin_group(40, health)
    for _ in range(4):
        physics.advance()
    rate.end_group(clock.tick)

    work_ns = (rate_rows[-1]["actual_end_ns"]
               - rate_rows[-2]["actual_start_ns"])
    cpu_rows = [row for row in wire if row["kind"]
                == "diagnostic_step_cpu_timing"]
    native_rows = [row for row in wire if row["kind"]
                   == "diagnostic_native_input_timing"]
    return {
        "census": census,
        "source_sha256": source_sha,
        "rate_rows": rate_rows,
        "wire": wire,
        "clock_calls": clock.calls,
        "ap_sends": [(packet.decode("ascii"), list(peer))
                     for packet, peer in ap.sent],
        "protocol_sends": [payload.hex() for payload in protocol.sent],
        "sleeps": sleeps,
        "work_ns": work_ns,
        "step_cpu_rows": len(cpu_rows),
        "native_input_rows": len(native_rows),
        "tick_reached": clock.tick,
    }


def ordinary_events(run):
    return [(row["kind"], row["tick"],
             {key: value for key, value in row.items()
              if key not in ("wall",)})
            for row in run["wire"]
            if not row["kind"].startswith("diagnostic_")]


def compare_modes(fast, census):
    """Ordinary events and clock progression must be identical either way."""
    return {
        "ordinary_events_identical":
            ordinary_events(fast) == ordinary_events(census),
        "clock_calls_identical": fast["clock_calls"] == census["clock_calls"],
        "ap_sends_identical": fast["ap_sends"] == census["ap_sends"],
        "protocol_sends_identical":
            fast["protocol_sends"] == census["protocol_sends"],
        "tick_reached_identical":
            fast["tick_reached"] == census["tick_reached"],
        "work_differs_only_by_diagnostic_reads":
            census["work_ns"] > fast["work_ns"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=HERE / "group-work-timing-fixture.json")
    args = parser.parse_args(argv)
    fast = produce(False)
    census = produce(True)
    result = {
        "schema": "wksim.group-work-timing-fixture.v1",
        "source_sha256": fast["source_sha256"],
        "patched_sha256": hashlib.sha256(patch_tool.apply_patch(
            (ROOT / "Simulator" / "wksim_core" / "joint.py")
            .read_bytes())).hexdigest(),
        "extracted_methods": list(EXTRACTED_METHODS),
        "fake_globals": list(FAKE_GLOBALS),
        "module_imported": False,
        "constructor_called": False,
        "slow_tick": SLOW_TICK,
        "slow_wait_wall_ns": SLOW_WAIT_WALL_NS,
        "runs": {"census_false": fast, "census_true": census},
        "mode_comparison": compare_modes(fast, census),
        "script_sha256": hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest(),
    }
    if args.output.exists():
        raise SystemExit(f"output exists, refusing: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({
        "output": str(args.output),
        "work_ns": {mode: run["work_ns"] for mode, run in result["runs"].items()},
        "step_cpu_rows": {"false": fast["step_cpu_rows"],
                          "true": census["step_cpu_rows"]},
        "native_input_rows": {"false": fast["native_input_rows"],
                              "true": census["native_input_rows"]},
        "mode_comparison": result["mode_comparison"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
