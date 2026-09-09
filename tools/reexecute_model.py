#!/usr/bin/env python3
"""#114: bounded cold native reexecution, never a state replay.

CLI: import --source DIR --output NEW_DIR; run --input DIR --library SO
--output NEW_DIR; audit --input DIR --run DIR --output NEW_JSON.
The ticket-approved filename supersedes the draft reexecute_physics.py name.
Schema details are executable below; #113's numerical budget remains zero.
Only a sealed static independent source is supported. Hashes bind bytes, not
the truthfulness of a capture: source provenance still requires #115 review.
"""
import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Simulator'))
from wksim_core.model_parameters import (ConfiguredModel, RAW_HASHES, SOURCE,
    WRAPPER_HASH, canonical, parameterize_source, validate)

SCHEMA = 'wksim.physics-reexecution.v1'
PROFILE = 'quad-mass-cold-post-step-v1'
CONTRACT = '54c93d120a9745bb9466b2b4279bafa0701b7b3c706f3728574a5797c719fac1'
DT = 1_000_000
MAX_TICKS = 100_000
MAX_BYTES = 256 * 1024 * 1024
SEEDS = {'S246.Number1': [12233, 645554, 678766],
         'S246.Number2': [3243, 44556, 2334343],
         'S246.Number3': [45465, 454534, 1234232],
         'S246.Number': [15634], 'S246.Number4': [25634],
         'S245.Number2': [1452, 787, 69], 'S245.Number4': [5445, 45433, 33433]}
CORE = {'config.json', 'inputs.jsonl', 'expected.jsonl', 'events.jsonl', 'terminal.json'}
BUILD_FILES = {*RAW_HASHES, 'Exp1_MinModelTemp.original.cpp', 'configured_wrapper.cpp',
               'libwksim_configured.so', 'config.json', 'build.json', 'builder.py', 'model.py', 'archive.zip'}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def equal(a, b):
    return canonical(a) == canonical(b)


def fields(obj, names, where):
    require(type(obj) is dict and set(obj) == set(names.split()), 'fields: ' + where)


def decode(data):
    def pairs(items):
        obj = {}
        for k, v in items:
            require(k not in obj, 'duplicate JSON key: ' + k)
            obj[k] = v
        return obj
    def constant(s):
        raise ValueError('nonfinite: ' + s)
    def number(s):
        v = float(s)
        require(math.isfinite(v), 'nonfinite number')
        return v
    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant, parse_float=number)


def read(path):
    path = Path(path)
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink: ' + str(path))
    before = path.stat()
    require(path.is_file() and before.st_size <= MAX_BYTES, 'file size/type: ' + str(path))
    data = path.read_bytes()
    after = path.stat()
    require((before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_ino, after.st_size, after.st_mtime_ns) and len(data) == after.st_size,
            'file changed: ' + str(path))
    return data


def member_path(name):
    require(type(name) is str and name and '\\' not in name and ':' not in name,
            'invalid member path')
    p = PurePosixPath(name)
    require(not p.is_absolute() and '..' not in p.parts and str(p) == name,
            'absolute/escaping/noncanonical member')
    return name


def rows(data):
    require(not data or data.endswith(b'\n'), 'truncated JSONL')
    return [decode(line) for line in data.splitlines()]


def descriptor(data, name):
    sequence = rows(data) if name.endswith('.jsonl') else [decode(data)] if name.endswith('.json') else []
    key = 'event_seq' if name == 'events.jsonl' else 'tick'
    return {'bytes': len(data), 'sha256': sha(data), 'records': len(sequence),
            'first': sequence[0].get(key) if sequence else None,
            'last': sequence[-1].get(key) if sequence else None}


def vector(values, length, where):
    require(type(values) is list and len(values) == length, 'vector length: ' + where)
    for x in values:
        require(type(x) in (int, float), 'non-number: ' + where)
        try:
            require(math.isfinite(x), 'nonfinite: ' + where)
        except OverflowError as error:
            raise ValueError('number overflow: ' + where) from error


def initialization(config):
    return {'mode': 'cold_initialize_at_tick_zero', 'tick': 0,
            'order': ['construct', 'initialize', 'zero_ExtU'],
            'config_identity': config['model_identity'],
            'internal_state': 'full_X_DW_solver_filters_delays_counters_from_same_build_initialize'}


