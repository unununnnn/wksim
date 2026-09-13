"""Independent ray/box oracle for the existing native visual fixture, not dynamics evidence."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Simulator.ue55.depth import rotate

# Frozen 2026-09-08 before any depth rendering run; optical-only budgets.
EDGE_PIXELS = 2
ABS_METERS = .01
RELATIVE = .002
COVERAGE = .995


def ray_box(origin, direction, obj):
    q = obj['quaternion_xyzw']; inverse = [-q[0], -q[1], -q[2], q[3]]
    o = rotate(inverse, [origin[i]-obj['position_cm'][i] for i in range(3)])
    d = rotate(inverse, direction)
    lo, hi = 0., float('inf')
    for i in range(3):
        lower = obj['mesh_bounds_min'][i]*obj['scale'][i]
        upper = obj['mesh_bounds_max'][i]*obj['scale'][i]
        if abs(d[i]) < 1e-12:
            if not lower <= o[i] <= upper:
                return float('inf')
        else:
            a, b = sorted(((lower-o[i])/d[i], (upper-o[i])/d[i]))
            lo, hi = max(lo, a), min(hi, b)
            if hi < lo:
                return float('inf')
    return lo if lo > 0 else float('inf')


def expected(metadata, fixture):
    w, h, k = metadata['width'], metadata['height'], metadata['K']
    p = metadata['camera_world_pose']; result = []
    for v in range(h):
        for u in range(w):
            direction = rotate(p['quaternion_xyzw'], [1, (u+.5-k[2])/k[0], -(v+.5-k[5])/k[4]])
            hits = [(ray_box(p['position_cm'], direction, o)/100, o['name'])
                    for o in fixture['objects'] if o['visible']]
            distance, name = min(hits, default=(float('inf'), 'invalid'))
            result.append((distance, name) if distance < metadata['max_depth_meters'] else (float('nan'), 'invalid'))
    return result


def compare(metadata, depths, fixture):
    w, h = metadata['width'], metadata['height']
    if len(depths) != w*h:
        raise ValueError('Depth dimensions differ')
    wanted = expected(metadata, fixture)
    valid = invalid = good = good_invalid = 0
    maximum_error = 0.
    for v in range(EDGE_PIXELS, h-EDGE_PIXELS):
        for u in range(EDGE_PIXELS, w-EDGE_PIXELS):
            i = v*w+u; distance, name = wanted[i]
            if any(wanted[(v+dv)*w+u+du][1] != name
                   for dv in range(-EDGE_PIXELS, EDGE_PIXELS+1) for du in range(-EDGE_PIXELS, EDGE_PIXELS+1)):
                continue
            actual = depths[i]
            if name == 'invalid':
                invalid += 1; good_invalid += math.isnan(actual)
            else:
                valid += 1
                error = abs(actual-distance) if math.isfinite(actual) else float('inf')
                maximum_error = max(maximum_error, error)
                good += error <= max(ABS_METERS, RELATIVE*distance)
    if valid < 100 or invalid < 100 or good/valid < COVERAGE or good_invalid/invalid < COVERAGE:
        raise ValueError(f'Depth geometry failed: valid {good}/{valid}, invalid {good_invalid}/{invalid}, max_error={maximum_error}')
    return dict(valid_interior=valid, invalid_interior=invalid, distance_coverage=good/valid,
                invalid_coverage=good_invalid/invalid, maximum_error_m=maximum_error)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--fixture', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    try:
        report = json.loads(a.report.read_text()); fixture = json.loads(a.fixture.read_text())
        if fixture['schema'] != 'wksim.rgb-calibration-visual.v1' or fixture['physics_authority'] is not False:
            raise ValueError('Expected native visual-only fixture')
        frames = []
        for frame in report['frames']:
            meta_path = Path(frame['metadata_path']); data_path = Path(frame['image_path'])
            metadata = json.loads(meta_path.read_text())
            if metadata != frame['metadata'] or metadata['schema'] != 'wksim.depth.v1':
                raise ValueError('Captured metadata changed')
            raw = data_path.read_bytes()
            frames.append(dict(step=metadata['step'], sha256=hashlib.sha256(raw).hexdigest(),
                               result=compare(metadata, [v[0] for v in struct.iter_unpack('<f', raw)], fixture)))
        if len(frames) < 3:
            raise ValueError('At least three real frames required')
        result = dict(status='pass', optical_geometry_only=True, frames=frames,
                      thresholds=dict(edge_pixels=EDGE_PIXELS, absolute_m=ABS_METERS, relative=RELATIVE, coverage=COVERAGE))
    except (OSError, ValueError, KeyError, TypeError, struct.error) as e:
        result = dict(status='failed', error=repr(e))
    a.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(status=result['status'])))
    return result['status'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
