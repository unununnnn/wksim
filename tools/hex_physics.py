"""Explicit experimental six-motor binding of the unchanged physics loops.

One process / one verified Hex lifetime. No production registration or UE stream.
The trace records accepted actuator packets and every held 1 ms native input/output.
"""
import argparse
from contextlib import contextmanager
import importlib
import json
import math
from pathlib import Path
import re
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Simulator.wksim_core import ap_json
from tools.build_hex_model_candidate import HexModel, load_config, sha, verify_build

LIBRARY_SHA256 = "b10ef333129b44ce41d2d8d944a1e3d1161db9201bb1aea9eca88e726a5a7c9c"
MODEL_IDENTITY = "sha256:d703da7f888e7110e402aa32ff911cabcb24e0b01afb8bbf4c9ec1ccb897276a"
_quad_decode = ap_json.decode_servos


def decode_servos(packet):
    # Retain original exact size, magic, rate and first-four validation.
    frame, rate, pwm, _ = _quad_decode(packet)
    if any(value != 0 and not 1000 <= value <= 2000 for value in pwm[4:6]):
        raise ValueError("Hex motor PWM outside configured 1000..2000 range")
    return frame, rate, pwm, [max(0, value - 1000) / 1000 for value in pwm[:6]] + [0.] * 10


def actuator_commands(message):
    if len(message.controls) != 16:
        raise ValueError("HIL_ACTUATOR_CONTROLS requires 16 channels")
    # Match the original disarmed behavior; unused/NaN outputs never reach ABI.
    if not message.mode & 128:  # MAV_MODE_FLAG_SAFETY_ARMED
        return [0.] * 16
    motors = list(message.controls[:6])
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in motors):
        raise ValueError("PX4 Hex motor outputs must be finite normalized [0,1]")
    return motors + [0.] * 10


class Recorder:
    def __init__(self, stream):
        self.stream = stream
        self.held_packet = None
        self.groups = 0

    def write(self, record):
        self.stream.write(json.dumps(record, allow_nan=False, separators=(",", ":")) + "\n")
        if record.get('kind') == 'step' and record['tick'] % 20 == 0:
            self.stream.flush()

    def actuator(self, raw, **fields):
        self.held_packet = dict(packet_hex=bytes(raw).hex(), **fields)
        self.write(dict(kind="actuator", **self.held_packet))


def observed_model(config, recorder):
    class ObservedHex(HexModel):
        def __init__(self, library):
            super().__init__(library, config)
            recorder.write(dict(kind="initialized", readback=self.readback, initial_tick=self.ticks))

        def step(self, commands, steps=1):
            if type(steps) is not int or not 1 <= steps <= 1000:
                raise ValueError("steps must be an integer in [1,1000]")
            recorder.groups += 1
            for substep in range(steps):
                output = super().step(commands, 1)
                recorder.write(dict(kind="step", tick=self.ticks, group=recorder.groups,
                    group_steps=steps, substep=substep, input16=list(commands), output120=output,
                    held_packet=recorder.held_packet, observed_monotonic_ns=time.monotonic_ns()))
            return output

        def close(self):
            super().close()
            recorder.stream.flush()
    return ObservedHex


@contextmanager
def bind(module, model_class, recorder):
    """Process-local substitutions only; restore on success and all failures.

    Call in the dedicated physics process, never in a concurrent shared service.
    Original serve/Lockstep retain peer filtering, replay and clock decisions.
    """
    key = "decode_servos" if module is ap_json else "actuator_commands"
    original_model, original_decode = module.Model, getattr(module, key)

    def decode(packet):
        result = decode_servos(packet)
        recorder.actuator(packet, frame=result[0], rate=result[1], pwm16=result[2])
        return result

    def commands(message):
        result = actuator_commands(message)
        recorder.actuator(message.get_msgbuf(), time_usec=message.time_usec,
                          mode=message.mode, flags=message.flags)
        return result

    module.Model = model_class
    setattr(module, key, decode if module is ap_json else commands)
    try:
        yield
    finally:
        module.Model = original_model
        setattr(module, key, original_decode)


def serve(stack, library, config_path, port, trace, raw, duration=None, *, run_id=None):
    if stack not in ("arducopter", "px4"):
        raise ValueError("Unsupported stack")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Invalid port")
    if duration is not None and (not math.isfinite(duration) or not 0 < duration <= 3600):
        raise ValueError("duration must be in (0,3600]")
    if run_id is not None and (type(run_id) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',run_id)):
        raise ValueError('Invalid run identity')
    config = load_config(config_path)
    library = verify_build(library, config)  # no native load
    if config["model_identity"] != MODEL_IDENTITY or sha(library.read_bytes()) != LIBRARY_SHA256:
        raise ValueError("This runtime seam requires the verified Hex candidate identity")
    module = ap_json if stack == "arducopter" else importlib.import_module("Simulator.wksim_core.px4_mavlink")
    with Path(raw).open("x", encoding="utf-8", buffering=1024 * 1024) as stream:
        recorder = Recorder(stream)
        sources = [Path(__file__), ROOT / "tools/build_hex_model_candidate.py",
                   *[ROOT / "Simulator/wksim_core" / name for name in
                     ("ap_json.py", "px4_mavlink.py", "model.py", "model.cpp", "state_stream.py")]]
        recorder.write(dict(kind="start", schema="wksim.hex.physics.v1", stack=stack, run_id=run_id,
            library=str(library), library_sha256=LIBRARY_SHA256, model_identity=MODEL_IDENTITY,
            config=config, dt_s=.001, sources_sha256={str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sources}))
        try:
            with bind(module, observed_model(config, recorder), recorder):
                # StateWriter(None) is inactive: quad metadata must not be emitted.
                extra = {"speedup": 1} if stack == "px4" else {}
                result = module.serve(library, port, trace, duration=duration, **extra)
        except BaseException as error:
            recorder.write(dict(kind="end", status="interrupted_or_failed", error_type=type(error).__name__, error=str(error)))
            raise
        recorder.write(dict(kind="end", status="completed", summary=result))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack", required=True, choices=("arducopter", "px4"))
    for name in ("library", "config", "trace", "raw"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    def retire(signum, frame):
        raise InterruptedError("Owned Hex physics process retired")

    signal.signal(signal.SIGTERM, retire)
    try:
        serve(args.stack, args.library, args.config, args.port, args.trace, args.raw, args.duration, run_id=args.run_id)
    except InterruptedError:
        pass


if __name__ == "__main__":
    main()