def randomness():
    return {'algorithm': 'rt_urand_Upu32_Yd_f_pw_snf', 'multiplier': 16807,
            'modulus': 2147483647, 'seeds': SEEDS,
            'algorithm_source_sha256': RAW_HASHES['Exp1_MinModelTemp.cpp'],
            'consumption': 'generated_initialize_and_step_order', 'os_seed_injection': False}


def identity(row, manifest):
    for key in ('scene_epoch', 'instance_id'):
        require(equal(row[key], manifest[key]), 'cross-generation identity: ' + key)


def load_bundle(directory):
    root = Path(directory)
    require(root.is_dir(), 'insufficient_recording: source must be a sealed directory')
    raw = {'manifest.json': read(root / 'manifest.json')}
    m = decode(raw['manifest.json'])
    fields(m, 'schema profile source_run_id scene_epoch instance_id source_capture_revision '
           'contract_sha256 config_identity build_identity initialization randomness time '
           'input_encoding output_phase event_policy members', 'manifest')
    require(m['schema'] == SCHEMA and m['profile'] == PROFILE, 'unsupported_profile')
    require(m['contract_sha256'] == CONTRACT and sha(read(ROOT / 'docs/plan/46-reexecution-contract.md')) == CONTRACT,
            'contract identity')
    for key in ('source_run_id', 'scene_epoch', 'instance_id', 'source_capture_revision'):
        require(type(m[key]) is str and bool(re.fullmatch(r'[A-Za-z0-9._-]{1,128}', m[key])), 'identity: ' + key)
    require(type(m['members']) is dict and CORE <= m['members'].keys() and len(m['members']) <= 64,
            'insufficient_recording: members')
    for name, desc in m['members'].items():
        member_path(name)
        require(name != 'manifest.json', 'self member')
        raw[name] = read(root / name)
        require(sum(map(len, raw.values())) <= MAX_BYTES, 'bundle exceeds bounded memory limit')
        require(equal(desc, descriptor(raw[name], name)), 'member identity: ' + name)
    listed = {str(p.relative_to(root).as_posix()) for p in root.rglob('*') if p.is_file() or p.is_symlink()}
    require(listed == set(raw), 'unlisted/duplicate member')
    require(sum(map(len, raw.values())) <= MAX_BYTES, 'bundle exceeds bounded memory limit')
    config = validate(decode(raw['config.json']))
    require(m['config_identity'] == config['model_identity'], 'config identity')
    require(equal(m['initialization'], initialization(config)), 'missing/unsupported initial state')
    require(equal(m['randomness'], randomness()), 'seed/consumption identity')
    require(m['input_encoding'] == 'per_tick_binary64' and m['output_phase'] == 'post_step_api', 'encoding/phase')
    fields(m['time'], 'first_tick last_tick dt_ns', 'time')
    n = m['time']['last_tick']
    require(type(n) is int and 1 <= n <= MAX_TICKS and equal(m['time'],
            {'first_tick': 1, 'last_tick': n, 'dt_ns': DT}), 'time interval')
    require(equal(m['event_policy'], {'mode': 'explicit_none', 'count': 0}), 'unsupported_event')
    require(raw['events.jsonl'] == b'', 'unsupported_event')
    inputs, expected = rows(raw['inputs.jsonl']), rows(raw['expected.jsonl'])
    require(len(inputs) == n and len(expected) == n, 'missing interval: input/output count')
    for tick, (inp, out) in enumerate(zip(inputs, expected), 1):
        fields(inp, 'scene_epoch instance_id tick before_ns after_ns inPWMs TerrainIn15d source_ref event_frontier', 'input')
        fields(out, 'scene_epoch instance_id tick output_phase output120', 'expected')
        for row in (inp, out):
            identity(row, m)
            require(type(row['tick']) is int and row['tick'] == tick, 'missing/duplicate/ordered interval at tick ' + str(tick))
        require(equal([inp['before_ns'], inp['after_ns'], inp['event_frontier']],
                      [(tick - 1) * DT, tick * DT, 0]), '1ms/event frontier at tick ' + str(tick))
        vector(inp['inPWMs'], 16, 'actuators')
        vector(inp['TerrainIn15d'], 15, 'terrain')
        require(all(0 <= v <= 1 for v in inp['inPWMs']) and not any(inp['inPWMs'][4:]), 'actuator bounds')
        require(not any(inp['TerrainIn15d']), 'unsupported terrain input')
        ref = inp['source_ref']
        require(type(ref) is str and ref in raw and ref not in CORE and ref != 'manifest.json', 'missing source_ref')
        plan = decode(raw[ref])
        fields(plan, 'kind first_tick last_tick inPWMs TerrainIn15d frozen_before_capture', 'static plan')
        require(equal(plan, dict(kind='static_experiment_plan', first_tick=1, last_tick=n,
                inPWMs=inp['inPWMs'], TerrainIn15d=inp['TerrainIn15d'], frozen_before_capture=True)), 'static plan mapping')
        require(out['output_phase'] == 'post_step_api', 'output phase')
        vector(out['output120'], 120, 'expected')
        require(abs(out['output120'][2] - tick * .001) <= 1e-8, 'expected engine time')
    terminal = decode(raw['terminal.json'])
    fields(terminal, 'source_status exit_code attempted returned emitted last_tick engine_end_ns '
           'event_frontier streams process last_confirmed_tick', 'terminal')
    completion = dict(source_status='complete', exit_code=0, attempted=n, returned=n, emitted=n,
                      last_tick=n, engine_end_ns=n*DT, event_frontier=0, last_confirmed_tick=n)
    require(equal({k: terminal[k] for k in completion}, completion), 'incomplete terminal/frontier')
    require(equal(terminal['streams'], {k: m['members'][k] for k in ('inputs.jsonl', 'expected.jsonl', 'events.jsonl')}), 'terminal streams')
    process = terminal['process']
    fields(process, 'pid boot_id starttime argv exited', 'source process')
    require(type(process['pid']) is int and process['pid'] > 0 and
            type(process['starttime']) is int and process['starttime'] > 0 and
            type(process['boot_id']) is str and bool(process['boot_id']) and
            type(process['argv']) is list and bool(process['argv']) and
            all(type(v) is str for v in process['argv']) and process['exited'] is True, 'source process identity')
    if sys.platform == 'linux' and process['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip():
        stat = Path('/proc') / str(process['pid']) / 'stat'
        if stat.exists():
            require(int(stat.read_text().rsplit(')', 1)[1].split()[19]) != process['starttime'], 'source still alive')
    build = m['build_identity']
    fields(build, 'source files dependencies platform', 'build identity')
    require(equal(build['source'], SOURCE), 'foreign model source')
    require(type(build['files']) is dict and set(build['files']) == BUILD_FILES and
            type(build['dependencies']) is dict and bool(build['dependencies']), 'build/dependency identities')
    for name, digest in build['files'].items():
        member_path(name)
        require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest), 'build hash')
    require(build['files']['archive.zip'] == SOURCE['archive_sha256'] and
            build['files']['Exp1_MinModelTemp.original.cpp'] == RAW_HASHES['Exp1_MinModelTemp.cpp'], 'archive/raw identity')
    require('build.json' in raw and sha(raw['build.json']) == build['files']['build.json'], 'missing sealed build receipt')
    for name, digest in build['dependencies'].items():
        require(type(name) is str and name.startswith('/') and type(digest) is str and
                re.fullmatch('[0-9a-f]{64}', digest), 'dependency identity')
    fields(build['platform'], 'system machine cpu libc python ctypes_bits rounding compiler', 'platform')
    for name in raw:
        require(read(root / name) == raw[name], 'source changed while importing: ' + name)
    return m, config, inputs, expected, raw


