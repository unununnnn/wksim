"""Fail-closed classifier for a #33 mixed/PV evidence packet.

The tool only reads committed contracts: the ``joint_profile`` catalog rows, the
committed mixed/PV proof chain (``joint_profile._mixed_proofs``, driven through
a narrow adapter that feeds it the packet's own declared resources), and the
FINAL AP/control/message pins in ``ap_mixed_candidate``.  It never launches
ROS/FC/native/model/UE/MATLAB, never binds catalog evidence, never verifies the
catalog candidate files, and never claims that issue #33 or #84 is accepted.

``current_combo_not_accepted`` is emitted only after the packet satisfies the
whole committed binding chain: retained raw evidence maps, result/audit/admission
identity, the admission file inside the result root, manifests, candidate and
control candidate records, the explicit message proof, the executed source seal,
PX4/model identity, and the dual-capability argv.  Every other outcome is a
rejection.

``--directory`` takes a packet directory that holds one run directory
(``result.json``, ``audit.json``, ``experimental-admission.json``) per mixed/PV
task; a single run directory is genuinely incomplete evidence, not a combo.

Exit codes: 0 = the packet was classified as matching the committed FINAL combo
shape (it is still never accepted); 2 = every rejected classification and every
usage error.

An empty ``--packet``/``--directory`` argument, and JSON too deeply nested to
traverse, are rejected as ``malformed_identity`` with exit code 2; they are never
treated as the current working directory and never crash.
"""
import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import re
import sys

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from Simulator.wksim_runtime import joint_profile as joint
from Simulator.wksim_runtime.config import ConfigError, _invalid_constant, _unique_object


SCHEMA = 'wksim.33-mixed-packet-classification.v2'
CLASSIFIED = 'current_combo_not_accepted'
EXIT_CLASSIFIED = 0
EXIT_REJECTED = 2
DIAGNOSTIC_MARKERS = ('rate_timing_probe', 'group_work_timing', 'perf_switch_capture')
PIN_KEYS = frozenset(('task_profile', 'result', 'audit', 'admission'))
RUN_FILES = {
    'result': 'result.json',
    'audit': 'audit.json',
    'admission': 'experimental-admission.json',
}
SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
# Deeply nested JSON is rejected instead of traversed: the non-finite walk below
# and ``json.loads`` both recurse, and a depth cap keeps the tool fail-closed at
# exit 2 rather than surfacing a RecursionError traceback.
MAX_JSON_DEPTH = 256


class _AbsentIdentity(ValueError):
    """A required identity field is missing; absence is never a match."""


def _literals(relative):
    tree = ast.parse((REPO / relative).read_text(encoding='utf-8'))
    values = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            values[node.targets[0].id] = node.value.value
    return values


_MIXED_SRC = _literals('tools/ap_mixed_candidate.py')
_AUDIT_SRC = _literals('tools/audit_mixed_control.py')
FINAL_AP_SHA = _MIXED_SRC['FINAL_AP_SHA']
FINAL_CONTROL_SHA = _MIXED_SRC['FINAL_CONTROL_SHA']
FINAL_MESSAGE_SHA = _MIXED_SRC['FINAL_MESSAGE_SHA']
LEGACY_CONTROL_SHA = _MIXED_SRC['LEGACY_CONTROL_SHA']
HISTORICAL_PV_CONTROL_SHA = _AUDIT_SRC['HISTORICAL_PV_CONTROL_SHA']
PREVIOUS_PV_CONTROL_SHA = _AUDIT_SRC['PREVIOUS_PV_CONTROL_SHA']
PV_FIRMWARE_SHA = _AUDIT_SRC['PV_SHA']


def _reject_nonfinite(value):
    """Iterative non-finite walk with an explicit depth cap (never recurses)."""
    stack = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            raise ValueError('JSON nesting depth exceeds %d' % MAX_JSON_DEPTH)
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError('non-finite JSON number')
        elif isinstance(item, dict):
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)


def _parse_json_text(text):
    try:
        value = json.loads(text, object_pairs_hook=_unique_object,
                           parse_constant=_invalid_constant)
        _reject_nonfinite(value)
        return value
    except (ConfigError, json.JSONDecodeError, TypeError, ValueError, RecursionError) as error:
        raise ValueError('malformed JSON: ' + str(error)) from error


