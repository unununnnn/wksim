"""Private #35 observer: actual bounded actuator-command multiplier, not #44.

The production adapters and native model are unchanged. Decoder wrappers retain
the complete source actuator packet, and each native 1ms step retains both the
decoded input16 and actually applied input16. No setpoint is used as disturbance.
"""
import argparse
import hashlib
import importlib
import json
import math
from pathlib import Path
import signal
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_core.model import Model
from Simulator.wksim_runtime.pid_task import CONFIG_SHA256, event_for, load_config


class Disturbance:
    def __init__(self, directory, run_id, config):
        self.directory, self.run_id, self.config = Path(directory), run_id, config
        self.path = self.directory/'disturbance-event.json'
        self.cancel_path = self.directory/'pid-disturbance-revoked.json'
        if self.path.exists() or self.cancel_path.exists():
            raise ValueError('New physics run requires an empty disturbance lifecycle')
        self.event = self.raw = self.sha256 = None
        self.revoked = False
        self.applied_ticks = 0
        self.next_tick = 0

    def poll(self, tick):
        if self.cancel_path.exists():
            # Presence alone revokes: a partially written failure record must
            # never delay cancellation. It cannot authorize another event.
            self.revoked = True
        if self.path.exists():
            raw = self.path.read_bytes()
            if self.raw is not None and raw != self.raw:
                raise RuntimeError('Immutable disturbance event changed')
            if self.raw is None:
                event = json.loads(raw)
                origin = event.get('declared_origin_tick')
                if (type(origin) is not int or origin < 0
                        or event != event_for(self.config, self.run_id, origin)):
                    raise ValueError('Disturbance event does not match frozen run/protocol/window')
                expected = (json.dumps(event_for(self.config, self.run_id, origin),
                                       sort_keys=True, separators=(',', ':'))+'\n').encode()
                if raw != expected:
                    raise ValueError('Disturbance event must use the exact canonical frozen bytes')
                if event['start_tick']-tick < self.config['disturbance']['minimum_load_lead_ticks']:
                    raise RuntimeError('Disturbance was not loaded at least 1 simulated second ahead')
                self.event, self.raw = event, raw
                self.sha256 = hashlib.sha256(raw).hexdigest()
        elif self.raw is not None:
            raise RuntimeError('Immutable disturbance event disappeared')

    def apply(self, commands, tick):
        if (type(tick) is not int or tick < 0 or len(commands) != 16
                or any(not math.isfinite(x) or not 0 <= x <= 1 for x in commands)):
            raise ValueError('Invalid disturbance model input or interval tick')
        if tick != self.next_tick:
            raise RuntimeError('Disturbance physical tick discontinuity; new run required')
        self.poll(tick)
        applied = list(commands)
        active = (not self.revoked and self.event is not None
                  and self.event['start_tick'] <= tick < self.event['end_tick'])
        if active:
            if not self.event['permitted_start_tick'] <= tick < self.event['permitted_end_tick']:
                raise RuntimeError('Disturbance outside permitted phase window')
            for channel in self.event['channels']:
                applied[channel] *= self.event['multiplier']
            self.applied_ticks += 1
        self.next_tick += 1
        return applied, bool(active)


def observed_model(path, directory, run_id, config, packet_context, *, base_model=Model):
    class ObservedModel(base_model):
        def __init__(self, library):
            if hashlib.sha256(Path(library).read_bytes()).hexdigest() != config['model']['library_sha256']:
                raise ValueError('PID physics library differs from fixed model identity')
            self.disturbance = Disturbance(directory, run_id, config)
            super().__init__(library)
            self.raw = Path(path).open('x', buffering=1024*1024)
            self.raw.write(json.dumps(dict(kind='start', run_id=run_id,
                schema='wksim.pid.physics.v1', library=str(library),
                library_sha256=config['model']['library_sha256'], protocol_sha256=CONFIG_SHA256,
                observer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                initial_tick=0, dt_s=.001, mass_kg=config['model']['mass_kg'],
                tick_semantics='step.tick is post-step; interval_tick is the applied input interval'))+'\n')
            self.groups = 0

        def step(self, commands, steps=1):
            if type(steps) is not int or not 1 <= steps <= 1000:
                raise ValueError('steps must be an integer in [1,1000]')
            self.groups += 1
            source_packet = packet_context.get('latest')
            for substep in range(steps):
                before = self.ticks
                applied, active = self.disturbance.apply(commands, before)
                output = super().step(applied, 1)
                self.raw.write(json.dumps(dict(kind='step', run_id=run_id, tick=self.ticks,
                    interval_tick=before, group=self.groups, group_steps=steps, substep=substep,
                    input16=list(commands), original_decoded_input16=list(commands), applied_input16=applied,
                    disturbance_active=active, disturbance_event_sha256=self.disturbance.sha256,
                    disturbance_revoked=self.disturbance.revoked,
                    raw_actuator_packet=source_packet, output120=output,
                    observed_monotonic_ns=time.monotonic_ns()), allow_nan=False)+'\n')
            if self.ticks % 1000 == 0:
                self.raw.flush()
            return output

        def close(self):
            if not self.raw.closed:
                self.raw.write(json.dumps(dict(kind='end', run_id=run_id, ticks=self.ticks, groups=self.groups,
                    disturbance_applied_ticks=self.disturbance.applied_ticks,
                    disturbance_event_sha256=self.disturbance.sha256, disturbance_revoked=self.disturbance.revoked))+'\n')
                self.raw.close()
            super().close()
    return ObservedModel


def capture_decoder(module, stack, context, raw_stream):
    """Wrap the actual decoder only; no change to admission, lockstep or routing."""
    if stack == 'arducopter':
        decode = module.decode_servos

        def observed(packet):
            result = decode(packet)
            frame, rate, pwm, commands = result
            row = dict(protocol='AP_JSON_SERVO16', packet_hex=bytes(packet).hex(), frame=frame,
                       rate_hint=rate, pwm16=pwm, decoded_input16=list(commands))
            context['latest'] = row
            raw_stream.write(json.dumps(row, allow_nan=False)+'\n')
            return result
        module.decode_servos = observed
    else:
        decode = module.actuator_commands

        def observed(message):
            commands = decode(message)
            row = dict(protocol='MAVLink_HIL_ACTUATOR_CONTROLS', packet_hex=bytes(message.get_msgbuf()).hex(),
                message=message.to_dict(), decoded_input16=list(commands))
            context['latest'] = row
            raw_stream.write(json.dumps(row, allow_nan=False)+'\n')
            return commands
        module.actuator_commands = observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stack', required=True, choices=('px4', 'arducopter'))
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('--port', required=True, type=int)
    parser.add_argument('--trace', required=True, type=Path)
    parser.add_argument('--raw', required=True, type=Path)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    module = importlib.import_module('Simulator.wksim_core.'+
                                    ('ap_json' if args.stack == 'arducopter' else 'px4_mavlink'))
    context = {}
    def retire(signum, frame):
        raise InterruptedError('Owned PID physics process retired')
    signal.signal(signal.SIGTERM, retire)
    with (args.raw.parent/'physics-actuator-packets.jsonl').open('x', buffering=1) as packets:
        capture_decoder(module, args.stack, context, packets)
        module.Model = observed_model(args.raw, args.raw.parent, args.run_id, config, context)
        extra = {} if args.stack == 'arducopter' else {'speedup': 1}
        try:
            module.serve(args.library, args.port, args.trace, duration=None, **extra)
        except InterruptedError:
            pass


if __name__ == '__main__':
    main()