def platform_identity():
    require(sys.platform == 'linux', 'platform_comparison_unbudgeted: requires Linux')
    cpu = Path('/proc/cpuinfo').read_text()
    cpu = sorted(set(line.strip() for line in cpu.splitlines() if line.startswith(('vendor_id', 'model name', 'flags'))))
    libc = ctypes.CDLL(None)
    libc.fegetround.restype = ctypes.c_int
    return {'system': platform.platform(), 'machine': platform.machine(),
            'cpu': cpu, 'libc': list(platform.libc_ver()), 'python': sys.version,
            'ctypes_bits': ctypes.sizeof(ctypes.c_void_p)*8, 'rounding': libc.fegetround(),
            'compiler': subprocess.check_output(['g++', '--version'], text=True).splitlines()[0]}


def build_identity(library, config):
    """Read-only pinned-source/build check before CDLL/model initialization.

    ldd is called only on the exact caller-supplied local ELF shared library,
    never a command/path supplied by the input manifest.
    """
    library = Path(library)
    require(library.name == 'libwksim_configured.so', 'library filename')
    folder = library.parent
    data = read(library)
    require(data[:4] == b'\x7fELF', 'library is not ELF')
    build = decode(read(folder / 'build.json'))
    require(equal(build['config'], config) and equal(decode(read(folder / 'config.json')), config), 'build config')
    names = {*RAW_HASHES, 'Exp1_MinModelTemp.original.cpp', 'configured_wrapper.cpp', library.name, 'config.json'}
    require(set(build['files_sha256']) == names, 'build member set')
    actual = {name: sha(read(folder / name)) for name in names}
    require(equal(actual, build['files_sha256']), 'build artifact hash')
    original = read(folder / 'Exp1_MinModelTemp.original.cpp')
    require(sha(original) == RAW_HASHES['Exp1_MinModelTemp.cpp'], 'original source')
    require(read(folder / 'Exp1_MinModelTemp.cpp') == parameterize_source(original, config['mass']['value']), 'parameterized source')
    for name, digest in RAW_HASHES.items():
        if name.endswith('.h'):
            require(actual[name] == digest, 'header identity')
    wrapper = read(ROOT / 'Simulator/wksim_core/model.cpp')
    require(sha(wrapper) == WRAPPER_HASH, 'base wrapper')
    wrapper = wrapper.replace(b'    try {', b'    static bool used = false;\n    if (used) return nullptr;\n    used = true;\n    try {')
    wrapper += ('\nextern "C" double wk_configured_mass() { return MulticopterModelClass::Exp1_MinModelTemp_P.ModelParam_uavMass; }\n'
                'extern "C" const char* wk_configured_identity() { return "' + config['model_identity'] + '"; }\n').encode()
    require(read(folder / 'configured_wrapper.cpp') == wrapper, 'actual wrapper identity')
    require(not any(os.environ.get(k) for k in ('LD_PRELOAD', 'LD_LIBRARY_PATH', 'LD_AUDIT')), 'loader environment')
    deps = subprocess.check_output(['/usr/bin/ldd', str(library.resolve())], text=True, stderr=subprocess.STDOUT)
    require('not found' not in deps, 'missing dependency')
    paths = re.findall(r'(?:=>\s+|^\s*)(/\S+)\s+\(', deps, re.MULTILINE)
    require(bool(paths), 'dependency inspection')
    dependencies = {str(Path(p).resolve()): sha(read(Path(p).resolve())) for p in paths}
    actual['build.json'] = sha(read(folder / 'build.json'))
    actual['builder.py'] = sha(read(ROOT / 'Simulator/wksim_core/model_parameters.py'))
    actual['model.py'] = sha(read(ROOT / 'Simulator/wksim_core/model.py'))
    actual['archive.zip'] = sha(read(Path(build['archive'])))
    require(actual['archive.zip'] == SOURCE['archive_sha256'], 'archive identity')
    measured_platform = platform_identity()
    require(build['compiler'] == measured_platform['compiler'] and build['builder_sha256'] == actual['builder.py'], 'compiler/builder identity')
    # Paths in the historical build argv are retained, never executed. Require
    # the exact reviewed compilation recipe, including its link-only tail.
    argv = build['argv']
    require(type(argv) is list and len(argv) == 13 and
            argv[:8] == ['g++', '-std=c++17', '-O2', '-fno-fast-math', '-fPIC', '-shared', '-Wl,--no-undefined', '-I'] and
            argv[11] == '-o' and Path(argv[9]).name == 'Exp1_MinModelTemp.cpp' and
            Path(argv[10]).name == 'configured_wrapper.cpp' and Path(argv[12]).name == 'libwksim_configured.so', 'compiler argv')
    return {'source': SOURCE, 'files': actual, 'dependencies': dependencies, 'platform': measured_platform}


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(value, indent=2, allow_nan=False) + '\n')


