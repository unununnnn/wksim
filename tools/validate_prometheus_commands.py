"""Differential-test migrated references against compiled original Prometheus C++.

Generated oracle fragments/build files go only to a new private WSL directory.
No ROS node, flight controller, MATLAB or scene is started by this test.
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

from prometheus_control.command import CommandProcessor
from prometheus_msgs.msg import UAVCommand as Cmd, UAVControlState as Control
from validation.test_prometheus_control import processor, state, move

REPO = Path(__file__).resolve().parent.parent
PIN = '5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce'
SOURCE = 'Modules/uav_control/src/uav_controller.cpp'


def source_integrity():
    installed = Path(inspect.getfile(CommandProcessor)).resolve()
    source = REPO/'ros2/src/prometheus_control/prometheus_control/command.py'
    if installed == source.resolve() or installed.read_bytes() != source.read_bytes():
        raise ValueError('Test must use an installed command module identical to repository source')
    files = [source, REPO/'validation/test_prometheus_control.py',
             REPO/'validation/prometheus_command_oracle.cpp',
             REPO/'validation/command-oracle-CMakeLists.txt', Path(__file__)]
    return dict(installed_module=str(installed),
                sha256={str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files})


def build_oracle(work, evidence):
    original = subprocess.check_output(['git', 'show', f'{PIN}:{SOURCE}'], cwd=REPO)
    current = (REPO/SOURCE).read_bytes()
    if original.replace(b'\r\n', b'\n') != current.replace(b'\r\n', b'\n'):
        raise ValueError('Upstream control source differs from the pinned commit')
    source = original.decode()
    methods = []
    for start, end in [('void UAV_controller::set_command_des()', 'void UAV_controller::set_command_des_for_pos_controller()'),
                       ('void UAV_controller::uav_cmd_cb(', 'void UAV_controller::send_pos_cmd_to_px4_original_controller()'),
                       ('void UAV_controller::rotation_yaw(', 'void UAV_controller::printf_control_state()')]:
        methods.append(source[source.index(start):source.index(end)])
    (work/'upstream_command_methods.inc').write_text('\n'.join(methods))
    manifest = json.loads((REPO/'ros2/src/prometheus_msgs/UPSTREAM.json').read_text())
    aliases = next(i['changes'] for i in manifest['interfaces'] if i['file'] == 'msg/UAVCommand.msg')
    (work/'upstream_command_aliases.inc').write_text('#define ConstPtr ConstSharedPtr\n' + '\n'.join(
        f'#define {c["source_name"]} {c["target_name"]}' for c in aliases if c['source_name'] != c['target_name']) + '\n')
    shutil.copy2(REPO/'validation/prometheus_command_oracle.cpp', work)
    shutil.copy2(REPO/'validation/command-oracle-CMakeLists.txt', work/'CMakeLists.txt')
    with (evidence/'oracle-build.log').open('w') as log:
        for command in (['cmake', '-S', str(work), '-B', str(work/'build')],
                        ['cmake', '--build', str(work/'build'), '--parallel', '4']):
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    return hashlib.sha256(original).hexdigest()


def fixtures():
    rows, randomizer = [], random.Random(5605)
    for mode in range(Cmd.XYZ_POS, Cmd.LAT_LON_ALT + 1):
        for number in range(1, 9):
            position = tuple(randomizer.uniform(-30, 30) for _ in range(2)) + (randomizer.uniform(2, 8),)
            yaw = randomizer.uniform(-math.pi, math.pi)
            command = move(mode, number=number,
                           position_ref=[randomizer.uniform(-3, 3) for _ in range(3)],
                           velocity_ref=[randomizer.uniform(-2, 2) for _ in range(3)],
                           acceleration_ref=[randomizer.uniform(-1, 1) for _ in range(3)],
                           yaw_ref=.25, att_ref=[.1, .2, .3, .5], latitude=47., longitude=8., altitude=3.)
            rows.append((True, position, yaw, command))
            if mode in CommandProcessor.BODY:
                rows.append((False, (position[0]+2, position[1]+3, position[2]+1), yaw+.2, command))
    for number, command in enumerate([
            Cmd(agent_cmd=Cmd.INIT_POS_HOVER),
            Cmd(agent_cmd=Cmd.CURRENT_POS_HOVER, control_level=Cmd.ABSOLUTE_CONTROL),
            move(position_ref=[4., 6., 3.]),
            Cmd(agent_cmd=Cmd.CURRENT_POS_HOVER, control_level=Cmd.ABSOLUTE_CONTROL),
            move(control_level=Cmd.EXIT_ABSOLUTE_CONTROL, position_ref=[4., 6., 3.]),
            Cmd(agent_cmd=Cmd.LAND)]):
        rows.append((number == 0, (10.+number, 20., 2.), .5, command))
    return rows


def compare(work, evidence):
    rows = fixtures()
    encoded = []
    for reset, position, yaw, command in rows:
        values = [int(reset), command.agent_cmd, command.control_level, command.move_mode, command.command_id,
                  *position, yaw, *command.position_ref, *command.velocity_ref, *command.acceleration_ref,
                  command.yaw_ref, int(command.yaw_rate_mode), command.yaw_rate_ref, *command.att_ref,
                  command.latitude, command.longitude, command.altitude]
        encoded.append(' '.join(str(v) for v in values))
    data = '\n'.join(encoded) + '\n'
    (evidence/'oracle-input.txt').write_text(data)
    run = subprocess.run([str(work/'build/command_oracle')], input=data, capture_output=True, text=True, check=True)
    (evidence/'oracle-output.txt').write_text(run.stdout)
    results = [[float(v) for v in line.split()[1:]] for line in run.stdout.splitlines() if line.startswith('RESULT ')]
    if len(results) != len(rows):
        raise AssertionError(f'Expected {len(rows)} rows, got {len(results)}')
    max_error, checks = 0.0, []
    for index, ((reset, position, yaw, command), expected) in enumerate(zip(rows, results)):
        if reset:
            obj = processor(takeoff_height=3., enable_external_control=True)
        obj.update_state(state(position=position, yaw=yaw))
        accepted = obj.accept(command)
        desired = obj.step()
        if obj.control_state != int(expected[0]):
            raise AssertionError(f'Control state differs at {index}')
        stop = -1 if accepted.stop_control is None else int(accepted.stop_control)
        if stop != int(expected[1]):
            raise AssertionError(f'Priority stop/resume differs at {index}')
        pairs = [(desired.position, expected[2:5]), (desired.velocity, expected[5:8]),
                 (desired.acceleration, expected[8:11]),
                 ((desired.yaw,) if desired.yaw is not None else None, expected[11:12]),
                 ((desired.yaw_rate,) if desired.yaw_rate is not None else None, expected[12:13]),
                 (desired.attitude, expected[13:17]), (desired.global_position, expected[17:20])]
        error = 0.0
        for actual, reference in pairs:
            if actual is None:
                continue
            for a, b in zip(actual, reference):
                error = max(error, abs(a-b))
                # Declared before running: source assigns body intermediates to float32.
                if not math.isclose(a, b, abs_tol=2e-5, rel_tol=1e-6):
                    raise AssertionError(f'Reference differs at {index}: {actual} != {reference}')
        max_error = max(max_error, error)
        checks.append(dict(index=index, agent=command.agent_cmd, mode=command.move_mode, accepted=asdict(accepted),
                           desired=asdict(desired), maximum_absolute_error=error))
    (evidence/'comparisons.json').write_text(json.dumps(checks, indent=2) + '\n')
    return dict(cases=len(rows), maximum_absolute_error=max_error, absolute_tolerance=2e-5, relative_tolerance=1e-6)


def main():
    work = Path(tempfile.mkdtemp(prefix='wksim-command-', dir='/root'))
    evidence = Path(tempfile.mkdtemp(prefix='prometheus-command-', dir=REPO/'validation'))
    print(f'Workspace: {work}\nEvidence: {evidence}', flush=True)
    report = dict(status='failed', source=SOURCE, upstream=PIN, workspace=str(work),
                  observed_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    try:
        report['source_integrity'] = source_integrity()
        report['upstream_sha256'] = build_oracle(work, evidence)
        report.update(compare(work, evidence))
        report['status'] = 'pass'
    except Exception:
        report['error'] = traceback.format_exc()
    report['artifacts'] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(evidence.iterdir()) if p.is_file()}
    (evidence/'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