def _pinned_object(pin):
    """Committed pin identity plus strict UTF-8 / duplicate-key / non-finite JSON.

    ``joint._pinned_json`` remains the decisive production read of the pin
    descriptor.  The tool then re-reads exactly the bytes it will classify and
    re-verifies them against the pin digest, so bytes that changed after the
    production read are rejected instead of classified (second-read TOCTOU).
    """
    try:
        joint._pinned_json(pin)
    except RecursionError as error:
        raise ValueError('malformed JSON: ' + str(error)) from error
    path = Path(pin['path'])
    if not path.is_absolute():
        path = REPO / path
    try:
        raw = path.read_bytes()
        text = raw.decode('utf-8')
    except UnicodeError as error:
        raise ValueError('pinned JSON is not valid UTF-8') from error
    if hashlib.sha256(raw).hexdigest() != pin['sha256']:
        raise ValueError('Pinned SHA256 differs: ' + str(path))
    return _parse_json_text(text)


def _catalog_binding(identity):
    """Packet-derived equality between this packet's identity and the catalog."""
    manifests = joint.select_profile(joint.MIXED_PROFILE)['manifests']
    return {
        'ap_matches_catalog': identity.get('ap') == manifests['ap']['sha256'],
        'control_matches_catalog': identity.get('control') == manifests['control']['sha256'],
        'px4_matches_catalog': identity.get('px4') == manifests['px4']['sha256'],
    }


def _report(classification, reasons, combo=None, catalog_binding=None):
    mixed = joint.select_profile(joint.MIXED_PROFILE)
    legacy = joint.select_profile(joint.LEGACY_PROFILE)
    classified = classification == CLASSIFIED
    return {
        'schema': SCHEMA,
        'status': 'classified_not_accepted' if classified else 'rejected',
        'classification': classification,
        'acceptance_eligible': False,
        'issue_33_accepted': False,
        'issue_84_accepted': False,
        'exit_code': EXIT_CLASSIFIED if classified else EXIT_REJECTED,
        # Catalog-row property only: never a statement about this packet.
        'catalog_has_evidence_rows': len(mixed['evidence']) == len(joint.MIXED_TASKS),
        # Packet-specific binding of this packet's identity to the catalog pins.
        'packet_catalog_binding': dict(catalog_binding or {}),
        'reasons': [str(item) for item in reasons],
        'combo': dict(combo or {}),
        'contracts': {
            'mixed_profile': joint.MIXED_PROFILE,
            'legacy_profile': joint.LEGACY_PROFILE,
            'final_ap': FINAL_AP_SHA,
            'final_control': FINAL_CONTROL_SHA,
            'final_message': FINAL_MESSAGE_SHA,
            'catalog_ap': mixed['manifests']['ap']['sha256'],
            'catalog_control': mixed['manifests']['control']['sha256'],
            'catalog_px4': mixed['manifests']['px4']['sha256'],
            'catalog_evidence_count': len(mixed['evidence']),
            'legacy_ap': legacy['manifests']['ap']['sha256'],
            'legacy_control': legacy['manifests']['control']['sha256'],
        },
        'verification': {
            'proof_chain': 'Simulator.wksim_runtime.joint_profile._mixed_proofs',
            'proof_chain_resources': 'packet-declared admission records',
            'catalog_candidates_verified': False,
            'launches': [],
        },
    }


def _historical_sets():
    mixed = joint.select_profile(joint.MIXED_PROFILE)
    legacy = joint.select_profile(joint.LEGACY_PROFILE)
    controls = {
        legacy['manifests']['control']['sha256'],
        LEGACY_CONTROL_SHA,
        HISTORICAL_PV_CONTROL_SHA,
        PREVIOUS_PV_CONTROL_SHA,
    }
    if mixed['manifests']['control']['sha256'] != FINAL_CONTROL_SHA:
        controls.add(mixed['manifests']['control']['sha256'])
    aps = {
        legacy['manifests']['ap']['sha256'],
        PV_FIRMWARE_SHA,
    }
    if mixed['manifests']['ap']['sha256'] != FINAL_AP_SHA:
        aps.add(mixed['manifests']['ap']['sha256'])
    return aps, controls


def _looks_like_pin(value):
    if not isinstance(value, dict):
        return False
    for key in ('result', 'audit', 'admission'):
        item = value.get(key)
        if not (isinstance(item, dict) and set(item) == {'path', 'sha256'}):
            return False
    return 'task_profile' in value


def _capability(task):
    if task == joint.MIXED_TASKS[0]:
        return dict(profile=task, position_axes='xyz', velocity_axes='xyz', yaw=True,
                    acceleration=False, yaw_rate=False, mixed_axes=False,
                    arducopter_type_mask=2496)
    if task == joint.MIXED_TASKS[1]:
        return dict(profile=task, position_axes='z', velocity_axes='xy', yaw=True,
                    yaw_rate=False, acceleration=False, terrain=False,
                    arducopter_type_mask=2531, native_submode=7,
                    vertical_velocity_avoidance=False)
    return None