def outside(output, source):
    require(not Path(output).resolve().is_relative_to(Path(source).resolve()), 'output must be outside source')


def import_bundle(source, output):
    outside(output, source)
    _, _, _, _, raw = load_bundle(source)
    Path(output).mkdir(parents=True, exist_ok=False)
    for name, data in raw.items():
        target = Path(output) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as f:
            f.write(data)
    return {'status': 'imported', 'manifest_sha256': sha(raw['manifest.json'])}


def execute(input_dir, library, output):
    outside(output, input_dir)
    m, config, inputs, _, raw = load_bundle(input_dir)
    measured = build_identity(library, config)
    require(equal(measured, m['build_identity']), 'platform/model/build identity mismatch')
    output = Path(output)
    write_json(output / 'request.json', {'manifest_sha256': sha(raw['manifest.json']),
               'tool_sha256': sha(read(Path(__file__))), 'library': str(Path(library).resolve()),
               'build_identity': measured, 'mode': 'native_physical_reexecution',
               'pid': os.getpid(), 'argv': sys.argv})
    attempted = returned = emitted = 0
    before_s = 0.0
    with (output / 'actual.jsonl').open('x', encoding='utf-8', newline='\n') as stream:
        with ConfiguredModel(library, config) as model:
            maps = Path('/proc/self/maps').read_text()
            require(str(Path(library).resolve()) in maps, 'actual loaded library mapping')
            for dependency in measured['dependencies']:
                require(dependency in maps, 'actual dependency mapping: ' + dependency)
            write_json(output / 'loaded.json', {'library': str(Path(library).resolve()),
                'library_sha256': sha(read(library)), 'dependencies': measured['dependencies'],
                'maps': maps, 'applied_mass_kg': model.applied_mass_kg})
            for inp in inputs:
                attempted += 1
                values = model.step(inp['inPWMs'], steps=1)
                returned += 1
                vector(values, 120, 'actual')
                row = {k: inp[k] for k in ('scene_epoch', 'instance_id', 'tick', 'before_ns', 'after_ns')}
                row.update(output_phase='post_step_api', output120=values,
                           engine_before_s=before_s, engine_after_s=values[2])
                stream.write(canonical(row) + '\n')
                emitted += 1
                before_s = values[2]
    require(equal(build_identity(library, config), measured), 'build changed during run')
    require(sha(read(Path(input_dir) / 'manifest.json')) == sha(raw['manifest.json']), 'manifest changed during run')
    write_json(output / 'terminal.json', {'status': 'recomputed', 'attempted': attempted,
        'returned': returned, 'emitted': emitted, 'last_tick': emitted, 'engine_end_ns': emitted*DT,
        'event_frontier': 0, 'manifest_sha256': sha(raw['manifest.json']),
        'actual_sha256': sha(read(output / 'actual.jsonl')),
        'request_sha256': sha(read(output / 'request.json')),
        'loaded_sha256': sha(read(output / 'loaded.json'))})


