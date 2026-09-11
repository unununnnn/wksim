"""Retained real-worker terrain feedback probe for issue #29.

The probe is deliberately narrower than the formal joint runtime: it uses the
real generated model ABI and worker pipes, while a deterministic native-I/O
stub supplies only exact AP acknowledgements and the four-millisecond PX4
barriers. It makes no SITL, UE, FC, ROS, MATLAB, or contact-force claim.
"""

import argparse
import hashlib
import json
import math
from contextlib import ExitStack
from pathlib import Path
import subprocess
import sys
import uuid

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Simulator.wksim_core.joint import JointPhysics
from Simulator.wksim_core.static_contact import StaticScene
from Simulator.wksim_core.worker import receive_workers
from Simulator.wksim_runtime.contact_observer import (
    DEFAULT_SCENE_PATH,
    FROZEN_SCENE_SHA256,
)
from Simulator.wksim_runtime.scene_clock import SceneClock
from Simulator.wksim_runtime.terrain_feedback import (
    TerrainFeedback,
    vehicle60_to_enu_query_point,
)


TICKS = 50
STEP_NS = 1_000_000
MACRO_TICKS = 4
STACKS = ("arducopter", "px4")
ZERO_COMMANDS = [0.0] * 16
BASELINE_TERRAIN = [0.0] * 15
ELEVATED_TERRAIN = [-1.0] + [0.0] * 14
SOURCE_FILES = (
    "Simulator/wksim_core/model.py",
    "Simulator/wksim_core/model.cpp",
    "Simulator/wksim_core/worker.py",
    "Simulator/wksim_core/joint.py",
    "Simulator/wksim_runtime/scene_clock.py",
    "Simulator/wksim_runtime/terrain_feedback.py",
    "Simulator/wksim_runtime/contact_observer.py",
    "Simulator/wksim_core/static_contact.py",
    "Simulator/wksim_runtime/static-scene-v1.json",
    "tools/probe_joint_terrain_feedback.py",
)


class ProbeError(RuntimeError):
    """A deterministic probe validation or execution failure."""


class ScenarioFailure(ProbeError):
    def __init__(self, scenario, evidence, cause):
        self.scenario = scenario
        self.evidence = evidence
        self.cause = cause
        super().__init__(f"{scenario} scenario failed: {cause}")


class WorkerLaunchFailure(ProbeError):
    def __init__(self, scenario, records, cause):
        self.scenario = scenario
        self.records = records
        self.cause = cause
        super().__init__(f"{scenario} worker launch failed: {cause}")


def _canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256_file(path):
    return _sha256_bytes(Path(path).read_bytes())


