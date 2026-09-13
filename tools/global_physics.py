"""Unmodified sensor/actuator coupling with every native 1ms step recorded."""
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
from tools.pid_physics import capture_decoder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('library', 'run-id', 'scene-epoch', 'profile', 'trace'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--stack', choices=('px4', 'arducopter'), required=True)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    directory = Path(args.trace).parent
    profile = json.loads(Path(args.profile).read_text())
    context, stop = {}, dict(requested=False, interval=False)
    def retire(signum, frame):
        stop['requested'] = True
        if not stop['interval']: raise InterruptedError('Owned global physics retired')
    signal.signal(signal.SIGTERM, retire)

    class Observed(Model):
        def __init__(self, library):
            super().__init__(library)
            self.raw = (directory/'physics-1ms.jsonl').open('x', buffering=1024*1024)
            self.raw.write(json.dumps(dict(kind='start', run_id=args.run_id, scene_epoch=args.scene_epoch,
                library_sha256=hashlib.sha256(Path(library).read_bytes()).hexdigest(), initial_tick=0))+'\n')

        def step(self, commands, steps=1):
            for _ in range(steps):
                if stop['requested']: raise InterruptedError('Owned global physics retired')
                stop['interval'] = True
                try:
                    if self.ticks >= profile['maximum_tick']: raise TimeoutError('Global physical tick budget')
                    output = super().step(commands, 1)
                    self.raw.write(json.dumps(dict(kind='step', tick=self.ticks, input16=list(commands),
                        raw_actuator_packet=context.get('latest'), output120=output,
                        observed_monotonic_ns=time.monotonic_ns()), allow_nan=False)+'\n')
                finally:
                    stop['interval'] = False
            if self.ticks % 1000 == 0: self.raw.flush()
            return output

        def close(self):
            if not self.raw.closed:
                self.raw.write(json.dumps(dict(kind='end', ticks=self.ticks))+'\n')
                self.raw.close()
            super().close()

    module = importlib.import_module('Simulator.wksim_core.'+('ap_json' if args.stack == 'arducopter' else 'px4_mavlink'))
    with (directory/'physics-actuator-packets.jsonl').open('x', buffering=1) as packets:
        capture_decoder(module, args.stack, context, packets)
        module.Model = Observed
        extra = {} if args.stack == 'arducopter' else dict(speedup=1)
        try:
            module.serve(Path(args.library), args.port, Path(args.trace), duration=None, **extra)
        except InterruptedError:
            pass


if __name__ == '__main__': main()
