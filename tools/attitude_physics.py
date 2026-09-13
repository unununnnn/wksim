"""Experimental per-ms observer around the unchanged independent physics adapters.

The original n-step call is split into n calls with the same held input. Each
call still uses the pinned native wrapper and its fixed 1 ms integrator. This is
an explicit experimental observer, not a change to the production loader.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import signal
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_core.model import Model


def observed_model(path):
    class ObservedModel(Model):
        def __init__(self, library):
            super().__init__(library)
            self.raw = Path(path).open('x', buffering=1024*1024)
            self.raw.write(json.dumps(dict(kind='start', library=str(library),
                library_sha256=hashlib.sha256(Path(library).read_bytes()).hexdigest(),
                observer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                schema='wksim.attitude.physics.v1', initial_tick=0, dt_s=.001))+'\n')
            self.groups = 0

        def step(self, commands, steps=1):
            if type(steps) is not int or not 1 <= steps <= 1000:
                raise ValueError('steps must be an integer in [1,1000]')
            self.groups += 1
            for substep in range(steps):
                output = super().step(commands, 1)
                self.raw.write(json.dumps(dict(kind='step', tick=self.ticks,
                    group=self.groups, group_steps=steps, substep=substep,
                    input16=list(commands), output120=output,
                    observed_monotonic_ns=time.monotonic_ns()), allow_nan=False)+'\n')
            if self.ticks % 1000 == 0:
                self.raw.flush()
            return output

        def close(self):
            if not self.raw.closed:
                self.raw.write(json.dumps(dict(kind='end', ticks=self.ticks, groups=self.groups))+'\n')
                self.raw.close()
            super().close()
    return ObservedModel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stack', required=True, choices=('px4','arducopter'))
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('--port', required=True, type=int)
    parser.add_argument('--trace', required=True, type=Path)
    parser.add_argument('--raw', required=True, type=Path)
    args = parser.parse_args()
    module = importlib.import_module('Simulator.wksim_core.'+
                                    ('ap_json' if args.stack=='arducopter' else 'px4_mavlink'))
    # Deliberate process-local dependency substitution, sealed in the run sources.
    # Packet parsing, lockstep, held inputs and all sensor routing remain original.
    module.Model = observed_model(args.raw)
    extra = {} if args.stack=='arducopter' else {'speedup':1}
    def retire(signum, frame):
        raise InterruptedError('Owned physics process retired')
    signal.signal(signal.SIGTERM, retire)
    try:
        module.serve(args.library, args.port, args.trace, duration=None, **extra)
    except InterruptedError:
        pass


if __name__ == '__main__':
    main()
