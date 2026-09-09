"""Read-only audit of a Hex ``physics-1ms.jsonl`` evidence stream."""
import argparse
from collections import OrderedDict
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import hex_physics
from Simulator.wksim_core import px4_mavlink


SCHEMA = "wksim.hex.physics.evidence.v1"
DT_S = 0.001
OUTPUT_COUNT = 120
INPUT_COUNT = 16
UNUSED_INPUTS = range(6, 16)
RPM_OUTPUTS = range(16, 22)
NORMAL_RETIREMENT = "Owned Hex physics process retired"


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _close(left, right, tolerance=1e-8):
    return _number(left) and _number(right) and abs(left - right) <= tolerance


def _same_vector(left, right, tolerance=1e-12):
    return (isinstance(left, list) and isinstance(right, list) and len(left) == len(right)
            and all(_close(a, b, tolerance) for a, b in zip(left, right)))


def _packet_inputs(stack, packet_hex):
    if not isinstance(packet_hex, str) or len(packet_hex) % 2:
        raise ValueError("packet_hex must be an even-length hexadecimal string")
    try:
        raw = bytes.fromhex(packet_hex)
    except ValueError as error:
        raise ValueError("packet_hex is not hexadecimal") from error
    if stack == "arducopter":
        frame, rate, pwm, normalized = hex_physics.decode_servos(raw)
        return normalized, {"frame": frame, "rate": rate, "pwm16": list(pwm)}
    if stack != "px4":
        raise ValueError("unsupported stack")
    decoder = px4_mavlink.mavlink.MAVLink(None)
    messages = decoder.parse_buffer(raw) or []
    if len(messages) != 1 or messages[0].get_type() != "HIL_ACTUATOR_CONTROLS":
        raise ValueError("packet_hex must contain one HIL_ACTUATOR_CONTROLS frame")
    message = messages[0]
    if bytes(message.get_msgbuf()) != raw:
        raise ValueError("decoded actuator frame differs from packet_hex")
    return hex_physics.actuator_commands(message), {
        "time_usec": int(message.time_usec),
        "mode": int(message.mode),
        "flags": int(message.flags),
    }


class _Audit:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.errors = []
        self.checks = OrderedDict((name, True) for name in (
            "record_sequence", "binding", "finite_values", "tick_clock",
            "group_structure", "input_shape", "held_input_reconstruction",
            "rpm_fields", "terminal"))

    def error(self, code, message, line=None, check="record_sequence"):
        self.checks[check] = False
        item = {"code": code, "message": message}
        if line is not None:
            item["line"] = line
        self.errors.append(item)


def _validate_start(row, audit, expected_run_id, expected_model_identity):
    if row.get("schema") != "wksim.hex.physics.v1":
        audit.error("schema_mismatch", "start.schema is not wksim.hex.physics.v1")
    stack = row.get("stack")
    if stack not in ("px4", "arducopter"):
        audit.error("stack_missing", "start.stack must be px4 or arducopter", check="binding")
    run_id = row.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        audit.error("run_id_missing", "start.run_id is required", check="binding")
    elif expected_run_id is not None and run_id != expected_run_id:
        audit.error("run_id_mismatch", f"start.run_id {run_id!r} != expected {expected_run_id!r}", check="binding")
    model_identity = row.get("model_identity")
    if not isinstance(model_identity, str) or not model_identity:
        audit.error("model_identity_missing", "start.model_identity is required", check="binding")
    elif expected_model_identity is not None and model_identity != expected_model_identity:
        audit.error("model_identity_mismatch", "start.model_identity differs from expected", check="binding")
    if not isinstance(row.get("library_sha256"), str) or len(row["library_sha256"]) != 64:
        audit.error("library_identity_missing", "start.library_sha256 must be a SHA256 hex string", check="binding")
    if not _close(row.get("dt_s"), DT_S, 0.0):
        audit.error("dt_mismatch", "start.dt_s must be 0.001", check="binding")
    config = row.get("config")
    if not isinstance(config, dict):
        audit.error("config_missing", "start.config must be an object", check="binding")
    else:
        if config.get("model_identity") != model_identity:
            audit.error("config_identity_mismatch", "start.config.model_identity differs from start.model_identity", check="binding")
        profile = config.get("profile")
        if isinstance(profile, dict):
            if profile.get("input_count") != INPUT_COUNT or profile.get("output_count") != OUTPUT_COUNT:
                audit.error("profile_shape_mismatch", "start.config profile must declare 16 inputs and 120 outputs", check="binding")
            if not _close(profile.get("dt_s"), DT_S, 0.0):
                audit.error("profile_dt_mismatch", "start.config.profile.dt_s must be 0.001", check="binding")
    if not isinstance(row.get("sources_sha256"), dict) or not row["sources_sha256"]:
        audit.error("source_identity_missing", "start.sources_sha256 must be a non-empty object", check="binding")


