"""Prepare the diagnostic-only first-step solve-candidate build: patch + command.

Read-only source transformation and command generation ONLY. This tool never runs
a compiler, model, MATLAB, or ROS; the main session executes the emitted build and
run commands separately. It reuses the shared first-step trace builder
(tools/build_first_step_trace.py, never modified) to validate the same pinned model
archive and frozen C3G input and to instrument the generated source, then adds ONE
uniform diagonal branch to rt_mrdivide_U1d1x3_U2d_9vOrDY9Z in the fresh output
copy, matching the main session's proven recipe
(validation/coordination/g6-diagonal-solve-candidate-20260913/prepare.py):

    if all 6 off-diagonal entries are zero, all 3 numerators (u0) and all 3
    diagonal entries (u1[0], u1[4], u1[8]) are finite, and the diagonal is
    nonzero: evaluate the three reciprocals first; only if ALL three are finite
    (a finite nonzero subnormal diagonal can overflow 1/d, and 0*inf would be
    NaN where the original 0/d is finite) use y[i] = u0[i] * reciprocal[i] for
    all three axes; otherwise the original function body runs verbatim below.

The branch is structural only: no axis/q-specific, value-specific, or time-specific
gating. It probes the observed same-operand 1ULP first-step difference (offline,
multiply-by-reciprocal reproduced the reference q; direct division reproduced the
target q). It is NOT a formal model change and NOT a G6/R1 acceptance result.

Anchor discipline: the pinned instrumented source contains exactly three
FUNC_NAME occurrences - one extern declaration, one definition, one call site.
Each occurrence must classify as exactly one of these (canonical u0/u1/y
signature required for declaration and definition; anything else is rejected -
a same-name token in a comment or with a different shape never counts). The
insertion goes right after the definition's opening brace line. Removing the
inserted bytes restores the instrumented source exactly (verified at patch time).

The original and instrumented sources, the frozen archive, and all earlier
evidence stay untouched; outputs go to a NEW directory only (existing dirs/files
refused), and after writing, every file is re-read and checked against the
recorded metadata. No git operations are performed.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

_BUILDER_PATH = Path(__file__).with_name('build_first_step_trace.py')
_spec = importlib.util.spec_from_file_location('first_step_trace_builder', _BUILDER_PATH)
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)

FUNC_NAME = b'rt_mrdivide_U1d1x3_U2d_9vOrDY9Z'
# Whitespace-insensitive canonical signature (the pinned extern declaration wraps
# as "const real_T u1\r\n  [9]"); must match declaration and definition.
PARAMS_COMPACT = 'constreal_Tu0[3],constreal_Tu1[9],real_Ty[3]'
TRACE_MARKERS = (b'wk_trace_ode4_stage', b'wk_trace_mrdivide')
BRANCH_MARKER = b'Diagnostic-only uniform diagonal solve'
# std::isfinite needs <cmath>; require textual evidence the pinned source already
# relies on it (it compiled on target), else reject instead of emitting bad code.
CMATH_EVIDENCE = (b'<cmath>', b'<math.h>', b'std::abs', b'std::sin', b'std::cos',
                  b'std::sqrt', b'fabs')

# Byte-identical to the main session's proven candidate insertion (prepare.py),
# CRLF-normalized: three reciprocals evaluated first, used only if all finite.
INSERTION = (
    b'  // Diagnostic-only uniform diagonal solve; original general solve follows.\r\n'
    b'  if (u1[1] == 0.0 && u1[2] == 0.0 && u1[3] == 0.0 &&\r\n'
    b'      u1[5] == 0.0 && u1[6] == 0.0 && u1[7] == 0.0 &&\r\n'
    b'      std::isfinite(u0[0]) && std::isfinite(u0[1]) && std::isfinite(u0[2]) &&\r\n'
    b'      std::isfinite(u1[0]) && std::isfinite(u1[4]) && std::isfinite(u1[8]) &&\r\n'
    b'      u1[0] != 0.0 && u1[4] != 0.0 && u1[8] != 0.0) {\r\n'
    b'    const real_T reciprocal[3] = {1.0 / u1[0], 1.0 / u1[4], 1.0 / u1[8]};\r\n'
    b'    if (std::isfinite(reciprocal[0]) && std::isfinite(reciprocal[1]) &&\r\n'
    b'        std::isfinite(reciprocal[2])) {\r\n'
    b'      y[0] = u0[0] * reciprocal[0];\r\n'
    b'      y[1] = u0[1] * reciprocal[1];\r\n'
    b'      y[2] = u0[2] * reciprocal[2];\r\n'
    b'      return;\r\n'
    b'    }\r\n'
    b'  }\r\n'
)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _exclusive_write(path, data):
    """Create a file exclusively; never overwrite an existing one."""
    if Path(path).exists() or Path(path).is_symlink():
        raise FileExistsError('Refusing to overwrite existing file: ' + str(path))
    with open(path, 'xb') as handle:
        handle.write(data)


def _classify_occurrence(src, pos):
    """Classify one FUNC_NAME occurrence as ('definition', insert_at),
    ('declaration', None), or ('call', None); reject any other shape. Only the
    canonical u0/u1/y signature counts as declaration/definition; the insertion
    point is right after the definition's opening-brace line."""
    j = pos + len(FUNC_NAME)
    while j < len(src) and src[j:j + 1].isspace():
        j += 1
    if src[j:j + 1] != b'(':
        raise ValueError('Unexpected rt_mrdivide occurrence (no parameter list)')
    depth = 0
    m = j
    while True:
        if m >= len(src):
            raise ValueError('Unbalanced rt_mrdivide parameter list')
        ch = src[m:m + 1]
        if ch == b'(':
            depth += 1
        elif ch == b')':
            depth -= 1
            if depth == 0:
                break
        m += 1
    params = src[j + 1:m]
    try:
        compact = ''.join(params.decode('ascii').split())
    except UnicodeDecodeError:
        raise ValueError('rt_mrdivide parameter list is not ASCII')
    n = m + 1
    while n < len(src) and src[n:n + 1].isspace():
        n += 1
    if src[n:n + 1] == b'{':
        if compact != PARAMS_COMPACT:
            raise ValueError('rt_mrdivide definition signature differs from the u0/u1/y convention')
        if src[n + 1:n + 3] != b'\r\n':
            raise ValueError('rt_mrdivide definition opening brace is not followed by CRLF')
        return ('definition', n + 3)
    if src[n:n + 1] == b';':
        return ('declaration', None) if compact == PARAMS_COMPACT else ('call', None)
    raise ValueError('Unexpected token after rt_mrdivide parameter list')


