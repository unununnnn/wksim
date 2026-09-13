"""Retained-source pure preparation identity check for the solve-candidate builder.

Owner: validation/coordination/g6-token-boundary-20260913-01.
Read-only verification: prepares the candidate from local retained material WITHOUT
compiling, running, or writing any WSL path, and compares the resulting bytes with
the identities recorded by the retained experiment.

Inputs (all local):
  * pinned generated source  work/quad-parameters-source-review-20260909/Exp1_MinModelTemp.cpp
  * pinned model archive     E:/rflysimtools/.../e0_MinModelTemp/MulticopterModel.zip
  * frozen C3G input         validation/numerical-conformance-gxxh6xhr/C3G/input.csv
  * recorder                 tools/first_step_trace_recorder.cpp
  * retained identity        validation/coordination/g6-diagonal-solve-candidate-20260913/
                             build-command.json and candidate-command.json

Run:
    python -B validation/coordination/g6-token-boundary-20260913-01/verify_preparation_identity.py
"""
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CANDIDATE_TOOL = ROOT / 'tools' / 'build_first_step_solve_candidate.py'
PINNED_SOURCE = ROOT / 'work/quad-parameters-source-review-20260909/Exp1_MinModelTemp.cpp'
ARCHIVE = Path('E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/MulticopterModel.zip')
INPUT_CSV = ROOT / 'validation/numerical-conformance-gxxh6xhr/C3G/input.csv'
RECORDER = ROOT / 'tools/first_step_trace_recorder.cpp'
RETAINED_DIR = ROOT / 'validation/coordination/g6-diagonal-solve-candidate-20260913'

spec = importlib.util.spec_from_file_location('candidate_tool', CANDIDATE_TOOL)
cand = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cand)

sha = lambda data: hashlib.sha256(data).hexdigest()
sha_file = lambda path: sha(Path(path).read_bytes())

build_record = json.loads((RETAINED_DIR / 'build-command.json').read_text(encoding='utf-8'))
candidate_record = json.loads((RETAINED_DIR / 'candidate-command.json').read_text(encoding='utf-8'))

results = []
def check(name, actual, expected):
    ok = actual == expected
    results.append((ok, name, actual, expected))
    print(('OK   ' if ok else 'FAIL ') + name)
    print(f'        actual   {actual}')
    print(f'        expected {expected}')
    return ok

print('=== pinned material ===')
check('pinned generated source sha256', sha_file(PINNED_SOURCE),
      build_record['identity']['original_cpp_sha256'])
check('frozen C3G input sha256', sha_file(INPUT_CSV),
      build_record['identity']['input_csv_sha256'])
check('recorder sha256', sha_file(RECORDER),
      build_record['identity']['recorder_cpp_sha256'])
check('shared trace builder sha256', sha_file(ROOT / 'tools' / 'build_first_step_trace.py'),
      build_record['identity']['builder_sha256'])
if ARCHIVE.is_file():
    check('model archive sha256', sha_file(ARCHIVE),
          build_record['identity']['archive_sha256'])
else:
    print('SKIP model archive not present at', ARCHIVE)

print()
print('=== local preparation (no compile, no run) ===')
raw = PINNED_SOURCE.read_bytes()
instrumented = cand.builder.instrument(raw)
check('instrumented source sha256', sha(instrumented),
      build_record['identity']['instrumented_cpp_sha256'])
candidate = cand.add_diagonal_branch(instrumented)
check('candidate source sha256', sha(candidate),
      candidate_record['identity']['instrumented_cpp_sha256'])
check('candidate source sha256 == recorded pin', sha(candidate),
      '0107001b1a4aeef4591b2516ffad338866e4645a59c519c3c3e367073acac001')
check('insertion removal restores instrumented',
      candidate.replace(cand.INSERTION, b'', 1) == instrumented, True)

print()
print('=== full builder path against the pinned archive (writes to a temp dir only) ===')
if not (ARCHIVE.is_file() and INPUT_CSV.is_file() and RECORDER.is_file()):
    print('SKIP archive/input/recorder not all present')
else:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / 'candidate-build'
        command = cand.build(ARCHIVE, RECORDER, out_dir, INPUT_CSV)
        identity = command['identity']
        check('builder candidate_cpp_sha256', identity['candidate_cpp_sha256'], sha(candidate))
        check('builder original_cpp_sha256', identity['original_cpp_sha256'],
              build_record['identity']['original_cpp_sha256'])
        check('builder archive_sha256', identity['archive_sha256'],
              build_record['identity']['archive_sha256'])
        check('builder input_csv_sha256', identity['input_csv_sha256'],
              build_record['identity']['input_csv_sha256'])
        check('written file matches metadata',
              sha_file(out_dir / 'Exp1_MinModelTemp.cpp'), identity['candidate_cpp_sha256'])
        check('written instrumented copy matches metadata',
              sha_file(out_dir / 'Exp1_MinModelTemp.instrumented.cpp'),
              identity['instrumented_cpp_sha256'])
        check('production_replacement is false', identity.get('candidate_cpp_sha256') is not None
              and command['production_replacement'], False)
        check('diagnostic_only is true', command['diagnostic_only'], True)
        # the tool writes the candidate as Exp1_MinModelTemp.cpp; the retained
        # prepare.py wrote Exp1_MinModelTemp.candidate.cpp. Byte identity is what is
        # compared, not the filename.
        print('        note: retained prepare.py named the file '
              'Exp1_MinModelTemp.candidate.cpp; the tool writes Exp1_MinModelTemp.cpp')

print()
failed = [name for ok, name, _, _ in results if not ok]
print(f'=== summary: {len(results) - len(failed)}/{len(results)} checks passed ===')
if failed:
    print('FAILED CHECKS:')
    for name in failed:
        print('  -', name)
    sys.exit(1)
print('all identities reproduce from local retained material')
