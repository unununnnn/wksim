"""Read-only Linux candidate admission. No FC, ROS node, compiler or child process."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import stat
import sys

from .config import ConfigError, load_config, validate_config

REPO = Path(__file__).resolve().parents[2]
INDEX = Path(__file__).with_name('capability-index.json')


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
        for key in ('fc_binary', 'fc_binary_sha256', 'fc_commit', 'agent_sha256'):
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


def preflight(config):
    """Return JSON-safe evidence; ok is candidate admission, never flight readiness."""
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
        for key in ('display_socket', 'telemetry_socket'):
            if key not in config:
                continue
            socket = Path(config[key])
            parent = socket.parent
            if parent.is_symlink() or parent.resolve() != parent:
                reject(key + '_invalid', 'Consumer directory must not resolve through a symlink')
            if parent.exists():
                mode = parent.stat()
                if not parent.is_dir() or mode.st_uid != os.getuid() or stat.S_IMODE(mode.st_mode) != 0o700:
                    reject(key + '_invalid', 'Consumer directory must be owned by current UID with mode 0700')
            if socket.is_symlink() or (socket.exists() and not stat.S_ISSOCK(socket.stat().st_mode)):
                reject(key + '_invalid', 'Consumer receiver must be a Unix socket, not a regular file or symlink')
            if key == 'telemetry_socket' and socket.exists():
                info = socket.stat()
                if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                    reject(key + '_invalid', 'Telemetry receiver must be owned by current UID with mode 0600')
        if 'telemetry_socket' in config:
            from .telemetry_dialect import load_dialect
            _, result['identities']['telemetry_decoder'] = load_dialect(config['stack'])
        release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
        if release.get('ID', '').strip('"') != 'ubuntu' or release.get('VERSION_ID', '').strip('"') != '22.04':
            reject('unsupported_platform', 'Only Ubuntu 22.04 has a pinned environment')
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
            if roots[key] != Path(expected).resolve(strict=True):
                reject('candidate_not_pinned', f'{key}: {roots[key]} is not the reviewed resource {expected}')
        firmware = (roots['ap_candidate'] / 'build/sitl/bin/arducopter' if stack == 'arducopter'
                    else roots['px4_root'] / 'build/px4_sitl_default/bin/px4')
        check_file('firmware', firmware, evidence['fc_binary_sha256'])
        if not os.access(firmware, os.X_OK):
            reject('resource_not_executable', f'Firmware is not executable: {firmware}')
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
        library = Path(config.get('model_library', model['library']))
        config['model_library'] = str(library.resolve())
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
        for file, expected in evidence['prometheus']['implementation_sha256'].items():
            check_file('prometheus/' + file, package_root / file, expected)
        if protocol == 'session_v1':
            expected_files = set(evidence['prometheus']['implementation_sha256'])
            actual_files = {p.relative_to(package_root).as_posix() for p in package_root.rglob('*.py')}
            if actual_files != expected_files:
                reject('identity_mismatch', 'Installed control Python file set differs from both flown results')
            source_root = roots['prometheus_workspace'] / 'src/prometheus_control/prometheus_control'
            for file, expected in evidence['prometheus']['implementation_sha256'].items():
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
        result['candidate_status']['flown'] = result['ok']
    except ConfigError as error:
        reject('invalid_config', error)
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
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