def add_diagonal_branch(instrumented):
    """Insert the uniform diagonal branch into rt_mrdivide of the INSTRUMENTED
    source; verify that removing the inserted bytes restores the input verbatim."""
    if any(marker not in instrumented for marker in TRACE_MARKERS):
        raise ValueError('Input must be the instrumented first-step trace source')
    if INSERTION in instrumented or BRANCH_MARKER in instrumented:
        raise ValueError('Candidate branch already present')
    if not any(token in instrumented for token in CMATH_EVIDENCE):
        raise ValueError('No evidence of <cmath> availability in the pinned source')
    declarations = 0
    calls = 0
    insert_points = []
    start = 0
    while True:
        pos = instrumented.find(FUNC_NAME, start)
        if pos < 0:
            break
        kind, insert_at = _classify_occurrence(instrumented, pos)
        if kind == 'definition':
            insert_points.append(insert_at)
        elif kind == 'declaration':
            declarations += 1
        else:
            calls += 1
        start = pos + 1
    if declarations != 1 or len(insert_points) != 1 or calls != 1:
        raise ValueError('Expected exactly one rt_mrdivide declaration, definition, and call site')
    insert_at = insert_points[0]
    patched = instrumented[:insert_at] + INSERTION + instrumented[insert_at:]
    if patched.count(INSERTION) != 1 or patched.replace(INSERTION, b'', 1) != instrumented:
        raise ValueError('Candidate insertion is not cleanly removable')
    return patched


