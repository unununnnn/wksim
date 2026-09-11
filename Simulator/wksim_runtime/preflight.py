"""Read-only Linux admission; no flight, ROS node or compiler is launched."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import stat
import subprocess
import sys
import zipfile

from .config import ConfigError, load_config, validate_config

REPO = Path(__file__).resolve().parents[2]
INDEX = Path(__file__).with_name('capability-index.json')
MODEL_BUILD_FIELDS = frozenset(('schema_version', 'archive', 'archive_sha256', 'archive_members',
                                'source_files', 'wrapper', 'wrapper_sha256', 'loader',
                                'loader_sha256', 'library', 'library_sha256', 'argv', 'compiler',
                                'profile', 'platform', 'abi', 'dynamic_dependencies'))


def digest(path):
    with Path(path).open('rb') as stream:
        checksum = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def package_digest(root, complete=False):
    """Hash installed content; complete snapshots also cover metadata and build hooks.

    The default preserves the historical schema/Python/ELF snapshot algorithm.
    Complete snapshots exclude only Python bytecode caches.
    """
    root = Path(root)
    files = sorted(p for p in root.rglob('*') if p.is_file() and
                   ((complete and '__pycache__' not in p.parts and p.suffix != '.pyc') or
                    (not complete and (p.suffix in ('.py', '.so', '.msg', '.srv', '.idl') or '.so.' in p.name))))
    if not files:
        raise ValueError(f'Empty message package: {root}')
    content = ''.join(f'{p.relative_to(root).as_posix()}\0{digest(p)}\n' for p in files)
    return hashlib.sha256(content.encode()).hexdigest()


def promotion_model_build(config, evidence):
    """Statically validate one explicit unflown model build without changing old proof."""
    if config.get('model_promotion_flight') is not True:
        raise ValueError('Model promotion requires an explicit model_promotion_flight flag')
    from Simulator.wksim_core.model import (ABI_CONTRACT, MEMBERS, dynamic_dependencies,
                                             exported_model_symbols, model_platform)
    baseline = evidence['model_build']
    library = Path(config['model_library'])
    if library.is_symlink() or library.resolve(strict=True) != library:
        raise ValueError('Promotion model library must be an existing canonical non-symlink path')
    manifest = library.with_name('build.json')
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError('Promotion model build manifest is missing or a symlink')
    build = json.loads(manifest.read_text(encoding='utf-8'))
    if not isinstance(build, dict) or set(build) != MODEL_BUILD_FIELDS:
        raise ValueError('Promotion model build manifest fields differ')
    if build['schema_version'] != 2:
        raise ValueError('Promotion model build manifest schema differs')
    for key in ('archive', 'archive_sha256', 'compiler', 'profile'):
        if build.get(key) != baseline[key]:
            raise ValueError('Promotion model differs from the reviewed baseline at ' + key)
    archive = Path(build['archive'])
    wrapper = REPO / 'Simulator/wksim_core/model.cpp'
    loader = REPO / 'Simulator/wksim_core/model.py'
    if build['wrapper'] != str(wrapper) or build['loader'] != str(loader.resolve()):
        raise ValueError('Promotion model wrapper or loader path differs')
    expected_argv = ['g++', '-std=c++17', '-O2', '-fno-fast-math', '-fPIC', '-shared',
                     '-Wl,--no-undefined', '-I', str(library.parent),
                     str(library.parent / 'Exp1_MinModelTemp.cpp'), str(wrapper), '-o', str(library)]
    if build['argv'] != expected_argv:
        raise ValueError('Promotion model compiler invocation differs')
    identities = {
        'model_library': (library, build['library_sha256']),
        'model_archive': (archive, build['archive_sha256']),
        'model_wrapper': (wrapper, build['wrapper_sha256']),
    }
    checked = {}
    for label, (path, expected) in identities.items():
        actual = digest(path)
        if actual != expected:
            raise ValueError(f'{label}: SHA256 differs: {path}')
        checked[label] = dict(path=str(path.resolve()), sha256=actual,
                              expected_sha256=expected, match=True, promotion_candidate=True)
    if Path(build['library']).resolve(strict=True) != library:
        raise ValueError('Promotion model build manifest library path differs')
    loader_sha = digest(loader)
    if loader_sha != build['loader_sha256']:
        raise ValueError('model_loader: SHA256 differs: ' + str(loader))
    checked['model_loader'] = dict(path=str(loader.resolve()), sha256=loader_sha,
                                   expected_sha256=build['loader_sha256'], match=True,
                                   promotion_candidate=True)
    with zipfile.ZipFile(archive) as source_archive:
        archive_members = [{"path": member, "size": source_archive.getinfo(member).file_size,
                            "sha256": hashlib.sha256(source_archive.read(member)).hexdigest()}
                           for member in MEMBERS]
    source_files = [{"path": Path(member).name,
                     "size": (library.parent / Path(member).name).stat().st_size,
                     "sha256": digest(library.parent / Path(member).name)} for member in MEMBERS]
    if build['archive_members'] != archive_members or build['source_files'] != source_files:
        raise ValueError('Promotion model generated source evidence differs')
    if build['abi'] != ABI_CONTRACT or build['platform'] != model_platform():
        raise ValueError('Promotion model ABI or platform contract differs')
    dependencies = dynamic_dependencies(library)
    symbols = exported_model_symbols(library)
    if build['dynamic_dependencies'] != dependencies:
        raise ValueError('Promotion model dynamic dependency set differs')
    if symbols != sorted(ABI_CONTRACT['required_symbols']):
        raise ValueError('Promotion model exported symbol set differs')
    return dict(build=build, identities=checked,
                abi=dict(contract=ABI_CONTRACT, exported_symbols=symbols,
                         dynamic_dependencies=dependencies,
                         scope='static candidate ELF/source contract; not ABI execution or flight proof'))


def control_profile(index, protocol, stack, check_file):
    """Select pinned evidence without updating the historical baseline or importing ROS."""
    profile = index['control_profiles'][protocol]
    baseline = index['baselines'][stack]
    if protocol == 'legacy_v1':
        if profile['baselines'] != 'baselines':
            raise ValueError('legacy_v1 must reference the historical baselines')
        return baseline
    evidence_by_stack = {}
    for peer in ('px4', 'arducopter'):
        pin = profile['evidence'][peer]
        path = REPO / pin['result']
        # Parse the very bytes whose digest was checked; no trust in directory names.
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != pin['result_sha256']:
            raise ValueError(f'{peer}: session flight evidence SHA256 differs')
        check_file('session_evidence/' + peer, path, pin['result_sha256'])
        evidence = json.loads(raw)
        historical_pin = index['baselines'][peer]
        historical_path = REPO / historical_pin['result']
        historical_raw = historical_path.read_bytes()
        if hashlib.sha256(historical_raw).hexdigest() != historical_pin['result_sha256']:
            raise ValueError(f'{peer}: historical flight evidence SHA256 differs')
        historical = json.loads(historical_raw)
        control = evidence['prometheus']
        if (evidence['status'] != 'pass' or evidence['stack'] != peer or
                control['protocol'] != protocol or
                evidence['prometheus_workspace'] != profile['workspace'] or
                evidence['dds_workspace'] != historical_pin['roots']['dds_workspace'] or
                evidence['dds']['commands'] != []):
            raise ValueError(f'{peer}: invalid control protocol, workspace, stack or observer evidence')
        allowed_binaries = {historical['fc_binary']}
        if peer == 'px4' and index.get('resource_locations', {}).get('px4_root'):
            # The already-approved project relocation applies to new evidence
            # as well as resource preflight. Historical bytes/hashes stay fixed.
            allowed_binaries.add(str(PurePosixPath(index['resource_locations']['px4_root']) / 'build/px4_sitl_default/bin/px4'))
        if evidence['fc_binary'] not in allowed_binaries:
            raise ValueError(f'{peer}: fixed firmware path differs from historical or reviewed relocation')
        for key in ('fc_binary_sha256', 'fc_commit', 'agent_sha256'):
            if evidence[key] != historical[key]:
                raise ValueError(f'{peer}: fixed firmware/agent differs at {key}')
        if peer == 'arducopter':
            for key in ('ap_dds_candidate', 'candidate_source_sha256'):
                if evidence[key] != historical[key]:
                    raise ValueError(f'{peer}: fixed candidate source differs at {key}')
        for key in ('archive', 'archive_sha256', 'wrapper_sha256', 'library_sha256', 'profile', 'compiler'):
            if evidence['model_build'][key] != historical['model_build'][key]:
                raise ValueError(f'{peer}: fixed model differs at {key}')
        if evidence['implementation_sha256']['Simulator/wksim_core/model.py'] != historical['implementation_sha256']['Simulator/wksim_core/model.py']:
            raise ValueError(f'{peer}: fixed model loader differs')
        if (not control['run_id'] or not control['control_epoch'] or
                control['run_id'] != Path(pin['result']).parent.name or
                'run_id:=' + control['run_id'] not in evidence['prometheus-node']['argv'] or
                'flight_stack:=' + peer not in evidence['prometheus-node']['argv'] or
                'session.py' not in control['implementation_sha256']):
            raise ValueError(f'{peer}: missing session/source identity')
        envelopes = control['request_envelopes']
        if len(envelopes) != 6 or len(control['sent']) != 6:
            raise ValueError(f'{peer}: incomplete flown request envelopes')
        for number, (request, sent) in enumerate(zip(envelopes, control['sent']), 1):
            payload = 'setup' if number in (1, 2, 3, 6) else 'command'
            if (request['version'] != 1 or request['request_id'] != number or
                    request['run_id'] != control['run_id'] or
                    request['control_epoch'] != control['control_epoch'] or request[payload] != sent):
                raise ValueError(f'{peer}: inconsistent request envelope')
        evidence_by_stack[peer] = evidence
    if evidence_by_stack['px4']['prometheus']['implementation_sha256'] != evidence_by_stack['arducopter']['prometheus']['implementation_sha256']:
        raise ValueError('Session flights used different installed control sources')
    return dict(baseline, roots=dict(baseline['roots'], prometheus_workspace=profile['workspace']),
                **profile['evidence'][stack],
                message_packages=dict(baseline['message_packages'], **profile['installed_packages']))


def consumer_rejections(config):
    errors=[]
    def reject(key,message):errors.append(dict(code=key+'_invalid',message=message))
    for key in ('display_socket','telemetry_socket'):
        if key not in config:continue
        socket=Path(config[key]);parent=socket.parent
        if parent.is_symlink() or parent.resolve()!=parent:
            reject(key,'Consumer directory must not resolve through a symlink')
        if parent.exists():
            mode=parent.stat()
            if not parent.is_dir() or mode.st_uid!=os.getuid() or stat.S_IMODE(mode.st_mode)!=0o700:
                reject(key,'Consumer directory must be owned by current UID with mode 0700')
        if socket.is_symlink() or (socket.exists() and not stat.S_ISSOCK(socket.stat().st_mode)):
            reject(key,'Consumer receiver must be a Unix socket, not a regular file or symlink')
        if key=='telemetry_socket' and socket.exists():
            info=socket.stat()
            if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600:
                reject(key,'Telemetry receiver must be owned by current UID with mode 0600')
    return errors


def control_sources(config, index, evidence):
    """Promotion replaces only historical source binding with the pinned build."""
    if not config.get('promotion_flight', False):
        return evidence['prometheus']['implementation_sha256']
    from . import joint_profile
    p = joint_profile.select_profile('joint_quad_dds_v1')
    record = joint_profile._pinned_json(p['manifests']['control'])
    joint_profile._control(record, sealed=True)
    pin = index['control_profiles']['session_v1']['installed_packages']['prometheus_control']
    prefix = Path(config['prometheus_workspace']) / 'install/prometheus_control'
    if (prefix != Path(pin['prefix']) or not pin.get('complete_snapshot')
            or package_digest(prefix, complete=True) != pin['sha256']):
        raise ValueError('Promotion control complete installed snapshot differs')
    return record['python_sha256']


def preflight(config):
    """Return JSON-safe evidence; ok is candidate admission, never flight readiness."""
    if isinstance(config,dict) and config.get('kind')=='joint_scene':
        from .joint_config import validate_joint_config
        from .joint_profile import check_profile
        try:
            normalized=validate_joint_config(config)
            if platform.system()=='Linux':
                errors=consumer_rejections(normalized)
                if errors:return dict(ok=False,reasons=errors,children_created=0,config=normalized)
            from .joint_aruco_profile import PROFILE as ARUCO_PROFILE, check as check_aruco
            admission = (check_aruco(normalized) if normalized['runtime_profile'] == ARUCO_PROFILE
                         else check_profile(normalized['runtime_profile'],normalized['run_id']))
            return dict(admission,config=normalized)
        except (OSError,ValueError,TypeError) as error:
            return dict(ok=False,reasons=[dict(code='invalid_config',message=str(error))],children_created=0)
    result = dict(ok=False, reasons=[], identities={}, capabilities=[], children_created=0)

    def reject(code, message):
        result['reasons'].append(dict(code=code, message=str(message)))

    def check_file(label, path, expected):
        path = Path(path)
        try:
            actual = digest(path)
            result['identities'][label] = dict(path=str(path.resolve()), sha256=actual,
                                               expected_sha256=expected, match=actual == expected)
            if actual != expected:
                reject('identity_mismatch', f'{label}: SHA256 differs: {path}')
        except OSError as error:
            reject('resource_missing', f'{label}: {error}')

    try:
        config = validate_config(config)
        result['config'] = config
        index = json.loads(INDEX.read_text(encoding='utf-8'))
        result['capabilities'] = index['capabilities']
        rows = {row['id']: row for row in index['capabilities']}
        for requested in config['capabilities']:
            if requested not in rows or not rows[requested].get('admitted', False):
                reject('unsupported_capability', f'{requested}: unknown or not admitted for this product slice')
        if result['reasons']:
            return result
        if platform.system() != 'Linux':
            reject('unsupported_platform', 'Run inside Ubuntu-22.04 with the selected ROS2 overlays sourced')
            return result
        result['reasons'].extend(consumer_rejections(config))
        if 'telemetry_socket' in config:
            from .telemetry_dialect import load_dialect
            _, result['identities']['telemetry_decoder'] = load_dialect(config['stack'])
        release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
        if release.get('ID', '').strip('"') != 'ubuntu' or release.get('VERSION_ID', '').strip('"') != '22.04':
            reject('unsupported_platform', 'Only Ubuntu 22.04 has a pinned environment')
        if config.get('runtime_profile'):
            if result['reasons']:
                return result
            from .independent_profile import check_profile
            consumer_identities=result['identities']
            result=check_profile(config)
            result['identities'].update(consumer_identities)
            if (result['ok'] and 'telemetry_socket' in config
                    and result['identities']['telemetry_decoder']['fc_commit']!=result['identities']['firmware_commit']):
                reject('identity_mismatch','Telemetry dialect does not match the pinned firmware commit')
                result['ok']=False
            return result
        stack = config['stack']
        protocol = config.get('control_protocol', 'legacy_v1')
        result['control_profile'] = protocol
        baseline = control_profile(index, protocol, stack, check_file)
        evidence_path = REPO / baseline['result']
        check_file('flight_evidence', evidence_path, baseline['result_sha256'])
        if result['reasons']:
            return result
        evidence = json.loads(evidence_path.read_text())
        if (evidence['status'] != 'pass' or evidence['stack'] != stack or
                evidence['prometheus'].get('protocol', 'legacy_v1') != protocol):
            reject('invalid_evidence', 'Pinned flight result does not report this stack passing')
            return result
        result['candidate_status'] = dict(implemented=True, built=False, flown=False,
                                         scope='six public inputs, independent SITL; ground DDS reconnect only')
        roots = {key: Path(config[key]).resolve(strict=True) for key in
                 ('dds_workspace', 'prometheus_workspace', 'px4_root')}
        if stack == 'arducopter':
            roots['ap_candidate'] = Path(config['ap_candidate']).resolve(strict=True)
        # Explicit roots plus content hashes: a familiar basename grants no trust.
        for key, expected in baseline['roots'].items():
            # Relocation changes local storage, not historical flight evidence
            # or the firmware/content hashes required below.
            expected = index.get('resource_locations', {}).get(key, expected)
            if roots[key] != Path(expected).resolve(strict=True):
                reject('candidate_not_pinned', f'{key}: {roots[key]} is not the reviewed resource {expected}')
        firmware = (roots['ap_candidate'] / 'build/sitl/bin/arducopter' if stack == 'arducopter'
                    else roots['px4_root'] / 'build/px4_sitl_default/bin/px4')
        check_file('firmware', firmware, evidence['fc_binary_sha256'])
        if not os.access(firmware, os.X_OK):
            reject('resource_not_executable', f'Firmware is not executable: {firmware}')
        if stack == 'px4':
            manifest = roots['px4_root']/'wksim-runtime-files.json'
            pin = index.get('runtime_resources', {}).get('px4_launch_manifest_sha256')
            if pin is None:
                reject('resource_missing', 'No pinned independent PX4 launch-file manifest')
            else:
                check_file('px4_launch_manifest', manifest, pin)
                if result['identities'].get('px4_launch_manifest', {}).get('match'):
                    launch_files=json.loads(manifest.read_text())
                    if (launch_files.get('independent_root')!=str(roots['px4_root'])
                            or launch_files.get('binary_sha256')!=evidence['fc_binary_sha256']):
                        reject('identity_mismatch','PX4 launch resource root/binary differs')
                    for name, entry in launch_files['files'].items():
                        if Path(name).name!=name or not name.startswith('px4-'):
                            reject('identity_mismatch','Invalid PX4 launch resource name')
                            continue
                        path=firmware.parent/name
                        if 'sha256' in entry:
                            check_file('px4_launch/'+name,path,entry['sha256'])
                        elif (entry.get('relative_link')!='px4' or not path.is_symlink()
                              or os.readlink(path)!='px4' or path.resolve()!=firmware.resolve()):
                            reject('resource_missing','PX4 module entry is not bound to the local pinned binary: '+name)
                    data=roots['px4_root']/'test_data'
                    if not data.is_dir() or data.resolve()!=data:
                        reject('resource_missing','Independent PX4 test_data directory is missing or external')
        firmware_identity = result['identities'].get('firmware', {})
        for candidate in index['known_unflown_candidates']:
            if firmware_identity.get('sha256') == candidate['sha256']:
                result['known_candidate'] = candidate
        result['identities']['firmware_commit'] = evidence['fc_commit']
        if ('telemetry_socket' in config
                and result['identities']['telemetry_decoder']['fc_commit'] != evidence['fc_commit']):
            reject('identity_mismatch', 'Telemetry dialect does not match the pinned firmware commit')
        agent = roots['dds_workspace'] / ('ros-install/micro_ros_agent/lib/micro_ros_agent/micro_ros_agent'
                                          if stack == 'arducopter' else 'agent-install/bin/MicroXRCEAgent')
        check_file('agent', agent, evidence['agent_sha256'])
        if not os.access(agent, os.X_OK):
            reject('resource_not_executable', f'Agent is not executable: {agent}')
        model = evidence['model_build']
        library = Path(config.get('model_library', index.get('resource_locations', {}).get('model_library', model['library'])))
        config['model_library'] = str(library.resolve())
        if config.get('model_promotion_flight', False):
            promoted = promotion_model_build(config, evidence)
            build = promoted['build']
            result['identities'].update(promoted['identities'])
            result['model_promotion'] = promoted['abi']
        else:
            check_file('model_library', library, model['library_sha256'])
            check_file('model_archive', model['archive'], model['archive_sha256'])
            check_file('model_wrapper', REPO / 'Simulator/wksim_core/model.cpp', model['wrapper_sha256'])
            check_file('model_loader', REPO / 'Simulator/wksim_core/model.py',
                       evidence['implementation_sha256']['Simulator/wksim_core/model.py'])
            build = json.loads(library.with_name('build.json').read_text())
            for key in ('archive_sha256', 'wrapper_sha256', 'library_sha256', 'profile', 'compiler'):
                if build.get(key) != model[key]:
                    reject('model_manifest_mismatch', f'model build.json differs at {key}')
            if Path(build['library']).resolve() != library.resolve():
                reject('model_manifest_mismatch', 'build.json library path differs from selected library')
        result['identities']['model_build'] = build
        package_root = roots['prometheus_workspace'] / 'install/prometheus_control/local/lib/python3.10/dist-packages/prometheus_control'
        expected_control = control_sources(config, index, evidence)
        for file, expected in expected_control.items():
            check_file('prometheus/' + file, package_root / file, expected)
        if protocol == 'session_v1':
            expected_files = set(expected_control)
            actual_files = {p.relative_to(package_root).as_posix() for p in package_root.rglob('*.py')}
            if actual_files != expected_files:
                reject('identity_mismatch', 'Installed control Python file set differs from both flown results')
            source_root = roots['prometheus_workspace'] / 'src/prometheus_control/prometheus_control'
            for file, expected in expected_control.items():
                check_file('control_source/' + file, source_root / file, expected)
        if stack == 'arducopter':
            for file, expected in evidence['candidate_source_sha256'].items():
                check_file('candidate_source/' + file, roots['ap_candidate'] / 'src' / file, expected)
            for file, expected in index['patches'].items():
                check_file('patch/' + file, REPO / file, expected)
        for name, package in baseline['message_packages'].items():
            prefix = Path(package['prefix'])
            actual = package_digest(prefix, complete=package.get('complete_snapshot', False))
            result['identities']['messages/' + name] = dict(prefix=str(prefix), sha256=actual,
                expected_sha256=package['sha256'], match=actual == package['sha256'],
                status='installed snapshot checked; historical flight provenance limited to pinned result')
            if actual != package['sha256']:
                reject('message_identity_mismatch', f'{name}: installed content differs from reviewed snapshot')
            spec = importlib.util.find_spec(name)
            expected_module = prefix / 'local/lib/python3.10/dist-packages' / name / '__init__.py'
            if spec is None or spec.origin is None or Path(spec.origin).resolve() != expected_module.resolve():
                reject('mixed_overlay', f'{name}: Python resolves {None if spec is None else spec.origin}; expected {expected_module}')
            active = next((Path(p).resolve() for p in os.environ.get('AMENT_PREFIX_PATH', '').split(os.pathsep)
                           if p and (Path(p) / 'share/ament_index/resource_index/packages' / name).is_file()), None)
            if active != prefix.resolve():
                reject('mixed_overlay', f'{name}: ament resolves {active}; expected {prefix}')
            for library_path in (prefix / 'lib').glob('*.so*'):
                selected = next((Path(p) / library_path.name for p in os.environ.get('LD_LIBRARY_PATH', '').split(os.pathsep)
                                 if p and (Path(p) / library_path.name).is_file()), None)
                if selected is None or selected.resolve() != library_path.resolve():
                    reject('mixed_overlay', f'{name}: linker resolves {selected}; expected {library_path}')
            for module_name, module in tuple(sys.modules.items()):
                module_file = getattr(module, '__file__', None)
                if module_file and (module_name == name or module_name.startswith(name + '.')):
                    if not Path(module_file).resolve().is_relative_to(prefix.resolve()):
                        reject('mixed_overlay', f'{name}: already imported module outside selected prefix: {module_file}')
        spec = importlib.util.find_spec('prometheus_control')
        if spec is None or spec.origin is None or Path(spec.origin).resolve() != (package_root / '__init__.py').resolve():
            reject('mixed_overlay', 'prometheus_control must resolve to the selected installed package')
        if os.environ.get('ROS_DISTRO') != 'humble':
            reject('ros_environment', 'ROS_DISTRO must be humble; source the selected overlays')
        result['candidate_status']['built'] = not any(r['code'] in ('identity_mismatch', 'resource_missing', 'candidate_not_pinned', 'model_manifest_mismatch') for r in result['reasons'])
        result['ok'] = not result['reasons']
        promotion = config.get('promotion_flight', False) or config.get('model_promotion_flight', False)
        result['candidate_status']['flown'] = result['ok'] and not promotion
        if config.get('model_promotion_flight', False):
            result['flight_provenance'] = 'model_promotion_flight'
        elif config.get('promotion_flight', False):
            result['flight_provenance'] = 'promotion_flight'
    except ConfigError as error:
        reject('invalid_config', error)
    except (OSError, ValueError, KeyError, TypeError, ImportError, subprocess.SubprocessError) as error:
        reject('preflight_unavailable', error)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    args = parser.parse_args(argv)
    try:
        result = preflight(load_config(args.config))
    except ConfigError as error:
        result = dict(ok=False, reasons=[dict(code='invalid_config', message=str(error))],
                      identities={}, capabilities=[], children_created=0)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    print('Preflight admitted (not flight readiness).' if result['ok'] else 'Preflight rejected.', file=sys.stderr)
    for reason in result['reasons']:
        print(f"{reason['code']}: {reason['message']}", file=sys.stderr)
    return 0 if result['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
