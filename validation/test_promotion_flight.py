"""Promotion contract checks; mocked reports are not build or flight evidence."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from Simulator.wksim_runtime.config import ConfigError, validate_config
from Simulator.wksim_runtime import independent_profile as profile, joint_profile, preflight
from validation.test_independent_profile import config
from tools import rebuild_promotion_evidence as rebuild


class PromotionFlightTests(unittest.TestCase):
    def test_flag_is_explicit_boolean_and_session_only(self):
        for value in ('true', 1, 0, None, [], {}):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                validate_config(dict(config(), promotion_flight=value))
        for value in (True, False):
            self.assertIs(validate_config(dict(config(), promotion_flight=value))['promotion_flight'], value)
        data = config()
        data.pop('runtime_profile')
        with self.assertRaisesRegex(ConfigError, 'explicit session_v1'):
            validate_config(dict(data, control_protocol='legacy_v1', promotion_flight=True))
        for value in ('true', 1, 0, None, [], {}):
            with self.subTest(model_value=value), self.assertRaises(ConfigError):
                validate_config(dict(config(), model_promotion_flight=value))
        with self.assertRaisesRegex(ConfigError, 'explicit session_v1'):
            validate_config(dict(data, control_protocol='legacy_v1', model_promotion_flight=True))
        promoted = validate_config(dict(config(), model_promotion_flight=True))
        self.assertIs(promoted['model_promotion_flight'], True)
        with self.assertRaisesRegex(ValueError, 'explicit model_promotion_flight'):
            preflight.promotion_model_build({}, {})

    def test_model_promotion_binds_exact_build_and_static_abi(self):
        from Simulator.wksim_core import model as model_module
        from Simulator.wksim_core.model import ABI_CONTRACT, MEMBERS
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / 'repo'
            core = repo / 'Simulator/wksim_core'
            core.mkdir(parents=True)
            wrapper, loader = core / 'model.cpp', core / 'model.py'
            wrapper.write_bytes(b'current wrapper')
            loader.write_bytes(b'current loader')
            build_dir = Path(directory) / 'model'
            build_dir.mkdir()
            archive = build_dir / 'MulticopterModel.zip'
            library = build_dir / 'libwksim_model.so'
            with zipfile.ZipFile(archive, 'w') as package:
                for index, member in enumerate(MEMBERS):
                    package.writestr(member, f'generated source {index}'.encode())
                    (build_dir / Path(member).name).write_bytes(f'generated source {index}'.encode())
            library.write_bytes(b'candidate library')
            sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            baseline = dict(archive=str(archive), archive_sha256=sha(archive),
                            compiler='pinned compiler', profile='pinned profile')
            source_files = [{'path': Path(member).name,
                             'size': (build_dir / Path(member).name).stat().st_size,
                             'sha256': sha(build_dir / Path(member).name)} for member in MEMBERS]
            archive_members = [{'path': member, 'size': row['size'], 'sha256': row['sha256']}
                               for member, row in zip(MEMBERS, source_files)]
            dependencies = ['libc.so.6', 'libstdc++.so.6']
            platform_record = {'system': 'Linux', 'machine': 'x86_64',
                               'libc': ['glibc', '2.35'], 'binary64_bytes': 8}
            build = dict(baseline, schema_version=2, archive_members=archive_members,
                         source_files=source_files, wrapper=str(wrapper), wrapper_sha256=sha(wrapper),
                         loader=str(loader.resolve()), loader_sha256=sha(loader), library=str(library),
                         library_sha256=sha(library), argv=[
                            'g++', '-std=c++17', '-O2', '-fno-fast-math', '-fPIC', '-shared',
                            '-Wl,--no-undefined', '-I', str(build_dir),
                            str(build_dir / 'Exp1_MinModelTemp.cpp'), str(wrapper), '-o', str(library)],
                         platform=platform_record, abi=ABI_CONTRACT,
                         dynamic_dependencies=dependencies)
            manifest = build_dir / 'build.json'

            def write_build(value):
                manifest.write_text(json.dumps(value))

            write_build(build)
            flags = dict(model_library=str(library), model_promotion_flight=True)
            nm_output = '\n'.join(
                f'0000000000000000 T {symbol}'
                for symbol in sorted(ABI_CONTRACT['required_symbols']))

            def fake_elf_tool(command, **kwargs):
                self.assertEqual(kwargs, dict(text=True, timeout=10))
                if command[:2] == ['readelf', '-d']:
                    return '\n'.join(
                        f' 0x0000000000000001 (NEEDED)             Shared library: [{dependency}]'
                        for dependency in dependencies)
                if command[:3] == ['nm', '-D', '--defined-only']:
                    return nm_output
                raise AssertionError(f'unexpected ELF command: {command}')

            with patch.object(preflight, 'REPO', repo), \
                    patch.object(model_module.subprocess, 'check_output', side_effect=fake_elf_tool) as elf_tools, \
                    patch('Simulator.wksim_core.model.model_platform', return_value=platform_record), \
                    patch.object(model_module.Model, '__init__', side_effect=AssertionError('must not load')), \
                    patch.object(model_module.ctypes, 'CDLL', side_effect=AssertionError('must not load')):
                regular = preflight.validate_model_build_manifest(
                    {'model_library': str(library)}, {'model_build': baseline})
                self.assertFalse(regular['identities']['model_library']['promotion_candidate'])
                result = preflight.promotion_model_build(flags, {'model_build': baseline})
                self.assertEqual(result['build'], build)
                self.assertEqual(result['abi']['contract'], ABI_CONTRACT)
                self.assertIn('wk_model_initial_state', result['abi']['exported_symbols'])
                self.assertEqual(result['identities']['model_loader']['sha256'], sha(loader))
                self.assertEqual(len(elf_tools.call_args_list), 4)
                changed = copy.deepcopy(build)
                changed['wrapper_sha256'] = '0' * 64
                write_build(changed)
                with self.assertRaisesRegex(ValueError, 'model_wrapper'):
                    preflight.promotion_model_build(flags, {'model_build': baseline})

                for key, value, pattern in (
                        ('schema_version', 1, 'schema'),
                        ('archive_sha256', '0' * 64, 'baseline'),
                        ('compiler', 'changed compiler', 'baseline'),
                        ('profile', 'changed profile', 'baseline'),
                        ('argv', list(build['argv']) + ['--changed'], 'compiler'),
                        ('archive_members', [], 'source'),
                        ('source_files', [], 'source'),
                        ('library_sha256', '0' * 64, 'model_library'),
                        ('loader_sha256', '0' * 64, 'model_loader'),
                        ('library', str(archive), 'library path'),
                        ('abi', {}, 'ABI'),
                        ('platform', {}, 'ABI')):
                    changed = copy.deepcopy(build)
                    changed[key] = value
                    write_build(changed)
                    with self.subTest(manifest_field=key), self.assertRaisesRegex(ValueError, pattern):
                        preflight.validate_model_build_manifest(flags, {'model_build': baseline})

                changed = copy.deepcopy(build)
                changed['abi']['initial_state']['read_only'] = 1
                write_build(changed)
                with self.assertRaisesRegex(ValueError, 'ABI'):
                    preflight.validate_model_build_manifest(flags, {'model_build': baseline})

                changed = copy.deepcopy(build)
                changed['dynamic_dependencies'] = ['libc.so.6']
                write_build(changed)
                with self.assertRaisesRegex(ValueError, 'dynamic dependency set'):
                    preflight.validate_model_build_manifest(flags, {'model_build': baseline})

                write_build(build)
                for dependency in ('libgazebo.so', 'gazebo_plugin.so', 'GAZEBO_PLUGIN.SO'):
                    changed = copy.deepcopy(build)
                    changed['dynamic_dependencies'] = [dependency]
                    write_build(changed)
                    with patch('Simulator.wksim_core.model.dynamic_dependencies',
                               return_value=[dependency]):
                        for candidate in (False, True):
                            with self.subTest(forbidden_dependency=dependency,
                                              promotion_candidate=candidate), \
                                    self.assertRaisesRegex(ValueError, 'Forbidden model dynamic dependency'):
                                if candidate:
                                    preflight.promotion_model_build(flags, {'model_build': baseline})
                                else:
                                    preflight.validate_model_build_manifest(
                                        {'model_library': str(library)}, {'model_build': baseline})
                for dependency in ('libgazeboard_helper.so', 'libregular.so'):
                    changed = copy.deepcopy(build)
                    changed['dynamic_dependencies'] = [dependency]
                    write_build(changed)
                    with patch('Simulator.wksim_core.model.dynamic_dependencies',
                               return_value=[dependency]):
                        for candidate in (False, True):
                            with self.subTest(allowed_dependency=dependency,
                                              promotion_candidate=candidate):
                                accepted = (preflight.promotion_model_build(
                                    flags, {'model_build': baseline}) if candidate else
                                    preflight.validate_model_build_manifest(
                                        {'model_library': str(library)},
                                        {'model_build': baseline}))
                                self.assertEqual(accepted['abi']['dynamic_dependencies'], [dependency])
                write_build(build)
                with patch('Simulator.wksim_core.model.exported_model_symbols',
                           return_value=sorted(ABI_CONTRACT['required_symbols'])[:-1]):
                    with self.assertRaisesRegex(ValueError, 'exported symbol set'):
                        preflight.validate_model_build_manifest(flags, {'model_build': baseline})

                duplicate = json.dumps(build).replace(
                    '"schema_version": 2', '"schema_version": 2, "schema_version": 2', 1)
                manifest.write_text(duplicate)
                with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
                    preflight.validate_model_build_manifest(flags, {'model_build': baseline})
                nonfinite = json.dumps(build).replace('"schema_version": 2',
                                                       '"schema_version": NaN', 1)
                manifest.write_text(nonfinite)
                with self.assertRaisesRegex(ValueError, 'Non-finite JSON'):
                    preflight.validate_model_build_manifest(flags, {'model_build': baseline})

                write_build(build)
                with patch.object(preflight.zipfile, 'ZipFile',
                                  side_effect=zipfile.BadZipFile('invalid archive')):
                    with self.assertRaisesRegex(zipfile.BadZipFile, 'invalid archive'):
                        preflight.validate_model_build_manifest(flags, {'model_build': baseline})

                write_build(build)
                link = build_dir / 'library-link.so'
                try:
                    link.symlink_to(library)
                except OSError:
                    pass
                else:
                    with self.assertRaisesRegex(ValueError, 'canonical non-symlink'):
                        preflight.validate_model_build_manifest(
                            dict(flags, model_library=str(link)), {'model_build': baseline})
                    link.unlink()

                moved_manifest = build_dir / 'build-moved.json'
                manifest.rename(moved_manifest)
                try:
                    manifest.symlink_to(moved_manifest)
                except OSError:
                    moved_manifest.rename(manifest)
                else:
                    with self.assertRaisesRegex(ValueError, 'canonical non-symlink'):
                        preflight.validate_model_build_manifest(flags, {'model_build': baseline})
                    manifest.unlink()
                    moved_manifest.rename(manifest)

    def test_preflight_early_rejection_keeps_candidate_schema(self):
        data = config()
        data['capabilities'] = ['not-admitted']
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory) / 'capability-index.json'
            index.write_text(json.dumps({'capabilities': []}))
            with patch.object(preflight, 'INDEX', index), \
                    patch.object(preflight, 'validate_config', return_value=dict(data)):
                result = preflight.preflight(data)
        self.assertFalse(result['ok'])
        self.assertEqual(result['reasons'][0]['code'], 'unsupported_capability')
        self.assertEqual(set(result['candidate_status']),
                         {'implemented', 'built', 'flown', 'scope'})
        self.assertFalse(result['candidate_status']['flown'])

        rejected = preflight._finish_preflight_result(
            dict(ok=False, reasons=[dict(code='model_manifest_mismatch', message='bad')],
                 identities={}, capabilities=[], children_created=0),
            dict(model_promotion_flight=True))
        self.assertFalse(rejected['candidate_status']['built'])
        self.assertEqual(rejected['flight_provenance'], 'model_promotion_flight')

    def test_independent_only_skips_history_and_never_claims_flown(self):
        for stack in ('px4', 'arducopter'):
            key = 'ap' if stack == 'arducopter' else 'px4'
            report = dict(ok=True, reasons=[], children_created=0, model_library='/model',
                          identities={key: dict(path='/firmware', sha256='fw', commit='commit'),
                                      stack + '_agent': dict(path='/agent', sha256='agent'),
                                      'model': dict(library_sha256='model')})
            for flag in (None, False, True):
                data = config(stack)
                if flag is not None:
                    data['promotion_flight'] = flag
                with self.subTest(stack=stack, flag=flag), \
                        patch.object(joint_profile, 'check_resources', return_value=copy.deepcopy(report)) as resources, \
                        patch.object(profile, 'check_flight_evidence', side_effect=ValueError('old flight')) as history:
                    result = profile.check_profile(data)
                resources.assert_called_once()
                self.assertEqual(resources.call_args.kwargs, dict(stacks=(stack,)))
                self.assertEqual(result['ok'], flag is True)
                self.assertFalse(result['candidate_status']['flown'])
                if flag is True:
                    history.assert_not_called()
                    self.assertEqual(result['flight_provenance'], 'promotion_flight')
                    self.assertTrue(result['candidate_status']['built'])
                    self.assertFalse(result['capabilities'][0]['flown'])
                    self.assertEqual(result['identities']['firmware']['sha256'], 'fw')
                else:
                    history.assert_called_once()

    def test_promotion_resource_failure_remains_rejection(self):
        for reason in ('firmware', 'control build', 'model', 'message content', 'overlay'):
            with self.subTest(reason=reason), patch.object(joint_profile, 'check_resources', return_value=dict(
                    ok=False, reasons=[dict(code='joint_profile_rejected', message=reason)], identities={})), \
                    patch.object(profile, 'check_flight_evidence') as history:
                result = profile.check_profile(dict(config(), promotion_flight=True))
                self.assertFalse(result['ok'])
                self.assertFalse(result['candidate_status']['built'])
                self.assertFalse(result['candidate_status']['flown'])
                self.assertEqual(result['reasons'][0]['message'], reason)
                history.assert_not_called()

    def test_session_requires_pinned_build_and_complete_snapshot(self):
        data = dict(config(), prometheus_workspace='/reviewed', promotion_flight=True)
        pin = dict(prefix='/reviewed/install/prometheus_control', complete_snapshot=True, sha256='snapshot')
        index = dict(control_profiles=dict(session_v1=dict(installed_packages=dict(prometheus_control=pin))))
        evidence = dict(prometheus=dict(implementation_sha256={'old.py': 'old'}))
        record = dict(python_sha256={'current.py': 'current'})
        self.assertEqual(preflight.control_sources(dict(data, promotion_flight=False), index, evidence), {'old.py': 'old'})
        with patch.object(joint_profile, '_pinned_json', return_value=record), \
                patch.object(joint_profile, '_control') as build, \
                patch.object(preflight, 'package_digest', return_value='snapshot') as snapshot:
            self.assertEqual(preflight.control_sources(data, index, evidence), record['python_sha256'])
            build.assert_called_once_with(record, sealed=True)
            self.assertEqual(snapshot.call_args.kwargs, dict(complete=True))
            for mutation in (dict(sha256='wrong'), dict(complete_snapshot=False), dict(prefix='/wrong')):
                changed = copy.deepcopy(index)
                changed['control_profiles']['session_v1']['installed_packages']['prometheus_control'].update(mutation)
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    preflight.control_sources(data, changed, evidence)
            build.side_effect = ValueError('build differs')
            with self.assertRaisesRegex(ValueError, 'build differs'):
                preflight.control_sources(data, index, evidence)

    def test_session_catalog_is_candidate_only_and_requires_current_control(self):
        before = preflight.INDEX.read_bytes()
        index = json.loads(before)
        paths = [preflight.REPO / p['result'] for p in index['control_profiles']['session_v1']['evidence'].values()]
        sources = json.loads(paths[0].read_text())['prometheus']['implementation_sha256']
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(preflight, 'control_sources', return_value={'not-flown.py': 'new'}):
                with self.assertRaisesRegex(ValueError, 'current pinned control'):
                    rebuild.session(paths, Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])
            with patch.object(preflight, 'control_sources', return_value=sources):
                rebuild.session(paths, Path(directory))
            candidate = json.loads((Path(directory) / 'capability-index.candidate.json').read_text())
            self.assertEqual(candidate, index)
            with patch.object(preflight, 'control_sources', return_value=sources), self.assertRaises(FileExistsError):
                rebuild.session(paths, Path(directory))
        self.assertEqual(preflight.INDEX.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