def write_outputs(out_dir, files, command):
    """Create the NEW output directory and all files exclusively; never overwrite."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True)  # must be new; FileExistsError if it already exists
    for name, data in files.items():
        _exclusive_write(out_dir / name, data)
    _exclusive_write(out_dir / 'build-command.json',
                     (json.dumps(command, indent=2) + '\n').encode())


def _verify_written(out_dir, files, command):
    """Re-read every written file; recorded metadata must match the actual bytes."""
    out_dir = Path(out_dir)
    for name, data in files.items():
        if (out_dir / name).read_bytes() != data:
            raise ValueError('Written file differs from prepared bytes: ' + name)
    on_disk = json.loads((out_dir / 'build-command.json').read_text())
    if on_disk['identity'] != command['identity']:
        raise ValueError('Written build-command.json identity differs')
    checks = {
        'original_cpp_sha256': 'Exp1_MinModelTemp.original.cpp',
        'instrumented_cpp_sha256': 'Exp1_MinModelTemp.instrumented.cpp',
        'candidate_cpp_sha256': 'Exp1_MinModelTemp.cpp',
        'recorder_cpp_sha256': 'first_step_trace_recorder.cpp',
        'input_csv_sha256': 'input.csv',
    }
    for key, name in checks.items():
        if _sha256((out_dir / name).read_bytes()) != command['identity'][key]:
            raise ValueError('Metadata SHA mismatch for ' + name)


def build(archive_path, recorder_cpp, out_dir, input_csv):
    """Write the candidate source, preserved baselines, recorder, input copy, and
    the real build/run commands to a NEW dir; verify metadata matches the files.
    Never compiles or runs anything."""
    archive_path = Path(archive_path)
    recorder_cpp = Path(recorder_cpp)
    out_dir = Path(out_dir)
    input_csv = Path(input_csv)

    archive_bytes = archive_path.read_bytes()
    sources = builder.read_sources(archive_bytes)  # pinned archive SHA + members
    recorder_bytes = recorder_cpp.read_bytes()
    input_bytes = input_csv.read_bytes()
    if _sha256(input_bytes) != builder.INPUT_SHA256:
        raise ValueError('Frozen C3G input SHA256 differs')
    original = sources['Exp1_MinModelTemp.cpp']
    instrumented = builder.instrument(original)  # pinned cpp SHA + trace hooks
    candidate = add_diagonal_branch(instrumented)

    build_argv = ['g++', '-std=c++17', '-O2', '-fno-fast-math', '-Wl,--no-undefined',
                  '-I', str(out_dir), str(out_dir / 'Exp1_MinModelTemp.cpp'),
                  str(out_dir / 'first_step_trace_recorder.cpp'),
                  '-o', str(out_dir / 'first_step_solve_candidate')]
    run_argv = [str(out_dir / 'first_step_solve_candidate'), '--record',
                str(out_dir / 'input.csv'),
                '--output', str(out_dir / 'first-step-solve-candidate.jsonl')]
    command = {
        'schema_version': 1,
        'kind': 'first_step_solve_candidate_build',
        'diagnostic_only': True,
        'production_replacement': False,
        'note': ('Diagnostic-only solve candidate: uniform y[i]=u0[i]*reciprocal[i] '
                 'for finite nonzero diagonal inertia with all-finite reciprocals, '
                 'original body otherwise. Not a model change, not a G6/R1 '
                 'acceptance. Compile/run separately (Linux/WSL).'),
        'candidate': ('Uniform reciprocal multiplication for finite invertible '
                      'diagonal matrices; original fallback retained'),
        'reciprocal_overflow_policy': 'Fall back to original solve if any reciprocal is nonfinite',
        'insertion_removed_restores_baseline': True,
        'build_argv': build_argv,
        'run_argv': run_argv,
        'compiler_reference': 'g++ (Ubuntu 11.4.0) -std=c++17 -O2 -fno-fast-math (same as R1 target build)',
        'identity': {
            'archive_sha256': _sha256(archive_bytes),
            'original_cpp_sha256': _sha256(original),
            'instrumented_cpp_sha256': _sha256(instrumented),
            'candidate_cpp_sha256': _sha256(candidate),
            'recorder_cpp_sha256': _sha256(recorder_bytes),
            'input_csv_sha256': _sha256(input_bytes),
            'shared_builder_sha256': _sha256(_BUILDER_PATH.read_bytes()),
            'candidate_builder_sha256': _sha256(Path(__file__).read_bytes()),
        },
    }
    files = {
        'Exp1_MinModelTemp.cpp': candidate,
        'Exp1_MinModelTemp.instrumented.cpp': instrumented,
        'Exp1_MinModelTemp.original.cpp': original,
        'Exp1_MinModelTemp.h': sources['Exp1_MinModelTemp.h'],
        'rtwtypes.h': sources['rtwtypes.h'],
        'rtw_continuous.h': sources['rtw_continuous.h'],
        'rtw_solver.h': sources['rtw_solver.h'],
        'first_step_trace_recorder.cpp': recorder_bytes,
        'input.csv': input_bytes,
    }
    write_outputs(out_dir, files, command)
    _verify_written(out_dir, files, command)
    return command


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=builder.ARCHIVE)
    parser.add_argument('--recorder', type=Path,
                        default=Path(__file__).with_name('first_step_trace_recorder.cpp'))
    parser.add_argument('--input', type=Path, required=True, help='the frozen C3G input.csv')
    parser.add_argument('--out-dir', type=Path, required=True,
                        help='NEW output directory (must not already exist); e.g. a WSL /root staging dir')
    args = parser.parse_args(argv)
    command = build(args.archive, args.recorder, args.out_dir, args.input)
    print('first-step solve-candidate build prepared (diagnostic only; no compile/run performed)')
    print('  out_dir           : {}'.format(args.out_dir))
    print('  candidate sha     : {}'.format(command['identity']['candidate_cpp_sha256']))
    print('  instrumented sha  : {}'.format(command['identity']['instrumented_cpp_sha256']))
    print('  original sha      : {}'.format(command['identity']['original_cpp_sha256']))
    print('  build             : {}'.format(' '.join(command['build_argv'])))
    print('  run               : {}'.format(' '.join(command['run_argv'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