def _load_pin(pin):
    if not isinstance(pin, dict) or set(pin) != PIN_KEYS:
        raise ValueError('Mixed capability proof descriptor schema differs')
    if not isinstance(pin['task_profile'], str) or not pin['task_profile']:
        raise ValueError('task_profile must be a non-empty string')
    flight, audit, admission = (_pinned_object(pin[key])
                                for key in ('result', 'audit', 'admission'))
    if not isinstance(flight, dict) or not isinstance(audit, dict) or not isinstance(admission, dict):
        raise ValueError('result/audit/admission must be JSON objects')
    return flight, audit, admission


def _manifest_sha(value, label):
    if value is None:
        raise _AbsentIdentity(label + ' is absent')
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ValueError(label + ' must be a 64-hex SHA256 string')
    return value


def _identity(flight, audit, admission):
    """Read the packet identity; absence of any required field is a rejection."""
    manifests = flight.get('manifest_sha256')
    if not isinstance(manifests, dict):
        raise _AbsentIdentity('result.manifest_sha256 is absent')
    ap = _manifest_sha(manifests.get('ap'), 'result.manifest_sha256.ap')
    control = _manifest_sha(manifests.get('control'), 'result.manifest_sha256.control')
    message = _manifest_sha(manifests.get('message'), 'result.manifest_sha256.message')
    if ap != _manifest_sha(admission.get('manifest_sha256'), 'admission.manifest_sha256'):
        raise ValueError('admission AP manifest differs from the flown result')
    if control != _manifest_sha(admission.get('control_manifest_sha256'),
                               'admission.control_manifest_sha256'):
        raise ValueError('admission control manifest differs from the flown result')
    if message != _manifest_sha(admission.get('message_manifest_sha256'),
                                'admission.message_manifest_sha256'):
        raise ValueError('admission message manifest differs from the flown result')
    run_id, scene_epoch = flight.get('run_id'), flight.get('scene_epoch')
    if (not isinstance(run_id, str) or not run_id
            or not isinstance(scene_epoch, str) or not scene_epoch):
        raise _AbsentIdentity('result.run_id/scene_epoch is absent')
    audit_run, audit_epoch = audit.get('run_id'), audit.get('scene_epoch')
    if (not isinstance(audit_run, str) or not audit_run
            or not isinstance(audit_epoch, str) or not audit_epoch):
        raise _AbsentIdentity('audit.run_id/scene_epoch is absent')
    if audit_run != run_id or audit_epoch != scene_epoch:
        raise ValueError('Mixed/PV audit run identity differs from the flown result')
    identities = admission.get('identities')
    baseline = identities.get('baseline') if isinstance(identities, dict) else None
    if not isinstance(baseline, dict):
        raise _AbsentIdentity('admission.identities.baseline is absent')
    pinned = baseline.get('manifests')
    descriptor = pinned.get('px4') if isinstance(pinned, dict) else None
    if not isinstance(descriptor, dict):
        raise _AbsentIdentity('admission.identities.baseline.manifests.px4 is absent')
    px4_identity = baseline.get('px4')
    if not isinstance(px4_identity, dict):
        raise _AbsentIdentity('admission.identities.baseline.px4 is absent')
    px4 = _manifest_sha(px4_identity.get('sha256'), 'baseline.px4.sha256')
    if descriptor.get('sha256') != px4 or descriptor.get('path') != px4_identity.get('path'):
        raise ValueError('PX4 identity contradicts its pinned manifest descriptor')
    return {'ap': ap, 'control': control, 'message': message, 'px4': px4}


def _markers(flight):
    if not isinstance(flight, dict):
        return ()
    return tuple(name for name in DIAGNOSTIC_MARKERS if name in flight)


def _combo_class(identity):
    historical_ap, historical_control = _historical_sets()
    catalog_px4 = joint.select_profile(joint.MIXED_PROFILE)['manifests']['px4']['sha256']
    if identity['ap'] in historical_ap or identity['control'] in historical_control:
        return 'historical_combo'
    if identity['ap'] != FINAL_AP_SHA or identity['control'] != FINAL_CONTROL_SHA:
        return 'wrong_combo'
    if identity['message'] != FINAL_MESSAGE_SHA:
        return 'wrong_combo'
    if identity['px4'] != catalog_px4:
        return 'wrong_combo'
    return 'current'


def _combo_reason(kind):
    if kind == 'historical_combo':
        return 'historical AP/control identity'
    if kind == 'wrong_combo':
        return 'identity is not the committed FINAL mixed/PV combo'
    return ('packet matches the committed FINAL combo shape, but catalog evidence is '
            'unbound and #33/#84 remain unaccepted')


