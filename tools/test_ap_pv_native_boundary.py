"""Compile exact candidate function slices with explicit dependency stubs; no SITL."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, default=Path('/root/wksim-ap-pv-vn04950x'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    output = args.output or Path(tempfile.mkdtemp(prefix='ap-pv-boundary-', dir=repo / 'validation'))
    output.mkdir(parents=True, exist_ok=True)
    manifest_raw = (args.candidate / 'pv-source.json').read_bytes()
    manifest = json.loads(manifest_raw)
    sources = {}
    records = {}
    names = ['libraries/AP_DDS/AP_DDS_ExternalControl.cpp',
             'ArduCopter/AP_ExternalControl_Copter.cpp',
             'libraries/AP_DDS/Idl/ardupilot_msgs/msg/GlobalPosition.idl']
    for name in names:
        raw = (args.candidate / 'src' / name).read_bytes()
        assert sha(raw) == manifest['source']['files'][name]['sha256'], name
        sources[name] = raw.decode()
        records[name] = sha(raw)
        target = output / 'sources' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    # Slice by top-level function delimiters. Function bodies are copied verbatim,
    # including all validation and forwarding; no policy expression is rewritten.
    requested = {
        names[0]: ['AP_DDS_External_Control::handle_global_position_control',
                   'AP_DDS_External_Control::convert_alt_frame'],
        names[1]: ['AP_ExternalControl_Copter::set_global_position_velocity_and_yaw',
                   'AP_ExternalControl_Copter::ready_for_external_control'],
    }
    slices = []
    for name, symbols in requested.items():
        for symbol in symbols:
            text = sources[name]
            start = text.index('bool ' + symbol + '(')
            end = text.index('\n}', start) + 2
            body = text[start:end]
            slices.append(body)
            records[symbol] = {'sha256': sha(body.encode()), 'source': name,
                               'line': text[:start].count('\n') + 1}
    constants = re.findall(r'const uint(?:8|16) (\w+) = (\d+);', sources[names[2]])
    (output / 'constants.inc').write_text('struct GlobalPosition {\n' + '\n'.join(
        f'static constexpr uint16_t {name} = {value};' for name, value in constants) + '\n};\n')
    (output / 'actual.inc').write_text('\n\n'.join(slices) + '\n')
    support = repo / 'tools/ap_pv_native_boundary.cpp'
    (output / support.name).write_bytes(support.read_bytes())
    records['support_sha256'] = sha(support.read_bytes())
    records['runner_sha256'] = sha(Path(__file__).read_bytes())
    records['pv_source_manifest_sha256'] = sha(manifest_raw)
    records['candidate'] = str(args.candidate)
    records['scope'] = 'exact function slices; dependency stubs; not firmware/SITL acceptance'
    commands = []
    try:
        for command in [['g++', '--version'], ['g++', '-std=c++17', '-O1', '-g',
                        '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined,float-cast-overflow',
                        '-fno-sanitize-recover=all', str(output / support.name), '-o', str(output / 'boundary')],
                        [str(output / 'boundary')]]:
            result = subprocess.run(command, capture_output=True, text=True)
            commands.append(dict(command=command, returncode=result.returncode,
                                 stdout=result.stdout, stderr=result.stderr))
            if result.returncode:
                raise RuntimeError(result.stderr or result.stdout)
        assert all(sha((args.candidate / 'src' / name).read_bytes()) == records[name] for name in names)
        records['source_unchanged_after'] = True
        records['result'] = 'PASS'
        print(commands[-1]['stdout'].strip())
        print('evidence=' + str(output))
    finally:
        (output / 'evidence.json').write_text(json.dumps(dict(records=records, commands=commands), indent=2))


if __name__ == '__main__':
    main()
