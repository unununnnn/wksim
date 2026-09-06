"""Compare actual pinned Prometheus output methods, separating intentional fixes.

Private WSL build only, typed in-memory MAVROS-shaped recorders, no FC/network.
Run as a module from the repository after sourcing its current ROS2 installation.
"""
from dataclasses import asdict
import hashlib
import inspect
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import time
import traceback

from prometheus_control.command import Desired
from prometheus_control.shaping import Setpoint, SetpointShaper, float32
from tools.validate_prometheus_commands import REPO, PIN, SOURCE, build_oracle


def build(work, evidence):
    source_hash = build_oracle(work, evidence)
    source = subprocess.check_output(['git', 'show', f'{PIN}:{SOURCE}'], cwd=REPO).decode()
    fragments = [source[source.index(start):source.index(end)] for start, end in [
        ('void UAV_controller::send_pos_cmd_to_px4_original_controller()', 'void UAV_controller::uav_state_cb('),
        ('void UAV_controller::send_pos_setpoint(', 'void UAV_controller::rotation_yaw(')]]
    (work/'upstream_shaping_methods.inc').write_text('\n'.join(fragments))
    math_path = 'Modules/common/include/math_utils.h'
    math_source = subprocess.check_output(['git', 'show', f'{PIN}:{math_path}'], cwd=REPO)
    if math_source.replace(b'\r\n', b'\n') != (REPO/math_path).read_bytes().replace(b'\r\n', b'\n'):
        raise ValueError('Upstream math source changed')
    (work/'upstream_math_utils.h').write_bytes(math_source)
    shutil.copy2(REPO/'validation/prometheus_shaping_oracle.cpp', work)
    with (work/'CMakeLists.txt').open('a') as cmake:
        cmake.write('\nadd_executable(shaping_oracle prometheus_shaping_oracle.cpp)\n'
                    'target_compile_features(shaping_oracle PRIVATE cxx_std_17)\n'
                    'target_compile_options(shaping_oracle PRIVATE -O2 -fno-fast-math)\n'
                    'target_link_libraries(shaping_oracle Eigen3::Eigen)\n'
                    'ament_target_dependencies(shaping_oracle prometheus_msgs)\n')
    with (evidence/'oracle-build.log').open('a') as log:
        for command in (['cmake', '-S', str(work), '-B', str(work/'build')],
                        ['cmake', '--build', str(work/'build'), '--target', 'shaping_oracle', '--parallel', '4']):
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    return {SOURCE: source_hash, math_path: hashlib.sha256(math_source).hexdigest()}


KINDS = ['position', 'velocity', 'velocity_xy_position_z', 'trajectory', 'acceleration', 'attitude', 'global', 'velocity', 'velocity_xy_position_z']


def row(mode, *, reset=False, state=(10., 20., 3.), velocity=(0., 0., 0.), yaw=.5, difference=None, offset=(0., 0.)):
    return dict(mode=mode, reset=reset, state=tuple(float32(v) for v in state), position=(4., 5., 6.),
                velocity=velocity, acceleration=(.1, .2, .3), attitude=(.1, .2, .3, .5),
                global_position=(47., 8., 3.), yaw=yaw, yaw_rate=.7, difference=difference, offset=offset)


def fixtures():
    rows, rng = [], random.Random(5616)
    # Four ticks: initial output, potential old transition gap, settled output, drift.
    for bits in range(8):
        for sample in range(6):
            velocity = tuple(float32((1.+sample*.2)*(-1 if sample%2 else 1)) if bits & (4 >> axis) else .01*(sample%2) for axis in range(3))
            initial = tuple(float32(rng.uniform(-20., 20.)) for _ in range(3))
            for tick in range(4):
                position = initial if tick<3 else tuple(v+(.02 if sample%2 else .1)*(i+1) for i,v in enumerate(initial))
                rows.append(row(1, reset=tick==0, state=position, velocity=velocity, yaw=.01 if sample%2 else .5,
                                difference='transition_output_gap' if tick==1 and bits else None))
    for bits in range(4):
        for sample in range(6):
            velocity = tuple(float32(1.+sample*.2) if bits & (2 >> axis) else 0. for axis in range(2)) + (0.,)
            for tick in range(2):
                rows.append(row(2, reset=tick==0, state=(10.+tick*.1, 20.+tick*.2, 3.), velocity=velocity, yaw=.01))
    for mode in (0, 3, 4, 5, 6, 7, 8):
        for sample in range(12):
            item = row(mode, reset=True, velocity=tuple(rng.uniform(-2,2) for _ in range(3)), yaw=rng.uniform(-math.pi,math.pi))
            item['attitude'] = tuple(rng.uniform(-math.pi,math.pi) for _ in range(3)) + (rng.random(),)
            rows.append(item)
    rows += [row(1, reset=True, yaw=0.), row(1, yaw=1., difference='transition_output_gap'),
             row(2, reset=True, velocity=(0., 1., 0.)),
             row(2, state=(10.3, 20.4, 3.), velocity=(1., 0., 0.), difference='held_axis_recapture'),
             row(1, reset=True), row(7, state=(11., 21., 3.), velocity=(1., 1., 0.)),
             row(1, state=(13., 24., 3.), difference='rate_history_reset'),
             row(1, reset=True, offset=(1., 2.), difference='offset_normalization')]
    return rows