def _finite_triplet(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ProbeError("tick-0 ENU position must contain three values")
    if any(isinstance(item, bool) or not isinstance(item, (int, float))
           or not math.isfinite(item) for item in value):
        raise ProbeError("tick-0 ENU position must be finite numeric data")
    return [float(item) for item in value]


def make_elevated_scene(initial_enu):
    """Create and immediately verify the one-metre elevated probe scene."""
    initial_enu = _finite_triplet(initial_enu)
    box = {
        "geometry_id": "box_0",
        "center_enu_m": [initial_enu[0], initial_enu[1], 0.5],
        "size_m": [1.0, 1.0, 1.0],
    }
    geometry = {
        "origin_enu_m": [0.0, 0.0, 0.0],
        "plane": {"geometry_id": "plane_z0", "z_m": 0.0},
        "box": box,
    }
    config = {
        "schema": "wksim.static-scene.v1",
        "scene_id": "static-plane-box-v1-real-tick0",
        "coordinate_frame": "ENU",
        "unit": "metre",
        "origin_enu_m": [0.0, 0.0, 0.0],
        "plane": {"geometry_id": "plane_z0", "z_m": 0.0},
        "box": box,
        "scene_sha256": _sha256_bytes(_canonical_json(geometry).encode("utf-8")),
    }
    scene = StaticScene(config)
    if scene.support_height_enu_m(initial_enu) != 1.0:
        raise ProbeError("generated elevated scene did not provide one-metre support")
    return config


def validate_cli_inputs(library, output, platform=None):
    """Validate Linux-only inputs without creating or touching the output."""
    platform = sys.platform if platform is None else platform
    if platform != "linux":
        raise ProbeError("the terrain probe requires Linux/WSL")
    library = Path(library)
    if not library.is_file():
        raise ProbeError(f"library is not a regular file: {library}")
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ProbeError("--output must name a new output directory")
    if not output.parent.is_dir():
        raise ProbeError(f"output parent does not exist: {output.parent}")
    return library.resolve(), output.resolve()


def _initial_request(epoch):
    return {"version": 1, "epoch": epoch, "initial": True}


def _positive_zero(value):
    return type(value) is float and value == 0.0 and math.copysign(1.0, value) > 0


def _exact_float_vector(actual, expected):
    if not isinstance(actual, list) or len(actual) != len(expected):
        return False
    for value, wanted in zip(actual, expected):
        if type(value) is not float:
            return False
        if wanted == 0.0:
            if not _positive_zero(value):
                return False
        elif value != wanted:
            return False
    return True


def _finite_state(state):
    return (isinstance(state, list) and len(state) == 120
            and all(type(value) in (int, float) and not isinstance(value, bool)
                    and math.isfinite(value) for value in state))


def _audit_clock_snapshots(snapshots):
    if not isinstance(snapshots, list) or len(snapshots) != TICKS + 1:
        raise ProbeError("clock evidence must contain tick zero plus 50 steps")
    for expected_tick, clock in enumerate(snapshots):
        if not isinstance(clock, dict):
            raise ProbeError("clock evidence contains a non-object snapshot")
        if clock.get("tick") != expected_tick:
            raise ProbeError("clock evidence skipped or reordered a tick")
        if clock.get("time_ns") != expected_tick * STEP_NS:
            raise ProbeError("clock evidence violates the fixed one-millisecond step")
        if clock.get("pending_tick") is not None:
            raise ProbeError("clock evidence retained an uncommitted model tick")
        if clock.get("phase") != "running":
            raise ProbeError("clock evidence left the running phase")
        if clock.get("last_input_tick") != expected_tick:
            raise ProbeError("clock evidence lacks the per-tick AP acknowledgement")
        if clock.get("last_barrier_tick") != expected_tick - expected_tick % MACRO_TICKS:
            raise ProbeError("clock evidence lacks the four-millisecond barrier")
        if clock.get("synchronized") is not (expected_tick >= MACRO_TICKS):
            raise ProbeError("clock evidence has the wrong PX4 synchronization state")
        if clock.get("input_pending") is not False or clock.get("recoverable") is not False:
            raise ProbeError("clock evidence retained an input fault or recovery state")


def audit_initial_sidecar(rows, epoch):
    if not isinstance(rows, list) or len(rows) != 1:
        raise ProbeError("each worker must retain exactly one initial-state sidecar row")
    row = rows[0]
    if not isinstance(row, dict) or set(row) != {
            "version", "epoch", "tick", "state", "initial", "input", "request"}:
        raise ProbeError("initial-state sidecar has the wrong evidence shape")
    request = _initial_request(epoch)
    if (row["version"], row["epoch"], row["tick"], row["initial"]) != (1, epoch, 0, True):
        raise ProbeError("initial-state sidecar has the wrong identity")
    if row["request"] != request:
        raise ProbeError("initial-state sidecar retained the wrong request")
    try:
        decoded = json.loads(row["input"])
    except (TypeError, ValueError) as exc:
        raise ProbeError("initial-state sidecar retained invalid raw input") from exc
    if decoded != request or not _finite_state(row["state"]):
        raise ProbeError("initial-state sidecar retained invalid state evidence")
    return _sha256_bytes(_canonical_json(row["state"]).encode("utf-8"))


def audit_scenario(evidence):
    """Audit retained worker traces and clocks without running any process."""
    if not isinstance(evidence, dict):
        raise ProbeError("scenario evidence must be an object")
    epoch = evidence.get("epoch")
    trace_rows = evidence.get("trace_rows")
    expected_terrain = evidence.get("expected_terrain")
    if (not isinstance(epoch, str) or not isinstance(trace_rows, dict)
            or set(trace_rows) != set(STACKS)):
        raise ProbeError("scenario evidence must contain both worker traces")
    allowed = (BASELINE_TERRAIN, ELEVATED_TERRAIN)
    if not any(_exact_float_vector(expected_terrain, candidate) for candidate in allowed):
        raise ProbeError("scenario evidence contains an invalid expected Terrain15D")
    _audit_clock_snapshots(evidence.get("clock_snapshots"))

    final_states = {}
    terrain_by_trace = {}
    for stack in STACKS:
        rows = trace_rows[stack]
        if not isinstance(rows, list) or len(rows) != TICKS:
            raise ProbeError(f"{stack} trace must contain exactly 50 records")
        values = []
        for expected_tick, row in enumerate(rows, 1):
            expected_request = {
                "version": 1,
                "epoch": epoch,
                "tick": expected_tick,
                "commands": list(ZERO_COMMANDS),
                "terrain": list(expected_terrain),
            }
            if not isinstance(row, dict) or set(row) != {
                    "version", "epoch", "tick", "state", "request",
                    "input", "commands", "terrain"}:
                raise ProbeError(f"{stack} trace row has the wrong evidence shape")
            if (row["version"], row["epoch"], row["tick"]) != (1, epoch, expected_tick):
                raise ProbeError(f"{stack} trace has a wrong epoch or tick")
            if row["request"] != expected_request:
                raise ProbeError(f"{stack} trace retained the wrong request")
            try:
                decoded = json.loads(row["input"])
            except (TypeError, ValueError) as exc:
                raise ProbeError(f"{stack} trace retained invalid raw input") from exc
            if decoded != expected_request or row["commands"] != ZERO_COMMANDS:
                raise ProbeError(f"{stack} trace retained the wrong raw command input")
            if not _exact_float_vector(row["terrain"], expected_terrain):
                raise ProbeError(f"{stack} trace retained the wrong terrain")
            state = row["state"]
            if not _finite_state(state):
                raise ProbeError(f"{stack} trace retained an invalid 120-value state")
            if abs(state[2] - expected_tick * 0.001) > 1e-8:
                raise ProbeError(f"{stack} state does not prove a one-millisecond tick")
            if round(state[60]) != expected_tick * 1000:
                raise ProbeError(f"{stack} state does not prove the expected sensor time")
            values.append(list(row["terrain"]))
            final_states[stack] = state
        terrain_by_trace[stack] = values

    for index in range(TICKS):
        if trace_rows[STACKS[0]][index]["state"] != trace_rows[STACKS[1]][index]["state"]:
            raise ProbeError("the two native Exp1 workers diverged within one scenario")

    final_state_sha256 = {
        stack: _sha256_bytes(_canonical_json(final_states[stack]).encode("utf-8"))
        for stack in STACKS
    }
    return {
        "ticks": TICKS,
        "stacks_identical": True,
        "terrain_by_trace": terrain_by_trace,
        "final_state_sha256": final_state_sha256,
        "final_states": final_states,
    }


def compare_scenarios(baseline, elevated):
    if baseline.get("ticks") != TICKS or elevated.get("ticks") != TICKS:
        raise ProbeError("both scenarios must retain exactly 50 ticks")
    differing_indices = {}
    for stack in STACKS:
        before = baseline["final_states"][stack]
        after = elevated["final_states"][stack]
        indices = [index for index, (left, right) in enumerate(zip(before, after))
                   if left != right]
        if not indices:
            raise ProbeError(f"elevated terrain did not change {stack} final state")
        differing_indices[stack] = indices
    return {
        "baseline_final_state_sha256": dict(baseline["final_state_sha256"]),
        "elevated_final_state_sha256": dict(elevated["final_state_sha256"]),
        "differing_indices": differing_indices,
        "both_stacks_differ": True,
    }


class DeterministicNativeIOStub:
    """Only exact AP ACKs and 4 ms PX4 barriers; never computes physics."""

    label = "deterministic native-I/O stub: AP ACK + 4 ms PX4 barrier only"

    def __init__(self, clock):
        self.clock = clock
        self.physics = None
        self.ap_ack_ticks = []
        self.px4_barrier_ticks = []
        self.sensor_packets = []

    def attach(self, physics):
        self.physics = physics
        physics.ap = self
        physics.protocol = self
        physics.wait_ap = self.wait_ap
        physics.wait_px4 = self.wait_px4
        physics.peer = ("127.0.0.1", 14550)
        physics.pending_ap = {"frame": 0, "commands": list(ZERO_COMMANDS)}
        physics.px_time = 0
        physics.px_commands = list(ZERO_COMMANDS)

    def sendto(self, packet, peer):
        self.sensor_packets.append({"peer": list(peer), "size": len(packet)})
        return len(packet)

    def wait_ap(self, previous, deadline=None):
        expected = self.clock.tick
        if previous != expected - 1:
            raise ProbeError("native-I/O stub received a non-consecutive AP ACK request")
        self.ap_ack_ticks.append(expected)
        return {"frame": expected, "commands": list(ZERO_COMMANDS)}

    def wait_px4(self, deadline=None):
        expected = self.clock.tick
        if expected == 0 or expected % MACRO_TICKS:
            raise ProbeError("native-I/O stub received a PX4 wait off the 4 ms boundary")
        self.physics.px_time = expected * 1000
        self.physics.px_commands = list(ZERO_COMMANDS)
        self.px4_barrier_ticks.append(expected)
        return True

    def hil_sensor_encode(self, *args):
        return _StubMavlinkMessage("HIL_SENSOR", args)

    def hil_gps_encode(self, *args):
        return _StubMavlinkMessage("HIL_GPS", args)

    def send(self, message):
        return None


class _StubMavlinkMessage:
    """Deterministic evidence bytes for JointPhysics' retained PX4 packet record."""

    def __init__(self, kind, arguments):
        self._bytes = _canonical_json({
            "kind": kind,
            "arguments": list(arguments),
        }).encode("ascii")

    def get_msgbuf(self):
        return self._bytes


def _read_proc_start_ticks(pid):
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    closing = stat.rfind(")")
    if closing < 0:
        raise ProbeError(f"cannot parse process start ticks for PID {pid}")
    fields = stat[closing + 2:].split()
    try:
        return int(fields[19])
    except (IndexError, ValueError) as exc:
        raise ProbeError(f"cannot read process start ticks for PID {pid}") from exc


def _launch_workers(scenario, library, traces, epoch):
    records = []
    argv_template = [sys.executable, "-B", "-m", "Simulator.wksim_core.worker",
                     "--library", str(library), "--trace", "", "--epoch", epoch]
    try:
        for stack in STACKS:
            argv = list(argv_template)
            argv[argv.index("--trace") + 1] = str(traces[stack])
            child = subprocess.Popen(
                argv,
                cwd=str(REPO_ROOT),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            record = {
                "stack": stack,
                "process": child,
                "pid": child.pid,
                "argv": argv,
                "cwd": str(REPO_ROOT),
                "start_ticks": None,
                "returncode": None,
                "reaped": False,
            }
            records.append(record)
            record["start_ticks"] = _read_proc_start_ticks(child.pid)
    except BaseException as exc:
        raise WorkerLaunchFailure(scenario, records, exc) from exc
    return records


def retire_children(records, failed=False):
    """Close, terminate if needed, wait, and retain exact reap evidence."""
    for record in records:
        child = record["process"]
        try:
            try:
                child.stdin.close()
            except (AttributeError, OSError, ValueError):
                pass
            if failed and child.poll() is None:
                child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=3)
            record["returncode"] = child.returncode
            record["reaped"] = True
        except BaseException as exc:
            record["reaped"] = False
            record["cleanup_error"] = f"{type(exc).__name__}: {exc}"
        finally:
            for name in ("stdout", "stderr"):
                stream = getattr(child, name, None)
                if stream is not None:
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass


def _public_child_records(records):
    return [
        {key: value for key, value in record.items() if key != "process"}
        for record in records
    ]


def _write_json(path, value):
    Path(path).write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path, values):
    Path(path).write_text(
        "".join(_canonical_json(value) + "\n" for value in values),
        encoding="utf-8",
        newline="\n",
    )