def _write_result(result, output, root):
    path = Path(output).resolve()
    root = Path(root).resolve()
    if path == root or path.is_relative_to(root):
        raise ValueError("output must be outside the original run root")
    with path.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


def check(root, *, expected_run_id=None, expected_model_identity=None, output=None):
    """Audit one immutable run directory without modifying it.

    ``output`` is optional; when provided it must name a new file outside
    ``root``.  The returned object is always the same schema as the file.
    """
    audit = _Audit(root)
    path = audit.root / "physics-1ms.jsonl"
    result = {
        "schema": SCHEMA,
        "status": "rejected",
        "passed": False,
        "root": str(audit.root),
        "source": {},
        "terminal": {},
        "counts": {
            "lines": 0, "start": 0, "initialized": 0, "actuator": 0,
            "step": 0, "end": 0, "groups": 0, "distinct_actuator_packets": 0,
            "repeated_actuator_packets": 0, "held_packet_none_steps": 0,
        },
        "checks": audit.checks,
        "errors": audit.errors,
    }
    if not path.is_file():
        audit.error("physics_stream_missing", f"missing {path}")
    else:
        start = None
        initialized = None
        current_packet = None
        packet_cache = {}
        packet_hexes = set()
        expected_tick = 1
        current_group = None
        current_group_steps = None
        current_group_size = 0
        current_group_input = None
        current_group_packet = None
        seen_end = False
        stack = None
        try:
            with path.open(encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, 1):
                    result["counts"]["lines"] += 1
                    try:
                        row = json.loads(line)
                    except (json.JSONDecodeError, UnicodeDecodeError) as error:
                        audit.error("invalid_json", str(error), line_number)
                        continue
                    if not isinstance(row, dict):
                        audit.error("record_not_object", "each JSONL record must be an object", line_number)
                        continue
                    kind = row.get("kind")
                    if line_number == 1 and kind != "start":
                        audit.error("start_not_first", "the first record must be start", line_number)
                    if seen_end:
                        audit.error("records_after_terminal", "records exist after the terminal end record", line_number)
                        continue
                    if kind == "start":
                        result["counts"]["start"] += 1
                        if start is not None:
                            audit.error("duplicate_start", "start must occur exactly once", line_number)
                        else:
                            start = row
                            stack = row.get("stack")
                            _validate_start(row, audit, expected_run_id, expected_model_identity)
                            result["source"] = {
                                "stack": row.get("stack"), "run_id": row.get("run_id"),
                                "model_identity": row.get("model_identity"),
                                "library": row.get("library"), "library_sha256": row.get("library_sha256"),
                                "dt_s": row.get("dt_s"), "sources_sha256": row.get("sources_sha256", {}),
                            }
                    elif kind == "initialized":
                        result["counts"]["initialized"] += 1
                        if start is None:
                            audit.error("initialized_before_start", "initialized cannot precede start", line_number)
                        if initialized is not None:
                            audit.error("duplicate_initialized", "initialized must occur exactly once", line_number)
                        elif result["counts"]["step"]:
                            audit.error("initialized_after_step", "initialized must precede all steps", line_number)
                        else:
                            initialized = row
                            result["source"]["initial_tick"] = row.get("initial_tick")
                            if row.get("initial_tick") != 0:
                                audit.error("initial_tick_mismatch", "initialized.initial_tick must be 0", line_number, "tick_clock")
                    elif kind == "actuator":
                        result["counts"]["actuator"] += 1
                        if initialized is None:
                            audit.error("actuator_before_initialized", "actuator cannot precede initialized", line_number)
                        packet_hex = row.get("packet_hex")
                        try:
                            if packet_hex not in packet_cache:
                                packet_cache[packet_hex] = _packet_inputs(stack, packet_hex)
                            normalized, metadata = packet_cache[packet_hex]
                            for key, value in metadata.items():
                                if row.get(key) != value:
                                    audit.error("actuator_metadata_mismatch", f"actuator.{key} differs from packet", line_number, "held_input_reconstruction")
                            current_packet = {key: value for key, value in row.items() if key != "kind"}
                            if packet_hex in packet_hexes:
                                result["counts"]["repeated_actuator_packets"] += 1
                            else:
                                packet_hexes.add(packet_hex)
                                result["counts"]["distinct_actuator_packets"] += 1
                        except (TypeError, ValueError, KeyError, AttributeError) as error:
                            audit.error("actuator_decode_failed", str(error), line_number, "held_input_reconstruction")
                    elif kind == "step":
                        result["counts"]["step"] += 1
                        if initialized is None:
                            audit.error("step_before_initialized", "step cannot precede initialized", line_number)
                        tick = row.get("tick")
                        if not isinstance(tick, int) or isinstance(tick, bool) or tick < 1:
                            audit.error("invalid_tick", "step.tick must be a positive integer", line_number, "tick_clock")
                            tick = expected_tick
                        elif tick != expected_tick:
                            audit.error("tick_discontinuity", f"expected tick {expected_tick}, got {tick}", line_number, "tick_clock")
                        expected_tick = tick + 1
                        output_values = row.get("output120")
                        input_values = row.get("input16")
                        if not isinstance(output_values, list) or len(output_values) != OUTPUT_COUNT:
                            audit.error("output_shape", "step.output120 must contain 120 values", line_number, "input_shape")
                            output_values = []
                        elif any(not _number(value) for value in output_values):
                            audit.error("nonfinite_output", "step.output120 must contain only finite numbers", line_number, "finite_values")
                        elif any(not _number(output_values[index]) for index in RPM_OUTPUTS):
                            audit.error("invalid_rpm_fields", "step.output120 RPM fields 16..21 must be finite", line_number, "rpm_fields")
                        if output_values and not _close(output_values[2], tick * DT_S):
                            audit.error("model_clock_mismatch", "output120[2] does not match tick * 0.001", line_number, "tick_clock")
                        if not isinstance(input_values, list) or len(input_values) != INPUT_COUNT:
                            audit.error("input_shape", "step.input16 must contain 16 values", line_number, "input_shape")
                            input_values = []
                        elif any(not _number(value) or not 0 <= value <= 1 for value in input_values):
                            audit.error("invalid_input", "step.input16 must be finite and normalized in [0,1]", line_number, "input_shape")
                        elif any(input_values[index] != 0 for index in UNUSED_INPUTS):
                            audit.error("unused_input_nonzero", "step.input16 channels 6..15 must be zero", line_number, "input_shape")
                        held = row.get("held_packet")
                        if held is None:
                            result["counts"]["held_packet_none_steps"] += 1
                            if current_packet is not None:
                                audit.error("held_packet_missing", "held_packet became None after an actuator record", line_number, "held_input_reconstruction")
                            elif input_values and any(value != 0 for value in input_values):
                                audit.error("initial_input_nonzero", "initial held_packet=None steps must have zero input", line_number, "held_input_reconstruction")
                            expected_input = [0.0] * INPUT_COUNT
                        elif current_packet is None or held != current_packet:
                            audit.error("held_packet_not_current", "step.held_packet is not the latest actuator record", line_number, "held_input_reconstruction")
                            expected_input = None
                        else:
                            try:
                                packet_hex = held["packet_hex"]
                                if packet_hex not in packet_cache:
                                    packet_cache[packet_hex] = _packet_inputs(stack, packet_hex)
                                expected_input = packet_cache[packet_hex][0]
                            except (KeyError, TypeError, ValueError, AttributeError) as error:
                                audit.error("held_packet_decode_failed", str(error), line_number, "held_input_reconstruction")
                                expected_input = None
                        if expected_input is not None and input_values and not _same_vector(input_values, expected_input):
                            audit.error("input_mismatch", "step.input16 differs from the decoded held actuator packet", line_number, "held_input_reconstruction")
                        group = row.get("group")
                        group_steps = row.get("group_steps")
                        substep = row.get("substep")
                        if not all(isinstance(value, int) and not isinstance(value, bool) for value in (group, group_steps, substep)):
                            audit.error("invalid_group_fields", "group, group_steps and substep must be integers", line_number, "group_structure")
                            group = current_group or 1
                            group_steps = current_group_steps or 1
                            substep = current_group_size
                        if group_steps < 1 or group_steps > 1000:
                            audit.error("invalid_group_steps", "group_steps must be in [1,1000]", line_number, "group_structure")
                        if current_group is None or group != current_group:
                            if current_group is not None and current_group_size != current_group_steps:
                                audit.error("group_incomplete", f"group {current_group} has {current_group_size} of {current_group_steps} steps", line_number, "group_structure")
                            if current_group is None:
                                if group != 1:
                                    audit.error("group_not_one", "first group must be 1", line_number, "group_structure")
                            elif group != current_group + 1:
                                audit.error("group_discontinuity", f"expected group {current_group + 1}, got {group}", line_number, "group_structure")
                            current_group, current_group_steps = group, group_steps
                            current_group_size = 0
                            current_group_input = None
                            current_group_packet = held
                        elif group_steps != current_group_steps:
                            audit.error("group_steps_changed", "group_steps must remain constant inside a group", line_number, "group_structure")
                        if substep != current_group_size:
                            audit.error("substep_discontinuity", f"expected substep {current_group_size}, got {substep}", line_number, "group_structure")
                        if current_group_input is None:
                            current_group_input = input_values
                        elif input_values and not _same_vector(input_values, current_group_input):
                            audit.error("group_input_changed", "input16 changed inside one model step group", line_number, "group_structure")
                        if held != current_group_packet:
                            audit.error("group_packet_changed", "held_packet changed inside one model step group", line_number, "group_structure")
                        current_group_size += 1
                    elif kind == "end":
                        result["counts"]["end"] += 1
                        if start is None or initialized is None:
                            audit.error("end_before_header", "end requires start and initialized", line_number)
                        if seen_end:
                            audit.error("duplicate_terminal", "end must occur exactly once", line_number, "terminal")
                        seen_end = True
                        status = row.get("status")
                        result["terminal"] = {"status": status, "error": row.get("error")}
                        if status == "interrupted_or_failed" and row.get("error") != NORMAL_RETIREMENT:
                            audit.error("terminal_failure", "interrupted_or_failed terminal is not the expected owner retirement", line_number, "terminal")
                        elif status not in ("completed", "interrupted_or_failed"):
                            audit.error("invalid_terminal_status", "end.status must be completed or expected owner retirement", line_number, "terminal")
                    else:
                        audit.error("unknown_record_kind", f"unsupported record kind {kind!r}", line_number)
        except OSError as error:
            audit.error("physics_stream_read_failed", str(error))
        if current_group is not None and current_group_size != current_group_steps:
            audit.error("group_incomplete", f"group {current_group} has {current_group_size} of {current_group_steps} steps", check="group_structure")
        if result["counts"]["start"] != 1:
            audit.error("start_count", "physics stream must contain exactly one start")
        if result["counts"]["initialized"] != 1:
            audit.error("initialized_count", "physics stream must contain exactly one initialized record")
        if result["counts"]["step"] == 0:
            audit.error("no_steps", "physics stream must contain at least one step")
        if result["counts"]["end"] != 1:
            audit.error("terminal_count", "physics stream must contain exactly one terminal end record", check="terminal")
        result["counts"]["groups"] = current_group or 0
    result["checks"] = audit.checks
    result["errors"] = audit.errors
    result["passed"] = not audit.errors
    result["status"] = "passed" if result["passed"] else "rejected"
    if output is not None:
        try:
            _write_result(result, output, audit.root)
            result["output"] = str(Path(output).resolve())
        except (OSError, ValueError) as error:
            audit.error("output_write_failed", str(error))
            result["checks"] = audit.checks
            result["errors"] = audit.errors
            result["passed"] = False
            result["status"] = "rejected"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="Original run directory containing physics-1ms.jsonl")
    parser.add_argument("--output", type=Path, help="New audit JSON path outside --root")
    parser.add_argument("--run-id")
    parser.add_argument("--model-identity")
    args = parser.parse_args(argv)
    result = check(args.root, expected_run_id=args.run_id,
                   expected_model_identity=args.model_identity, output=args.output)
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