def run_bundle(input_dir, library, output):
    outside(output, input_dir)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    # Parent and child both validate before constructing the native model.
    try:
        m, config, _, _, _ = load_bundle(input_dir)
        require(equal(build_identity(library, config), m['build_identity']), 'platform/model/build identity mismatch')
        argv = [sys.executable, str(Path(__file__).resolve()), '_execute', '--input', str(Path(input_dir).resolve()),
                '--library', str(Path(library).resolve()), '--output', str(output.resolve())]
        with (output/'stdout.log').open('xb') as stdout, (output/'stderr.log').open('xb') as stderr:
            child = subprocess.run(argv, stdout=stdout, stderr=stderr, timeout=300)
        write_json(output/'process.json', {'argv': argv, 'exit_code': child.returncode})
        if child.returncode:
            return {'status': 'model_execution_failed', 'exit_code': child.returncode}, 1
        report = audit_bundle(input_dir, output)
        write_json(output/'audit.json', report)
        return report, 0 if report['status'] == 'reexecution_passed' else 1
    except (OSError, ValueError, KeyError, TypeError, OverflowError, subprocess.SubprocessError) as error:
        write_json(output/'failure.json', {'status': 'rejected', 'reason': str(error)})
        return {'status': 'rejected', 'reason': str(error)}, 2


