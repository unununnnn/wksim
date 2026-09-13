"""Explicit single-experiment admission of pinned joint-proven builds; no launch."""
from pathlib import Path, PurePosixPath
import json

from .config import validate_config
from . import joint_profile

PROFILE_ID = 'independent_quad_dds_v1'
SCOPE = ('Pinned quad-X DDS builds passed three-waypoint independent public missions under retained source; '
         'current admission code is not flight evidence; not complete G2/Full acceptance')


def select_config(config):
    """Reject unsupported selectors and roots before inspecting build resources."""
    if not isinstance(config, dict) or config.get('runtime_profile') != PROFILE_ID:
        raise ValueError('Unknown independent runtime profile')
    normalized = validate_config({k: v for k, v in config.items() if k != 'runtime_profile'})
    if normalized.get('control_protocol') != 'session_v1':
        raise ValueError('Independent profile requires explicit session_v1')
    if normalized['capabilities'] != ['native_position_mission']:
        raise ValueError('Independent profile supports only native_position_mission')
    if normalized.get('restart_control_on_ground', False):
        raise ValueError('Independent profile ground control restart is not admitted')
    p = joint_profile.select_profile('joint_quad_dds_v1')
    expected = dict(dds_workspace=p['dds_workspace'], prometheus_workspace=p['control_workspace'],
                    px4_root=str(PurePosixPath(p['manifests']['px4']['path']).parent / 'src'),
                    model_library=p['model_library'])
    if normalized['stack'] == 'arducopter':
        expected['ap_candidate'] = str(PurePosixPath(p['manifests']['ap']['path']).parent)
    for key, value in expected.items():
        if key == 'model_library' and key not in normalized:
            normalized[key] = value
        elif normalized[key] != value:
            raise ValueError(key + ': resource is not the pinned independent candidate')
    return dict(normalized, runtime_profile=PROFILE_ID), p


def check_flight_evidence(stack, p, identities):
    """Bind historical single-flight proof to resources that passed current checks."""
    catalog = json.loads(Path(__file__).with_name('independent-profile-evidence.json').read_text())
    if catalog['schema_version'] != 1 or catalog['profile'] != PROFILE_ID:
        raise ValueError('Independent evidence catalog differs')
    audit = joint_profile._pinned_json(catalog['audit'])
    joint_profile._pinned_json(catalog['archive_manifest'])
    if joint_profile.digest(joint_profile.REPO/catalog['audit_source']['path']) != catalog['audit_source']['sha256']:
        raise ValueError('Independent audit source differs')
    row = catalog['runs'][stack]
    for name, expected in dict(catalog['sources'], **row['files']).items():
        if joint_profile.digest(joint_profile.REPO/name) != expected:
            raise ValueError('Independent retained evidence differs: ' + name)
    flight = joint_profile._pinned_json(row['result'])
    matches = [r for r in audit['runs'] if r['stack'] == stack]
    if audit['status'] != 'pass' or len(matches) != 1:
        raise ValueError('Independent audit did not pass')
    proof = matches[0]
    old = flight['preflight']['identities']
    key = 'ap' if stack == 'arducopter' else 'px4'
    selected, _ = select_config(flight['config'])
    if (selected['stack'] != stack or audit['audit_sha256'] != catalog['audit_source']['sha256']
            or proof['status'] != 'pass' or proof['result_sha256'] != row['result']['sha256']
            or flight['status'] != 'pass' or old['manifests'] != p['manifests']
            or any(old[name] != identities[name] for name in (key, 'model', stack+'_agent', 'message_packages'))
            or proof['firmware_sha256'] != identities[key]['sha256']
            or proof['model_sha256'] != identities['model']['library_sha256']):
        raise ValueError('Independent flight does not match admitted resources')
    return dict(run_id=flight['run_id'], result_sha256=row['result']['sha256'],
                audit_sha256=catalog['audit']['sha256'], source_mode='retained-source-audit',
                current_admission_code_flown=False, scope=SCOPE)


def check_profile(config):
    """Return current resource admission and explicitly historical flight provenance."""
    result = dict(ok=False, reasons=[], identities={}, capabilities=[], children_created=0,
                  scope=SCOPE, candidate_status=dict(implemented=True, built=False, flown=False,
                                                    scope=SCOPE))
    try:
        normalized, p = select_config(config)
        result['config'] = normalized
        stack = normalized['stack']
        checked = joint_profile.check_resources(p, stacks=(stack,))
        result.update(checked)
        result['scope'] = SCOPE
        result['candidate_status']['built'] = checked['ok']
        result['control_profile'] = 'session_v1'
        result['setup_files'] = list(p['setup_files'])
        result['capabilities'] = [dict(id='native_position_mission', admitted=checked['ok'],
                                      implemented=True, built=checked['ok'], flown=False, reason=SCOPE)]
        if checked['ok']:
            if normalized.get('promotion_flight', False):
                result['flight_provenance'] = 'promotion_flight'
            else:
                result['flight_provenance'] = check_flight_evidence(stack, p, result['identities'])
                result['candidate_status']['flown'] = True
                result['capabilities'][0]['flown'] = True
            identities = result['identities']
            firmware = identities['ap' if stack == 'arducopter' else 'px4']
            identities['firmware'] = dict(firmware, expected_sha256=firmware['sha256'], match=True)
            identities['firmware_commit'] = firmware['commit']
            agent = identities[stack + '_agent']
            identities['agent'] = dict(agent, expected_sha256=agent['sha256'], match=True)
            model = identities['model']
            identities['model_build'] = model
            identities['model_library'] = dict(path=checked['model_library'],
                                              sha256=model['library_sha256'],
                                              expected_sha256=model['library_sha256'], match=True)
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        result['ok'] = False
        for capability in result['capabilities']:
            capability['admitted'] = False
        result['reasons'].append(dict(code='independent_profile_rejected', message=str(error)))
    return result
