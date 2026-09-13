"""#114 regression and optional real native fixture (not #115 source acceptance).

python -m unittest validation.test_model_reexecution -v
Linux: WKSIM_REEXECUTION_NATIVE=/root/NEW python -m unittest ... -v
Native fixture creates a new build, runs a separate source process, seals only
after its exit, then calls the actual import/run/audit CLI in fresh processes.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import reexecute_model as r
from wksim_core.model_parameters import make_config, build_configured_model


def encoded(value):
    return (json.dumps(value, allow_nan=False) + '\n').encode()


def seal(root, config, outputs, build, process, build_receipt=b'{}\n', plan_bytes=None):
    """New test-source package; never upgrades old or partial recorded sources."""
    n = len(outputs)
    commands = [.55, .55, .55, .55] + [0.] * 12
    common = {'scene_epoch': 'native-fixture-epoch', 'instance_id': 'quad-0'}
    inputs = [dict(common, tick=t, before_ns=(t-1)*r.DT, after_ns=t*r.DT,
                   inPWMs=commands, TerrainIn15d=[0.]*15, source_ref='plan.json', event_frontier=0)
              for t in range(1, n+1)]
    expected = [dict(common, tick=t, output_phase='post_step_api', output120=v)
                for t, v in enumerate(outputs, 1)]
    data = {'config.json': encoded(config), 'events.jsonl': b'',
            'inputs.jsonl': b''.join(map(encoded, inputs)),
            'expected.jsonl': b''.join(map(encoded, expected)),
            'plan.json': encoded(dict(kind='static_experiment_plan', first_tick=1, last_tick=n,
                            inPWMs=commands, TerrainIn15d=[0.]*15, frozen_before_capture=True))}
    data['build.json'] = build_receipt
    if plan_bytes is not None:
        data['plan.json'] = plan_bytes
    members = {name: r.descriptor(value, name) for name, value in data.items()}
    terminal = dict(source_status='complete', exit_code=0, attempted=n, returned=n,
                    emitted=n, last_tick=n, engine_end_ns=n*r.DT, event_frontier=0,
                    streams={k: members[k] for k in ('inputs.jsonl', 'expected.jsonl', 'events.jsonl')},
                    process=process, last_confirmed_tick=n)
    data['terminal.json'] = encoded(terminal)
    members['terminal.json'] = r.descriptor(data['terminal.json'], 'terminal.json')
    manifest = dict(schema=r.SCHEMA, profile=r.PROFILE, source_run_id='native-static-test-source',
        source_capture_revision='test_model_reexecution-v1', **common, contract_sha256=r.CONTRACT,
        config_identity=config['model_identity'], build_identity=build,
        initialization=r.initialization(config), randomness=r.randomness(),
        time=dict(first_tick=1, last_tick=n, dt_ns=r.DT), input_encoding='per_tick_binary64',
        output_phase='post_step_api', event_policy={'mode': 'explicit_none', 'count': 0}, members=members)
    data['manifest.json'] = encoded(manifest)
    root.mkdir()
    for name, raw in data.items():
        (root/name).write_bytes(raw)
    return root


def rewrite(root, name, value):
    data = value if isinstance(value, bytes) else encoded(value)
    (root/name).write_bytes(data)
    if name != 'manifest.json':
        m = r.decode((root/'manifest.json').read_bytes())
        # Mutations rehash their envelope, to reach semantic validation.
        try:
            m['members'][name] = r.descriptor(data, name)
        except ValueError:
            m['members'][name]['sha256'] = r.sha(data)
            m['members'][name]['bytes'] = len(data)
        (root/'manifest.json').write_bytes(encoded(m))


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        outputs = [[0.]*120 for _ in range(3)]
        for tick, v in enumerate(outputs, 1):
            v[2] = tick*.001
        files = {name: 'a'*64 for name in r.BUILD_FILES}
        files.update({'archive.zip': r.SOURCE['archive_sha256'], 'build.json': r.sha(b'{}\n'),
                      'Exp1_MinModelTemp.original.cpp': r.RAW_HASHES['Exp1_MinModelTemp.cpp']})
        self.root = seal(self.base/'source', make_config(), outputs,
            {'source': r.SOURCE, 'files': files,
             'dependencies': {'/lib/test.so': 'b'*64}, 'platform':
             dict(system='test', machine='test', cpu=[], libc=[], python='test', ctypes_bits=64, rounding=0, compiler='test')},
            dict(pid=99999999, boot_id='test-only', starttime=1, argv=['synthetic-parser-fixture'], exited=True))

    def change_manifest(self, change):
        m = r.decode((self.root/'manifest.json').read_bytes())
        change(m)
        rewrite(self.root, 'manifest.json', m)

    def change_rows(self, name, change):
        values = r.rows((self.root/name).read_bytes())
        change(values)
        rewrite(self.root, name, b''.join(map(encoded, values)))

    def rejected(self, pattern):
        # A malformed bundle must be rejected before even build inspection,
        # and therefore before any CDLL, create, FC or transport operation.
        with patch.object(r, 'build_identity') as build, patch.object(r, 'ConfiguredModel') as model:
            result, code = r.run_bundle(self.root, self.base/'unused.so', self.base/'run')
        self.assertEqual(code, 2)
        self.assertRegex(result['reason'], pattern)
        build.assert_not_called()
        model.assert_not_called()
        self.assertTrue((self.base/'run/failure.json').exists())

    def test_complete_parser_fixture_import_only(self):
        result = r.import_bundle(self.root, self.base/'imported')
        self.assertEqual(result['status'], 'imported')
        self.assertNotIn('reexecution_passed', json.dumps(result))
        for path in self.root.iterdir():
            self.assertEqual(path.read_bytes(), (self.base/'imported'/path.name).read_bytes())

    def test_missing_tick(self):
        self.change_rows('inputs.jsonl', lambda x: x.pop(1))
        self.rejected('missing interval')

    def test_duplicate_tick(self):
        self.change_rows('inputs.jsonl', lambda x: x[1].update(tick=1))
        self.rejected('duplicate')

    def test_reordered_tick(self):
        self.change_rows('inputs.jsonl', lambda x: x.reverse())
        self.rejected('ordered interval')

    def test_changed_input(self):
        self.change_rows('inputs.jsonl', lambda x: x[0]['inPWMs'].__setitem__(0, .6))
        self.rejected('plan mapping')

    def test_nonzero_terrain(self):
        self.change_rows('inputs.jsonl', lambda x: x[0]['TerrainIn15d'].__setitem__(0, .1))
        self.rejected('terrain')

    def test_unused_actuator(self):
        self.change_rows('inputs.jsonl', lambda x: x[0]['inPWMs'].__setitem__(4, .1))
        self.rejected('actuator')

    def test_bool_number(self):
        self.change_rows('inputs.jsonl', lambda x: x[0]['inPWMs'].__setitem__(0, True))
        self.rejected('non-number')

    def test_bool_tick(self):
        self.change_rows('inputs.jsonl', lambda x: x[0].update(tick=True))
        self.rejected('interval')

    def test_millisecond_grid(self):
        self.change_rows('inputs.jsonl', lambda x: x[0].update(after_ns=1000001))
        self.rejected('1ms')

    def test_cross_generation(self):
        self.change_rows('inputs.jsonl', lambda x: x[0].update(scene_epoch='old'))
        self.rejected('cross-generation')

    def test_missing_reference(self):
        self.change_rows('inputs.jsonl', lambda x: x[0].update(source_ref='absent.json'))
        self.rejected('source_ref')

    def test_event_frontier(self):
        self.change_rows('inputs.jsonl', lambda x: x[0].update(event_frontier=1))
        self.rejected('frontier')

    def test_seed_mutation(self):
        self.change_manifest(lambda m: m['randomness']['seeds']['S246.Number'].__setitem__(0, 0))
        self.rejected('seed')

    def test_missing_initialization(self):
        self.change_manifest(lambda m: m.update(initialization={}))
        self.rejected('initial state')

    def test_warm_restart(self):
        self.change_manifest(lambda m: m['initialization'].update(tick=1))
        self.rejected('initial state')

    def test_pause_reset_stale_events(self):
        for kind in ('pause', 'resume', 'reset', 'single_step'):
            with self.subTest(kind=kind):
                self.change_manifest(lambda m: m.update(event_policy={'mode': kind, 'count': 1}))
                with self.assertRaisesRegex(ValueError, 'unsupported_event'):
                    r.load_bundle(self.root)

    def test_unexpected_event(self):
        rewrite(self.root, 'events.jsonl', encoded({'event_seq': 1, 'scene_epoch': 'stale', 'kind': 'start'}))
        self.rejected('unsupported_event')

    def test_foreign_model(self):
        self.change_manifest(lambda m: m['build_identity']['source'].update(archive_sha256='a'*64))
        self.rejected('foreign model')

    def test_wrong_config(self):
        rewrite(self.root, 'config.json', make_config(mass_kg=2))
        self.rejected('config identity')

    def test_phase_mismatch(self):
        self.change_rows('expected.jsonl', lambda x: x[0].update(output_phase='major_root'))
        self.rejected('phase')

    def test_undersampled_output(self):
        self.change_rows('expected.jsonl', lambda x: x.pop())
        self.rejected('missing interval')

    def test_terminal_missing(self):
        (self.root/'terminal.json').unlink()
        self.rejected('terminal.json')

    def test_terminal_unconfirmed(self):
        terminal = r.decode((self.root/'terminal.json').read_bytes())
        terminal['last_confirmed_tick'] = 2
        rewrite(self.root, 'terminal.json', terminal)
        self.rejected('terminal/frontier')

    def test_truncated_tail(self):
        rewrite(self.root, 'inputs.jsonl', (self.root/'inputs.jsonl').read_bytes()[:-1])
        self.rejected('truncated')

    def test_hash_mutation(self):
        with (self.root/'inputs.jsonl').open('ab') as f:
            f.write(b'\n')
        self.rejected('JSON|identity|Expecting value')

    def test_duplicate_json_key(self):
        (self.root/'manifest.json').write_bytes(b'{"schema":1,"schema":2}')
        self.rejected('duplicate JSON key')

    def test_nonfinite_json(self):
        for raw in (b'{"x":NaN}', b'{"x":1e999}'):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'nonfinite'):
                r.decode(raw)

    def test_escaping_member(self):
        self.change_manifest(lambda m: m['members'].update({'../escape': {}}))
        self.rejected('escaping')

    def test_symlink_member(self):
        target = self.base/'target'
        shutil.copyfile(self.root/'plan.json', target)
        (self.root/'plan.json').unlink()
        try:
            (self.root/'plan.json').symlink_to(target)
        except OSError:
            # Windows without symlink permission: exercise the same pre-read guard.
            with patch.object(Path, 'is_symlink', return_value=True):
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    r.read(target)
        else:
            self.rejected('symlink')

    def test_unknown_semantics(self):
        self.change_manifest(lambda m: m.update(interpolate=True))
        self.rejected('fields')

    def test_no_overwrite_or_source_output(self):
        with self.assertRaises(ValueError):
            r.import_bundle(self.root, self.root/'out')
        with self.assertRaises(FileExistsError):
            r.import_bundle(self.root, self.root.parent)

    def test_legacy_recording_refused(self):
        source = r.ROOT/'validation/quad-parameters-native-20260909-b/baseline.jsonl'
        with self.assertRaisesRegex(ValueError, 'insufficient_recording'):
            r.import_bundle(source, self.base/'legacy')
        self.assertFalse((self.base/'legacy').exists())


@unittest.skipUnless(os.environ.get('WKSIM_REEXECUTION_NATIVE'), 'explicit Linux native evidence directory required')
class NativeTests(unittest.TestCase):
    def test_native_cold_reexecution_and_corruption(self):
        base = Path(os.environ['WKSIM_REEXECUTION_NATIVE'])
        base.mkdir(parents=True, exist_ok=False)
        config = make_config('reexecution-native-fixture')
        built = build_configured_model(config)
        shutil.copytree(built.parent, base/'build')
        library = base/'build/libwksim_configured.so'
        identity = r.build_identity(library, config)
        r.write_json(base/'config.json', config)
        # Freeze the actual source plan before the source process starts.
        r.write_json(base/'source-plan.json', dict(kind='static_experiment_plan', first_tick=1, last_tick=25,
                     inPWMs=[.55]*4+[0.]*12, TerrainIn15d=[0.]*15, frozen_before_capture=True))
        command = [sys.executable, '-m', 'validation.test_model_reexecution', '--capture',
                   str(library), str(base/'config.json'), str(base/'source-plan.json'), str(base/'capture.json')]
        child = subprocess.run(command, capture_output=True, text=True, timeout=60)
        r.write_json(base/'capture-process.json', dict(argv=command, exit_code=child.returncode,
                      stdout=child.stdout, stderr=child.stderr))
        self.assertEqual(child.returncode, 0, child.stderr)
        capture = r.decode(r.read(base/'capture.json'))
        capture['process']['exited'] = True  # parent observed exit_code=0 above
        source = seal(base/'source', config, capture['outputs'], identity, capture['process'],
                      r.read(base/'build/build.json'), r.read(base/'source-plan.json'))
        before = {p.name: r.sha(r.read(p)) for p in source.iterdir()}
        def cli(*args, expected=0):
            result = subprocess.run([sys.executable, str(r.ROOT/'tools/reexecute_model.py'), *map(str, args)],
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, expected, result.stderr + result.stdout[-2000:])
            return result
        cli('import', '--source', source, '--output', base/'input')
        cli('run', '--input', base/'input', '--library', library, '--output', base/'run')
        cli('audit', '--input', base/'input', '--run', base/'run', '--output', base/'audit.json')
        audit = r.decode(r.read(base/'audit.json'))
        self.assertEqual(audit['counts'], {'ticks': 25, 'comparisons': 3000, 'failures': 0})
        request = r.decode(r.read(base/'run/request.json'))
        self.assertNotEqual(request['pid'], capture['process']['pid'])
        # Change expected output but preserve honest stream hashes. The rerun
        # must still integrate and return numerical_failed, not echo expected.
        shutil.copytree(source, base/'wrong-output')
        values = r.rows(r.read(base/'wrong-output/expected.jsonl'))
        values[9]['output120'][10] += 1
        rewrite(base/'wrong-output', 'expected.jsonl', b''.join(map(encoded, values)))
        m = r.decode(r.read(base/'wrong-output/manifest.json'))
        terminal = r.decode(r.read(base/'wrong-output/terminal.json'))
        terminal['streams']['expected.jsonl'] = m['members']['expected.jsonl']
        rewrite(base/'wrong-output', 'terminal.json', terminal)
        cli('run', '--input', base/'wrong-output', '--library', library, '--output', base/'mismatch-run', expected=1)
        mismatch = r.decode(r.read(base/'mismatch-run/audit.json'))
        self.assertEqual(mismatch['first_mismatch']['tick'], 10)
        self.assertEqual(mismatch['first_mismatch']['slot'], 10)
        self.assertEqual(mismatch['counts']['failures'], 1)
        # Independent audit rejects damaged runtime evidence even if an
        # attacker updates the actual-stream hash in its terminal.
        for case in ('gap', 'time', 'epoch', 'request', 'exit', 'terminal'):
            target = base/('audit-negative-' + case)
            shutil.copytree(base/'run', target)
            if case in ('gap', 'time', 'epoch'):
                actual = r.rows(r.read(target/'actual.jsonl'))
                if case == 'gap':
                    actual.pop(8)
                elif case == 'time':
                    actual[8]['before_ns'] += 1
                else:
                    actual[8]['scene_epoch'] = 'foreign'
                (target/'actual.jsonl').write_bytes(b''.join(map(encoded, actual)))
                term = r.decode(r.read(target/'terminal.json'))
                term['actual_sha256'] = r.sha(r.read(target/'actual.jsonl'))
                (target/'terminal.json').write_bytes(encoded(term))
            elif case == 'request':
                req = r.decode(r.read(target/'request.json'))
                req['manifest_sha256'] = '0'*64
                (target/'request.json').write_bytes(encoded(req))
            elif case == 'exit':
                proc = r.decode(r.read(target/'process.json'))
                proc['exit_code'] = 1
                (target/'process.json').write_bytes(encoded(proc))
            else:
                (target/'terminal.json').unlink()
            cli('audit', '--input', base/'input', '--run', target,
                '--output', base/('audit-rejected-' + case + '.json'), expected=2)
        # Wrong actual library is rejected before child request/create.
        shutil.copytree(base/'build', base/'wrong-build')
        with (base/'wrong-build/libwksim_configured.so').open('ab') as f:
            f.write(b'corruption')
        cli('run', '--input', base/'input', '--library', base/'wrong-build/libwksim_configured.so',
            '--output', base/'wrong-build-run', expected=2)
        self.assertFalse((base/'wrong-build-run/request.json').exists())
        self.assertEqual(before, {p.name: r.sha(r.read(p)) for p in source.iterdir()})


def capture():
    _, _, library, config_file, plan_file, output = sys.argv
    config = r.decode(r.read(config_file))
    plan = r.decode(r.read(plan_file))
    pid = os.getpid()
    process = dict(pid=pid, boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        starttime=int(Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19]),
        argv=sys.argv, exited=False)
    with r.ConfiguredModel(library, config) as model:
        outputs = [model.step(plan['inPWMs']) for _ in range(plan['last_tick'])]
    r.write_json(output, {'process': process, 'outputs': outputs})


if __name__ == '__main__':
    if '--capture' in sys.argv:
        capture()
    else:
        unittest.main()