def audit_bundle(input_dir, run_dir):
    m, _, inputs, expected, raw = load_bundle(input_dir)
    run = Path(run_dir)
    saved = {name: read(run/name) for name in ('request.json', 'loaded.json', 'actual.jsonl', 'terminal.json', 'process.json')}
    request, loaded, terminal, process = (decode(saved[n]) for n in ('request.json', 'loaded.json', 'terminal.json', 'process.json'))
    n = len(inputs)
    require(request['mode'] == 'native_physical_reexecution' and request['manifest_sha256'] == sha(raw['manifest.json']) and
            request['tool_sha256'] == sha(read(Path(__file__))) and equal(request['build_identity'], m['build_identity']), 'run request identity')
    require(loaded['library'] == request['library'] and loaded['library_sha256'] == m['build_identity']['files']['libwksim_configured.so'] and
            equal(loaded['dependencies'], m['build_identity']['dependencies']) and loaded['library'] in loaded['maps'], 'loaded identity')
    require(type(process['exit_code']) is int and process['exit_code'] == 0, 'child incomplete')
    require(equal(terminal, {'status': 'recomputed', 'attempted': n, 'returned': n, 'emitted': n,
        'last_tick': n, 'engine_end_ns': n*DT, 'event_frontier': 0, 'manifest_sha256': sha(raw['manifest.json']),
        'actual_sha256': sha(saved['actual.jsonl']), 'request_sha256': sha(saved['request.json']),
        'loaded_sha256': sha(saved['loaded.json'])}), 'run terminal identity/frontier')
    actual = rows(saved['actual.jsonl'])
    require(len(actual) == n, 'actual missing interval')
    slots = [{'slot': s, 'max_absolute': 0.0, 'max_relative': 0.0, 'failures': 0} for s in range(120)]
    failures, first = 0, None
    previous = 0.0
    for tick, (out, target) in enumerate(zip(actual, expected), 1):
        fields(out, 'scene_epoch instance_id tick before_ns after_ns output_phase output120 engine_before_s engine_after_s', 'actual')
        identity(out, m)
        require(equal([out['tick'], out['before_ns'], out['after_ns']], [tick, (tick-1)*DT, tick*DT]), 'actual interval')
        require(out['output_phase'] == 'post_step_api', 'actual phase')
        vector(out['output120'], 120, 'actual')
        vector([out['engine_before_s'], out['engine_after_s']], 2, 'engine times')
        require(out['engine_before_s'] == previous and out['engine_after_s'] == out['output120'][2] and
                abs(out['engine_after_s'] - tick*.001) <= 1e-8, 'actual engine time')
        previous = out['engine_after_s']
        for slot, (a, b) in enumerate(zip(out['output120'], target['output120'])):
            absolute = abs(a-b)
            relative = absolute/abs(b) if b else (0.0 if a == b else math.inf)
            metric = slots[slot]
            metric['max_absolute'] = max(metric['max_absolute'], absolute)
            metric['max_relative'] = max(metric['max_relative'], relative)
            if a != b:
                failures += 1
                metric['failures'] += 1
                if first is None:
                    first = {'tick': tick, 'slot': slot, 'source': b, 'recomputed': a}
    for metric in slots:
        for key in ('max_absolute', 'max_relative'):
            if not math.isfinite(metric[key]):
                metric[key] = 'infinity'
    for name, data in saved.items():
        require(read(run/name) == data, 'run changed during audit')
    return {'status': 'numerical_failed' if failures else 'reexecution_passed',
            'errors': [] if not failures else ['zero-budget output mismatch'],
            'identity_checks': {'manifest_sha256': sha(raw['manifest.json']), 'config': m['config_identity'],
                'build': m['build_identity'], 'scene_epoch': m['scene_epoch'], 'source_run_id': m['source_run_id']},
            'counts': {'ticks': n, 'comparisons': n*120, 'failures': failures},
            'first_mismatch': first, 'per_slot_errors': slots, 'budget': {'atol': 0, 'rtol': 0}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('import', 'run', 'audit', '_execute'):
        p = sub.add_parser(action)
        p.add_argument('--source' if action == 'import' else '--input', type=Path, required=True)
        if action in ('run', '_execute'):
            p.add_argument('--library', type=Path, required=True)
        if action == 'audit':
            p.add_argument('--run', type=Path, required=True)
        p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        code = 0
        if args.action == 'import':
            result = import_bundle(args.source, args.output)
        elif args.action == 'run':
            result, code = run_bundle(args.input, args.library, args.output)
        elif args.action == '_execute':
            execute(args.input, args.library, args.output)
            result = {'status': 'recomputed'}
        else:
            outside(args.output, args.input)
            outside(args.output, args.run)
            result = audit_bundle(args.input, args.run)
            write_json(args.output, result)
            code = 0 if result['status'] == 'reexecution_passed' else 1
        print(json.dumps(result, allow_nan=False))
        return code
    except (OSError, ValueError, KeyError, TypeError, OverflowError, subprocess.SubprocessError) as error:
        result = {'status': 'rejected', 'reason': str(error)}
        if args.action == 'audit' and not args.output.exists():
            outside(args.output, args.input)
            outside(args.output, args.run)
            write_json(args.output, result)
        print(json.dumps(result), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