def _load_trace(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


def _source_hashes():
    return {
        relative: sha256_file(REPO_ROOT / relative)
        for relative in SOURCE_FILES
    }


def _scenario_summary(name, epoch, scene_path, scene_config, manifest,
                      traces, clock_path, clock_snapshots, children,
                      initial_state_sha256, stub, audit):
    return {
        "name": name,
        "epoch": epoch,
        "ticks": TICKS,
        "scene_path": str(scene_path),
        "scene_config": scene_config,
        "scene_manifest": manifest,
        "trace_paths": {stack: str(traces[stack]) for stack in STACKS},
        "initial_sidecar_paths": {
            stack: str(Path(str(traces[stack]) + ".initial.jsonl"))
            for stack in STACKS
        },
        "initial_state_sha256": initial_state_sha256,
        "clock_path": str(clock_path),
        "clock_snapshots": clock_snapshots,
        "children": children,
        "native_io_stub": {
            "label": DeterministicNativeIOStub.label,
            "ap_ack_ticks": list(stub.ap_ack_ticks),
            "px4_barrier_ticks": list(stub.px4_barrier_ticks),
        },
        "terrain_by_trace": audit["terrain_by_trace"],
        "stacks_identical": audit["stacks_identical"],
        "final_state_sha256": audit["final_state_sha256"],
    }


def _run_scenario(name, library, output):
    epoch = uuid.uuid4().hex
    traces = {
        stack: output / f"{name}-{stack}-truth.jsonl"
        for stack in STACKS
    }
    clock_path = output / f"{name}-clocks.jsonl"
    records = []
    clock_snapshots = []
    scene_path = output / f"{name}-scene.json"
    scene_config = None
    manifest = None
    expected_terrain = BASELINE_TERRAIN if name == "baseline" else ELEVATED_TERRAIN
    scenario_evidence = {
        "epoch": epoch,
        "trace_rows": {},
        "clock_snapshots": clock_snapshots,
        "expected_terrain": expected_terrain,
    }
    success = False
    failure = None
    native_io = None
    try:
        try:
            records = _launch_workers(name, library, traces, epoch)
        except WorkerLaunchFailure as exc:
            records = exc.records
            raise
        initial = receive_workers(
            {record["stack"]: (record["process"], _initial_request(epoch))
             for record in records},
            epoch,
        )
        if set(initial) != set(STACKS):
            raise ProbeError("initial-state RPC did not return both stacks")
        states = {stack: initial[stack]["state"] for stack in STACKS}
        if states[STACKS[0]] != states[STACKS[1]]:
            raise ProbeError("real tick-0 model states differ between stacks")
        initial_enu = vehicle60_to_enu_query_point(states[STACKS[0]][:60])

        if name == "baseline":
            scene_config = json.loads(DEFAULT_SCENE_PATH.read_text(encoding="utf-8"))
            if scene_config.get("scene_sha256") != FROZEN_SCENE_SHA256:
                raise ProbeError("admitted frozen scene hash is not the reviewed hash")
            scene_path.write_bytes(DEFAULT_SCENE_PATH.read_bytes())
            scene_source = DEFAULT_SCENE_PATH
            expected_scene_hash = FROZEN_SCENE_SHA256
        else:
            scene_config = make_elevated_scene(initial_enu)
            scene_path.write_text(
                json.dumps(scene_config, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            scene_source = scene_config
            expected_scene_hash = scene_config["scene_sha256"]

        clock = SceneClock(epoch)
        terrain_feedback = TerrainFeedback(
            epoch,
            scene_source=scene_source,
            expected_sha256=expected_scene_hash,
        )
        runtime_records = []

        def health():
            for record in records:
                if record["process"].poll() is not None:
                    raise ProbeError(f"{record['stack']} worker exited during {name} scenario")

        def record(kind, **fields):
            runtime_records.append({"kind": kind, **fields})

        with ExitStack() as stack:
            physics = JointPhysics(
                stack,
                clock,
                {record["stack"]: record["process"] for record in records},
                health,
                record,
                terrain_feedback=terrain_feedback,
            )
            native_io = DeterministicNativeIOStub(clock)
            native_io.attach(physics)
            physics.initialize_states(initial)
            clock_snapshots.append(clock.snapshot())
            for expected_tick in range(1, TICKS + 1):
                physics.advance()
                if clock.tick != expected_tick:
                    raise ProbeError("JointPhysics did not advance one authoritative tick")
                clock_snapshots.append(clock.snapshot())
            expected_ap = list(range(1, TICKS + 1))
            expected_px4 = list(range(MACRO_TICKS, TICKS, MACRO_TICKS))
            if (native_io.ap_ack_ticks != expected_ap
                    or native_io.px4_barrier_ticks != expected_px4):
                raise ProbeError("native-I/O stub did not retain every required barrier")
            manifest = terrain_feedback.manifest()

        retire_children(records, failed=False)
        if (not all(record.get("reaped") for record in records)
                or any(record.get("returncode") != 0 for record in records)):
            raise ProbeError("real worker child retirement was not clean")
        initial_state_sha256 = {
            stack: audit_initial_sidecar(
                _load_trace(Path(str(traces[stack]) + ".initial.jsonl")), epoch)
            for stack in STACKS
        }
        scenario_evidence["trace_rows"] = {
            stack: _load_trace(traces[stack]) for stack in STACKS
        }
        audit = audit_scenario(scenario_evidence)
        success = True
        scenario = _scenario_summary(
            name, epoch, scene_path, scene_config, manifest, traces,
            clock_path, clock_snapshots, _public_child_records(records),
            initial_state_sha256, native_io, audit,
        )
        scenario["runtime_record_count"] = len(runtime_records)
        return scenario, audit
    except BaseException as exc:
        evidence = {
            "name": name,
            "epoch": epoch,
            "ticks_completed": clock_snapshots[-1]["tick"] if clock_snapshots else 0,
            "scene_path": str(scene_path),
            "scene_config": scene_config,
            "clock_path": str(clock_path),
            "clock_snapshots": clock_snapshots,
            "children": _public_child_records(records),
        }
        failure = ScenarioFailure(name, evidence, exc)
        raise failure
    finally:
        if not success:
            pending = [record for record in records if not record.get("reaped")]
            retire_children(pending, failed=True)
        if failure is not None:
            failure.evidence["children"] = _public_child_records(records)
        _write_jsonl(clock_path, clock_snapshots)


def run_probe(library, output):
    library, output = validate_cli_inputs(library, output)
    output.mkdir()
    result = {
        "schema": "wksim.lunar-29-real-terrain.v1",
        "status": "running",
        "ticks": TICKS,
        "fixed_step_ns": STEP_NS,
        "macro_barrier_ticks": list(range(MACRO_TICKS, TICKS, MACRO_TICKS)),
        "library": {"path": str(library), "sha256": sha256_file(library)},
        "source_sha256": _source_hashes(),
        "claims": {
            "terrain_feedback": "state[k-1].Vehicle60 -> ENU support height -> Terrain15D",
            "physical_boundary": "terrain input/model response only; no contact-force claim",
            "native_io": DeterministicNativeIOStub.label,
            "external_systems": "No SITL, UE, FC, ROS, or MATLAB",
        },
        "scenarios": {},
    }
    failure = None
    audits = {}
    try:
        for name in ("baseline", "elevated"):
            scenario, audit = _run_scenario(name, library, output)
            result["scenarios"][name] = scenario
            audits[name] = audit
        result["comparison"] = compare_scenarios(audits["baseline"], audits["elevated"])
        result["status"] = "passed"
    except ScenarioFailure as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        result["scenarios"][exc.scenario] = exc.evidence
        failure = exc
    except BaseException as exc:
        result["status"] = "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
        failure = exc
    finally:
        _write_json(output / "result.json", result)
    if failure is not None:
        if isinstance(failure, ProbeError):
            raise failure
        raise ProbeError(str(failure)) from failure
    return result


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_probe(args.library, args.output)
    except ProbeError as exc:
        print(f"probe failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "status": result["status"],
        "output": str(args.output),
        "ticks": result["ticks"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
