"""Consume only newly notified current-authority depth frames; export ENU cloud and mask."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Simulator.ue55.depth import Reader


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    for key in ('run-id', 'instance-id', 'epoch'):
        p.add_argument('--'+key, required=True)
    p.add_argument('--generation', type=int, required=True)
    p.add_argument('--minimum-step', type=int, required=True)
    p.add_argument('--seconds', type=float, default=30)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if not 0 < a.seconds <= 300:
        p.error('seconds must be in (0,300]')
    value = json.loads(a.config.read_text(encoding='utf-8-sig'))
    directory, stream = value.pop('output_directory'), value.pop('stream_id')
    a.output.mkdir(parents=True, exist_ok=False)
    reader = Reader(directory, a.run_id, a.instance_id, value, stream_id=stream)
    frames = []
    try:
        reader.set_epoch(a.epoch, a.generation, minimum_step=a.minimum_step)
        end = time.monotonic()+a.seconds
        while time.monotonic() < end:
            for frame in reader.poll():
                stem = Path(frame['metadata_path']).stem
                (a.output/(stem+'.cloud.json')).write_text(json.dumps(frame.pop('point_cloud'), allow_nan=False)+'\n')
                (a.output/(stem+'.mask.u8')).write_bytes(frame.pop('valid_mask'))
                frame.pop('depths')
                frames.append(frame)
            time.sleep(.01)
    finally:
        reader.close()
    report = dict(status='captured' if frames else 'no_frames', frames=frames, rejected=reader.rejected,
                  authority_binding=dict(epoch=a.epoch, generation=a.generation, minimum_step=a.minimum_step),
                  physical_progress_verified=False)
    (a.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(frames=len(frames), rejected=reader.rejected)))
    return 0 if frames else 1


if __name__ == '__main__':
    raise SystemExit(main())
