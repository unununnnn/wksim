"""Source/build and input-only checks. Never initialize or step a vehicle model."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('major_builder', ROOT/'tools/build_major_model_recorder.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def rejected(function, *args):
    try:
        function(*args)
    except ValueError:
        return
    raise AssertionError('Expected source refusal')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--archive', type=Path, default=builder.ARCHIVE)
    args = parser.parse_args()
    evidence = Path(tempfile.mkdtemp(prefix='major-recorder-', dir=ROOT/'validation'))
    print(evidence, flush=True)
    report = dict(status='running', model_initialized=False, model_stepped=False, checks=[])
    try:
        source_paths = [ROOT/'tools/build_major_model_recorder.py',
                        ROOT/'tools/major_model_recorder.cpp', Path(__file__)]
        before = {str(path.relative_to(ROOT)): builder.sha256(path.read_bytes()) for path in source_paths}
        for path in source_paths:
            (evidence/path.name).write_bytes(path.read_bytes())
        manifest_raw = args.manifest.read_bytes()
        manifest = json.loads(manifest_raw)
        (evidence/'build.json').write_bytes(manifest_raw)
        executable = Path(manifest['executable'])
        assert manifest['status'] == 'built' and manifest['exit_code'] == 0
        assert manifest['model_executed'] is False
        assert builder.sha256(executable.read_bytes()) == manifest['executable_sha256']
        assert manifest['source']['builder_sha256'] == before['tools/build_major_model_recorder.py']
        assert manifest['source']['driver_sha256'] == before['tools/major_model_recorder.cpp']
        for name in ('build.stdout.log', 'build.stderr.log'):
            (evidence/name).write_bytes((args.manifest.parent/name).read_bytes())
        sources = builder.read_sources(args.archive)
        raw = sources['Exp1_MinModelTemp.cpp']
        instrumented = builder.instrument(raw)
        assert instrumented == (args.manifest.parent/'Exp1_MinModelTemp.cpp').read_bytes()
        assert raw == (args.manifest.parent/'Exp1_MinModelTemp.original.cpp').read_bytes()
        assert instrumented.replace(builder.DECLARATION, b'', 1).replace(builder.HOOK, b'', 1) == raw
        assert instrumented.count(builder.HOOK) == 1
        for member in builder.MEMBERS:
            name = Path(member).name
            assert builder.sha256(sources[name]) == manifest['source']['members_sha256'][member]
            if name != 'Exp1_MinModelTemp.cpp':
                assert sources[name] == (args.manifest.parent/name).read_bytes()
        rejected(builder.instrument, raw + b'\n')
        for malformed in (raw + builder.INCLUDE, raw.replace(builder.NEXT_CONTEXT, b'changed', 1),
                          raw + builder.OUTPUT_END + builder.NEXT_CONTEXT):
            with patch.object(builder, 'CPP_SHA256', builder.sha256(malformed)):
                rejected(builder.instrument, malformed)
        bad_archive = evidence/'unreviewed.zip'
        bad_archive.write_bytes(b'not the pinned archive')
        rejected(builder.read_sources, bad_archive)
        report['checks'].append('exact-five-member hashes, insertion-only reconstruction, SHA/context refusals')

        header = ['k', 'time_s'] + [f'inPWMs{i}' for i in range(16)] + [f'TerrainIn15d{i}' for i in range(15)]
        rows = [[str(k), f'{k / 1000:.3f}'] + ['0.25'] * 16 + ['0'] * 15 for k in range(501)]
        cases = [('valid', rows, '--validate-input', 0),
                 ('missing_row', rows[:-1], '--record', 1),
                 ('extra_row', rows + [rows[-1]], '--record', 1)]
        for name, row, col, value in [('wrong_k', 5, 0, '4'), ('wrong_time', 5, 1, '0.006'),
                ('pwm_high', 0, 2, '1.01'), ('pwm_low', 0, 2, '-0.01'),
                ('pwm_nan', 0, 2, 'nan'), ('terrain_inf', 500, 32, 'inf'),
                ('non_numeric', 0, 3, 'no'), ('empty_field', 0, 4, '')]:
            changed = [list(item) for item in rows]
            changed[row][col] = value
            cases.append((name, changed, '--record', 1))
        changed = [list(item) for item in rows]
        changed[0].pop()
        cases.append(('missing_field', changed, '--record', 1))
        invocations = []

        def invoke(name, command, expected):
            result = subprocess.run(command, capture_output=True, timeout=10)
            (evidence/f'{name}.stdout.log').write_bytes(result.stdout)
            (evidence/f'{name}.stderr.log').write_bytes(result.stderr)
            invocations.append(dict(name=name, argv=command, exit_code=result.returncode))
            assert result.returncode == expected, (name, result.stderr)
            if expected == 0:
                assert json.loads(result.stdout) == dict(status='input_valid', rows=501, model_initialized=False)
                assert result.stderr == b''
            else:
                failure = json.loads(result.stderr)
                assert failure['status'] == 'failed'
                assert failure['attempted_calls'] == failure['returned_calls'] == failure['emitted_samples'] == 0
                assert result.stdout == b''

        for name, data, mode, expected in cases:
            path = evidence/f'{name}.csv'
            path.write_text(','.join(header) + '\n' + '\n'.join(','.join(row) for row in data) + '\n', encoding='ascii')
            invoke(name, [str(executable), mode, str(path)], expected)
            invocations[-1]['input_sha256'] = builder.sha256(path.read_bytes())
        invoke('invalid_arguments', [str(executable)], 1)
        invoke('missing_file', [str(executable), '--record', str(evidence/'absent.csv')], 1)
        (evidence/'invocations.json').write_text(json.dumps(invocations, indent=2) + '\n')
        assert all(builder.sha256((ROOT/name).read_bytes()) == digest for name, digest in before.items())
        assert builder.sha256(executable.read_bytes()) == manifest['executable_sha256']
        report.update(status='pass', checks=report['checks'] + [f'{len(invocations)} input-only/refusal invocations'],
            source_sha256=before, executable_sha256=manifest['executable_sha256'],
            build_manifest_sha256=builder.sha256(manifest_raw), source_unchanged=True)
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        (evidence/'result.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