def decode(line):
    values = [float(v) for v in line.split()[1:]]
    kind = int(values[0])
    if kind == 0:
        return None
    if kind == 1:
        mask, frame = int(values[1]), int(values[2])
        if frame != 1 or mask & 512:
            raise AssertionError('Unexpected original local frame/force flag')
        axes = [tuple(None if mask & (1 << (group*3+i)) else values[3+group*3+i] for i in range(3)) for group in range(3)]
        return asdict(Setpoint('local', position=axes[0], velocity=axes[1], acceleration=axes[2],
                              yaw=None if mask & 1024 else values[12], yaw_rate=None if mask & 2048 else values[13]))
    if kind == 2:
        if int(values[1]) != 7:
            raise AssertionError('Unexpected original attitude mask')
        return asdict(Setpoint('attitude', quaternion_xyzw=tuple(values[2:6]), thrust=values[6]))
    if kind != 3 or values[1:3] != [2552., 6.]:
        raise AssertionError('Unexpected original global mask/frame')
    return asdict(Setpoint('global', global_position=tuple(values[3:6]), yaw=values[6]))


def compare_value(actual, expected):
    if isinstance(actual, dict):
        if actual.keys() != expected.keys():
            raise AssertionError('Output fields differ')
        return max(compare_value(actual[k], expected[k]) for k in actual)
    if isinstance(actual, (tuple, list)):
        if not isinstance(expected, (tuple, list)) or len(actual) != len(expected):
            raise AssertionError('Output dimensions differ')
        return max(compare_value(a,b) for a,b in zip(actual,expected))
    if actual is None or expected is None or isinstance(actual, str):
        if actual != expected:
            raise AssertionError(f'Active fields/kind differ: {actual} vs {expected}')
        return 0.
    # Predeclared output-logic tolerance, NOT a model/dynamics tolerance.
    if not math.isfinite(expected) or not math.isclose(actual, expected, abs_tol=2e-5, rel_tol=1e-6):
        raise AssertionError(f'Output value differs: {actual} vs {expected}')
    return abs(actual-expected)


def compare(work, evidence):
    cases = fixtures()
    encoded = [' '.join(map(str, [int(c['reset']), c['mode'], *c['state'], *c['position'], *c['velocity'],
                *c['acceleration'], *c['attitude'], *c['global_position'], c['yaw'], c['yaw_rate']])) for c in cases]
    data = '\n'.join(encoded) + '\n'
    (evidence/'oracle-input.txt').write_text(data)
    output = subprocess.run([str(work/'build/shaping_oracle')], input=data, text=True, capture_output=True, check=True)
    (evidence/'oracle-output.txt').write_text(output.stdout)
    lines = [line for line in output.stdout.splitlines() if line.startswith('RESULT ')]
    if len(lines) != len(cases):
        raise AssertionError('Oracle row count differs')
    records, differences, maximum = [], {}, 0.
    for number, (case, line) in enumerate(zip(cases, lines)):
        if case['reset']:
            shaper = SetpointShaper()
        reference = Desired(KINDS[case['mode']], position=case['position'], velocity=case['velocity'],
                            acceleration=case['acceleration'], attitude=case['attitude'], global_position=case['global_position'],
                            yaw=case['yaw'] if case['mode']<7 else None,
                            yaw_rate=case['yaw_rate'] if case['mode']>=7 else None)
        position = tuple(v-case['offset'][i] if i<2 else v for i,v in enumerate(case['state']))
        actual = asdict(shaper.shape(reference, position))
        expected = decode(line)
        difference = case['difference']
        if difference:
            differences[difference] = differences.get(difference,0)+1
            if difference == 'transition_output_gap':
                if expected is not None or actual is None:
                    raise AssertionError(f'Expected an old-only output gap at {number}')
            elif difference == 'held_axis_recapture':
                if actual['velocity'][1] != 0. or abs(expected['velocity'][1]) < .1:
                    raise AssertionError('Mixed-mode old anchor error not reproduced')
            elif difference in ('rate_history_reset', 'offset_normalization'):
                if actual['position'] != position or actual['position'] == expected['position']:
                    raise AssertionError(f'Expected corrected local hold at {number}')
            else:
                raise AssertionError('Unspecified expected difference')
            error = None
        else:
            if expected is None:
                raise AssertionError(f'Unexpected old output gap at {number}')
            error = compare_value(actual, expected)
            maximum = max(maximum, error)
        records.append(dict(index=number, input=case, original=expected, migrated=actual, maximum_error=error))
    (evidence/'comparisons.json').write_text(json.dumps(records,indent=2)+'\n')
    return dict(cases=len(cases), equivalent_cases=len(cases)-sum(differences.values()),
                intentional_differences=differences, maximum_absolute_error=maximum,
                absolute_tolerance=2e-5, relative_tolerance=1e-6)


def main():
    work = Path(tempfile.mkdtemp(prefix='wksim-shaping-', dir='/root'))
    evidence = Path(tempfile.mkdtemp(prefix='prometheus-shaping-', dir=REPO/'validation'))
    print(f'Workspace: {work}\nEvidence: {evidence}', flush=True)
    report = dict(status='failed', upstream=PIN, workspace=str(work), observed_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    try:
        installed = Path(inspect.getfile(SetpointShaper)).resolve()
        source = REPO/'ros2/src/prometheus_control/prometheus_control/shaping.py'
        if installed == source.resolve() or installed.read_bytes() != source.read_bytes():
            raise ValueError('Run a fresh install identical to repository shaping.py')
        files = [source, REPO/'validation/test_prometheus_control.py',
                 REPO/'validation/prometheus_shaping_oracle.cpp', Path(__file__)]
        report['installed_module'] = str(installed)
        report['source_sha256'] = {str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        report['upstream_sha256'] = build(work, evidence)
        report.update(compare(work, evidence))
        report['status'] = 'pass'
    except Exception:
        report['error'] = traceback.format_exc()
    report['artifacts'] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(evidence.iterdir()) if p.is_file()}
    (evidence/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