def _proof_chain(loaded):
    """Run the committed mixed/PV proof chain over packet-declared resources.

    ``joint_profile._mixed_proofs`` is the committed contract.  In production it
    receives records verified from the catalog candidate files; here those
    records are the packet's own admission declarations, so the chain proves the
    packet-internal binding (retained raw evidence, result/audit/admission/root,
    manifests, candidate/control candidate, message, executed source, PX4/model,
    dual-capability argv) and explicitly does not prove catalog candidate content.
    """
    catalog = joint.select_profile(joint.MIXED_PROFILE)
    admission, identity = loaded[0][3], loaded[0][4]
    control = admission.get('control_candidate')
    candidate = admission.get('candidate')
    native = admission.get('candidate_verification')
    baseline = admission['identities']['baseline']
    for label, value in (('admission.candidate', candidate),
                         ('admission.control_candidate', control),
                         ('admission.candidate_verification', native),
                         ('admission.identities.baseline.px4', baseline.get('px4'))):
        if not isinstance(value, dict):
            raise ValueError(label + ' is absent')
    for label, path, name in (('admission.manifest_path', admission.get('manifest_path'),
                               'mixed-build.json'),
                              ('admission.control_manifest_path',
                               admission.get('control_manifest_path'), 'build.json')):
        if not isinstance(path, str) or Path(path).name != name:
            raise ValueError(label + ' must name the committed ' + name)
    pinned_ap = catalog['manifests']['ap']
    if identity['ap'] == pinned_ap['sha256'] and admission.get('manifest_path') != pinned_ap['path']:
        raise ValueError('Committed mixed AP manifest path differs from its pinned descriptor')
    profile = dict(catalog)
    profile['evidence'] = [item[0] for item in loaded]
    profile['manifests'] = {
        'ap': {'path': admission.get('manifest_path'), 'sha256': identity['ap']},
        'control': {'path': admission.get('control_manifest_path'), 'sha256': identity['control']},
        'px4': catalog['manifests']['px4'],
    }
    records = {'ap': candidate, 'control': control}
    identities = {'ap_mixed': native, 'px4': baseline['px4']}
    joint._mixed_proofs(profile, records, identities)


def _classify_pins(pins):
    loaded = []
    for pin in pins:
        try:
            flight, audit, admission = _load_pin(pin)
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, RecursionError) as error:
            return _report('malformed_identity', [error])
        markers = _markers(flight)
        if markers:
            return _report('diagnostic_marker',
                           ['Formal mixed/PV evidence cannot include ' + name
                            for name in markers])
        try:
            identity = _identity(flight, audit, admission)
        except _AbsentIdentity as error:
            return _report('missing_identity', [error])
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            return _report('malformed_identity', [error])
        loaded.append((pin, flight, audit, admission, identity))
    if len(loaded) != len(joint.MIXED_TASKS):
        return _report('incomplete_evidence',
                       ['final mixed/PV proof requires both task capabilities; '
                        '%d evidence pin(s) supplied' % len(loaded)],
                       loaded[0][4] if loaded else None,
                       _catalog_binding(loaded[0][4]) if loaded else None)
    tasks = {item[0]['task_profile'] for item in loaded}
    if tasks != set(joint.MIXED_TASKS):
        return _report('incomplete_evidence',
                       ['evidence task_profile set differs from MIXED_TASKS'],
                       loaded[0][4], _catalog_binding(loaded[0][4]))
    identities = [item[4] for item in loaded]
    if any(item != identities[0] for item in identities[1:]):
        return _report('wrong_combo',
                       ['Mixed/PV capability proofs use different resources'],
                       identities[0], _catalog_binding(identities[0]))
    identity = identities[0]
    binding = _catalog_binding(identity)
    kind = _combo_class(identity)
    if kind != 'current':
        return _report(kind, [_combo_reason(kind)], identity, binding)
    try:
        _proof_chain(loaded)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError,
            RecursionError) as error:
        return _report('incomplete_evidence', [error], identity, binding)
    return _report(CLASSIFIED, [_combo_reason(kind)], identity, binding)


