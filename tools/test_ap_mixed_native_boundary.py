"""Host-only exact sealed AP mixed DDS/helper slices with explicit dependency stubs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from unittest.mock import patch


BUILD_SHA256 = '1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c'
PROFILE = 'xy_velocity_z_position_yaw_v1'
NAMES = ['libraries/AP_DDS/AP_DDS_ExternalControl.cpp',
         'ArduCopter/AP_ExternalControl_Copter.cpp',
         'libraries/AP_DDS/Idl/ardupilot_msgs/msg/GlobalPosition.idl',
         'libraries/AP_DDS/Idl/geometry_msgs/msg/Twist.idl',
         'libraries/AP_DDS/Idl/geometry_msgs/msg/Vector3.idl',
         'libraries/AP_Common/Location.h',
         'libraries/AP_AHRS/AP_AHRS.h',
         'libraries/AP_ExternalControl/AP_ExternalControl.h',
         'ArduCopter/AP_ExternalControl_Copter.h']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_candidate(candidate, expected_build_sha256):
    build_raw = (candidate / 'mixed-build.json').read_bytes()
    require(sha(build_raw) == expected_build_sha256, 'mixed-build.json SHA256 mismatch')
    build = json.loads(build_raw)
    require(build['profile'] == PROFILE and build['status'] == 'built-not-admitted', 'wrong profile/status')
    require(build['candidate_root'] == str(candidate), 'wrong candidate root')
    require(build['source_unchanged_during_build'] is True, 'source changed during build')
    source_raw = (candidate / 'mixed-source.json').read_bytes()
    require(sha(source_raw) == build['source_manifest_sha256'], 'mixed-source.json SHA256 mismatch')
    manifest = json.loads(source_raw)
    require(manifest['profile'] == PROFILE and manifest['candidate_root'] == str(candidate), 'wrong source identity')
    require(manifest['patch_sha256'] == build['patch_sha256'], 'wrong patch identity')
    sources = {}
    for name in NAMES:
        raw = (candidate / 'src' / name).read_bytes()
        require(sha(raw) == manifest['source']['files'][name]['sha256'], f'source SHA256 mismatch: {name}')
        sources[name] = raw
    return build_raw, source_raw, sources


def check_rejections(candidate, expected_build_sha256):
    """Alter read results in memory: never modify the sealed candidate or call g++."""
    read_bytes = Path.read_bytes
    cases = [('wrong expected build hash', None, '0' * 64),
             ('changed build manifest', candidate / 'mixed-build.json', expected_build_sha256),
             ('changed source manifest', candidate / 'mixed-source.json', expected_build_sha256)]
    cases += [('changed actual source: ' + name, candidate / 'src' / name, expected_build_sha256) for name in NAMES]
    checked = []
    for label, changed_path, expected in cases:
        def changed_read(path):
            raw = read_bytes(path)
            return raw + b'\n' if path == changed_path else raw
        with patch.object(Path, 'read_bytes', changed_read):
            try:
                verify_candidate(candidate, expected)
            except ValueError as exc:
                checked.append({'case': label, 'result': 'rejected-before-compile', 'reason': str(exc)})
            else:
                raise AssertionError('identity checker accepted ' + label)
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True, help='explicit sealed mixed candidate root')
    parser.add_argument('--expected-build-sha256', default=BUILD_SHA256)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    parent = repo / 'validation/ap-mixed-20260909'
    parent.mkdir(parents=True, exist_ok=True)
    output = args.output or Path(tempfile.mkdtemp(prefix='native-boundary-', dir=parent))
    output.mkdir(parents=True, exist_ok=True)
    records = {'candidate': str(args.candidate), 'profile': PROFILE, 'result': 'FAIL',
               'scope': 'Exact DDS and Copter helper function slices; explicit dependency stubs; no firmware/controller/fence/Location/reset/timeout/flight execution'}
    commands = []
    try:
        build_raw, source_raw, sources = verify_candidate(args.candidate, args.expected_build_sha256)
        records['identity_negative_checks'] = check_rejections(args.candidate, args.expected_build_sha256)
        records['build_manifest_sha256'] = sha(build_raw)
        records['source_manifest_sha256'] = sha(source_raw)
        records['stub_provenance'] = {
            'DDS scalar types and constants': NAMES[2:5],
            'Location enum and method signatures': NAMES[5],
            'AHRS method signatures': NAMES[6],
            'external interface signatures': NAMES[7:9],
            'behavior': 'AHRS/Location outputs and downstream refusal are scripted. Vector storage, math, DDS C++ representation, Guided state and fence are not native AP execution.'}
        requested = {
            NAMES[0]: ['AP_DDS_External_Control::handle_global_position_control',
                       'AP_DDS_External_Control::convert_alt_frame'],
            NAMES[1]: ['AP_ExternalControl_Copter::set_global_position_velocity_and_yaw',
                       'AP_ExternalControl_Copter::set_altitude_velocity_xy_and_yaw',
                       'AP_ExternalControl_Copter::ready_for_external_control'],
        }
        slices = []
        for name, raw in sources.items():
            records[name] = sha(raw)
            target = output / 'sources' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            source = raw.decode()
            for symbol in requested.get(name, []):
                require(source.count('bool ' + symbol + '(') == 1, 'nonunique function: ' + symbol)
                start = source.index('bool ' + symbol + '(')
                end = source.index('\n}', start) + 2
                body = source[start:end]
                require(body.count('{') == body.count('}'), 'unbalanced function: ' + symbol)
                slices.append(body)
                records[symbol] = {'source': name, 'line': source[:start].count('\n') + 1,
                                   'sha256': sha(body.encode())}
        constants = re.findall(r'const uint(?:8|16) (\w+) = (\d+);', sources[NAMES[2]].decode())
        require(len(constants) == 15, 'unexpected IDL constants')
        (output / 'constants.inc').write_text('struct GlobalPosition {\n' + '\n'.join(
            f'static constexpr uint16_t {name} = {value};' for name, value in constants) + '\n};\n')
        (output / 'actual.inc').write_text('\n\n'.join(slices) + '\n')
        support = repo / 'tools/ap_mixed_native_boundary.cpp'
        (output / support.name).write_bytes(support.read_bytes())
        records['support_sha256'] = sha(support.read_bytes())
        records['runner_sha256'] = sha(Path(__file__).read_bytes())
        for command in [['g++', '--version'], ['g++', '-std=c++17', '-O1', '-g',
                        '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined,float-cast-overflow',
                        '-fno-sanitize-recover=all', str(output / support.name), '-o', str(output / 'boundary')],
                        [str(output / 'boundary')]]:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            commands.append(dict(command=command, returncode=result.returncode,
                                 stdout=result.stdout, stderr=result.stderr))
            require(result.returncode == 0, result.stderr or result.stdout)
        require(verify_candidate(args.candidate, args.expected_build_sha256) == (build_raw, source_raw, sources), 'source changed after test')
        records['source_unchanged_after'] = True
        records['result'] = 'PASS'
        print(commands[-1]['stdout'].strip())
        print('identity_negative_checks=' + str(len(records['identity_negative_checks'])))
        print('evidence=' + str(output))
    finally:
        (output / 'evidence.json').write_text(json.dumps(dict(records=records, commands=commands), indent=2))


if __name__ == '__main__':
    main()