def classify(packet):
    """Classify a packet object, JSON text, or pin/bundle dictionary."""
    try:
        if isinstance(packet, (bytes, bytearray)):
            packet = packet.decode('utf-8')
        if isinstance(packet, str):
            packet = _parse_json_text(packet)
        if not isinstance(packet, dict):
            raise ValueError('packet must be a JSON object')
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as error:
        return _report('malformed_identity', [error])
    if 'evidence' in packet:
        if not isinstance(packet['evidence'], list):
            return _report('malformed_identity', ['evidence must be a list'])
        return _classify_pins(packet['evidence'])
    if _looks_like_pin(packet):
        return _classify_pins([packet])
    if {'result', 'audit', 'admission'} <= set(packet):
        return _report('missing_identity', ['inline packet has no pinned identity'])
    return _report('malformed_identity', ['unrecognized packet schema'])


def classify_path(path):
    if isinstance(path, str):
        if not path:
            return _report('malformed_identity', ['packet path is empty'])
    elif not isinstance(path, Path):
        return _report('malformed_identity', ['packet path must be a filesystem path'])
    try:
        raw = Path(path).read_text(encoding='utf-8')
    except (OSError, UnicodeError) as error:
        return _report('malformed_identity', [error])
    return classify(raw)


def _run_directories(root):
    found = []
    for pattern in ('', '*', '*/*'):
        candidates = [root] if not pattern else sorted(root.glob(pattern))
        for candidate in candidates:
            if (candidate.is_dir()
                    and all((candidate / name).is_file() for name in RUN_FILES.values())):
                found.append(candidate)
    return [item for item in found
            if not any(other != item and item.is_relative_to(other) for other in found)]


def classify_directory(directory):
    """Classify a packet directory holding one run directory per mixed/PV task."""
    if isinstance(directory, str):
        if not directory:
            return _report('malformed_identity', ['packet directory is empty'])
    elif not isinstance(directory, Path):
        return _report('malformed_identity', ['packet directory must be a filesystem path'])
    root = Path(directory)
    if not root.is_dir():
        return _report('malformed_identity', ['packet directory is absent: ' + str(directory)])
    root = root.resolve()
    runs = _run_directories(root)
    if not runs:
        return _report('incomplete_evidence',
                       ['final mixed/PV proof requires both task capabilities; no run directory '
                        'with result.json/audit.json/experimental-admission.json under ' + str(root)])
    by_task = {}
    for run in runs:
        if run.is_symlink() or run.resolve(strict=True) != run:
            return _report('malformed_identity',
                           ['run directory must not resolve through a symlink: ' + str(run)])
        try:
            flight = _parse_json_text((run / RUN_FILES['result']).read_text(encoding='utf-8'))
        except (OSError, UnicodeError, ValueError, RecursionError) as error:
            return _report('malformed_identity', [error])
        task = flight.get('task_profile') if isinstance(flight, dict) else None
        if not isinstance(task, str) or not task:
            return _report('missing_identity', ['result.task_profile is absent in ' + str(run)])
        if task in by_task:
            return _report('incomplete_evidence',
                           ['duplicate run directories for task_profile ' + task])
        by_task[task] = run
    missing = [task for task in joint.MIXED_TASKS if task not in by_task]
    unexpected = sorted(set(by_task) - set(joint.MIXED_TASKS))
    if missing or unexpected:
        return _report('incomplete_evidence',
                       ['final mixed/PV proof requires both task capabilities; exactly one run '
                        'directory per mixed/PV task; missing=' + repr(missing)
                        + ' unexpected=' + repr(unexpected)])
    pins = []
    for task in joint.MIXED_TASKS:
        run = by_task[task]
        pins.append({
            'task_profile': task,
            'result': {'path': str(run / RUN_FILES['result']),
                       'sha256': joint.digest(run / RUN_FILES['result'])},
            'audit': {'path': str(run / RUN_FILES['audit']),
                      'sha256': joint.digest(run / RUN_FILES['audit'])},
            'admission': {'path': str(run / RUN_FILES['admission']),
                          'sha256': joint.digest(run / RUN_FILES['admission'])},
        })
    return _classify_pins(pins)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Exit codes: 0 = classified as the committed FINAL combo shape (never accepted); '
               '2 = rejected classification or usage error.')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--packet', help='JSON pin or evidence bundle')
    source.add_argument('--directory', help='packet directory holding one run directory '
                        '(result.json, audit.json, experimental-admission.json) per mixed/PV task')
    parser.add_argument('--output', help='optional LF JSON report path')
    args = parser.parse_args(argv)
    # Branch on presence, not truthiness: ``--packet ""`` must be a rejection
    # report, never a silent fall-through to ``classify_directory(None)``.
    if args.packet is not None:
        report = classify_path(args.packet)
    else:
        report = classify_directory(args.directory)
    text = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.output:
        Path(args.output).write_text(text, encoding='utf-8', newline='\n')
    else:
        sys.stdout.write(text)
    return report['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
