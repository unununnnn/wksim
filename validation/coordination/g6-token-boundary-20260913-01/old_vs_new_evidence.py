"""Old-versus-new evidence for the function-token boundary rule (read-only).

Owner: validation/coordination/g6-token-boundary-20260913-01.

The "old" side is the immutable pre-fix baseline pinned by commit
`5165781dc3607d08179c26f11b9af13f152fbf17`, whose blob for
`tools/build_first_step_solve_candidate.py` hashes to
`0f3a79a4b5bf7d96a71f3337ee6f2e3b3c0ac767e59d8a2cd7aab7d742e3e3bd`. The ref is a
commit id, never `HEAD`, so the evidence cannot drift when the fix is committed.

The baseline bytes are executed in an isolated module namespace with `__file__` set to
the REAL tool path, so its `Path(__file__).with_name('build_first_step_trace.py')`
lookup resolves without writing any scratch file into `tools/`.

Fixtures are exactly THREE occurrences of the audited name:
  * POSITIVE     = HEADER + DECL + DEF + CALL
  * REPLACED-DEF = HEADER + DECL + WRAPPER_DEF + CALL   (real definition replaced)
  * REPLACED-CALL= HEADER + DECL + DEF + PREFIXED_CALL  (real call replaced)

Read-only: nothing is written anywhere.
"""
import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOL_REL = 'tools/build_first_step_solve_candidate.py'
TOOL = ROOT / TOOL_REL
BASELINE_REF = '5165781dc3607d08179c26f11b9af13f152fbf17'
BASELINE_SHA256 = '0f3a79a4b5bf7d96a71f3337ee6f2e3b3c0ac767e59d8a2cd7aab7d742e3e3bd'


def load_new():
    spec = importlib.util.spec_from_file_location('candidate_new', TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_old():
    """Load the pinned baseline bytes in an isolated namespace; no scratch file."""
    text = subprocess.run(['git', 'cat-file', 'blob',
                           BASELINE_REF + ':' + TOOL_REL], cwd=str(ROOT),
                          capture_output=True, check=True).stdout.decode('utf-8')
    module = type(sys)('candidate_old_baseline')
    module.__file__ = str(TOOL)          # resolves the shared builder next to the tool
    exec(compile(text, str(TOOL), 'exec'), module.__dict__)
    return module


new = load_new()
old = load_old()

baseline_bytes = subprocess.run(['git', 'cat-file', 'blob',
                                 BASELINE_REF + ':' + TOOL_REL], cwd=str(ROOT),
                                capture_output=True, check=True).stdout

NAME = new.FUNC_NAME
SIG = b'(const real_T u0[3], const real_T u1[9],\r\n  real_T y[3])\r\n'
DECL = (b'extern void ' + NAME + b'(const real_T u0[3], const real_T u1\r\n'
        b'  [9], real_T y[3]);\r\n')
DEF = b'void ' + NAME + SIG + b'{\r\n  real_T A[9];\r\n  y[0] = u0[0] / A[0];\r\n}\r\n'
CALL = (b'  ' + NAME + b'(rtb_IntegratorSecondOrderLimi_d,\r\n'
        b'    Exp1_MinModelTemp_B.Selector2, Exp1_MinModelTemp_B.Product2);\r\n')
WRAPPER_DEF = b'void outer_' + NAME + SIG + b'{\r\n  Real2 A;\r\n  A = A;\r\n}\r\n'
PREFIXED_CALL = (b'  outer_' + NAME + b'(rtb_IntegratorSecondOrderLimi_d,\r\n'
                 b'    Exp1_MinModelTemp_B.Selector2, Exp1_MinModelTemp_B.Product2);\r\n')
HEADER = (b'#include "Exp1_MinModelTemp.h"\r\n'
          b'#include <cmath>\r\n'
          b'extern void wk_trace_ode4_stage(int, double, const real_T*, const real_T*, int);\r\n'
          b'extern void wk_trace_mrdivide(double, int, const real_T*, const real_T*,'
          b' const real_T*);\r\n')

FIXTURES = {
    'POSITIVE (DECL + DEF + CALL)': HEADER + DECL + DEF + CALL,
    'REPLACED-DEF (prefixed wrapper replaces the real definition)':
        HEADER + DECL + WRAPPER_DEF + CALL,
    'REPLACED-CALL (prefixed call replaces the real call)':
        HEADER + DECL + DEF + PREFIXED_CALL,
}

print('old side ref        : {} (pinned commit, not HEAD)'.format(BASELINE_REF))
print('old side blob sha256: {}'.format(hashlib.sha256(baseline_bytes).hexdigest()))
print('expected blob sha256: {}'.format(BASELINE_SHA256))
if hashlib.sha256(baseline_bytes).hexdigest() != BASELINE_SHA256:
    raise SystemExit('BASELINE SHA MISMATCH - refusing to present evidence')
print('old helper present  : {}'.format(hasattr(old, '_at_identifier_boundary')))
print('new helper present  : {}'.format(hasattr(new, '_at_identifier_boundary')))
print()

for label, source in FIXTURES.items():
    positions = []
    start = 0
    while True:
        pos = source.find(NAME, start)
        if pos < 0:
            break
        positions.append(pos)
        start = pos + 1
    print('=' * 78)
    print(label)
    print('  byte-length {}   NAME occurrences {}'.format(len(source), len(positions)))
    for pos in positions:
        print('    offset {:5d}  before={!r:6}  after={!r}'.format(
            pos, source[pos - 1:pos], source[pos + len(NAME):pos + len(NAME) + 24]))
    for which, module in (('OLD', old), ('NEW', new)):
        outcomes = []
        for pos in positions:
            try:
                outcomes.append(module._classify_occurrence(source, pos))
            except Exception as error:
                outcomes.append('REJECT: ' + str(error))
        print('  {} classify  : {}'.format(which, outcomes))
        try:
            patched = module.add_diagonal_branch(source)
            offset = patched.index(module.INSERTION)
            real_def = source.index(DEF) if DEF in source else None
            if real_def is None:
                landed = 'prefixed wrapper (fixture has no real definition)'
            else:
                landed = 'real definition' if offset >= real_def else 'prefixed wrapper'
            print('  {} add_branch: ACCEPTED, insertions={}, insertion_at={} -> {}'.format(
                which, patched.count(module.INSERTION), offset, landed))
        except Exception as error:
            print('  {} add_branch: REJECTED: {}'.format(which, error))
    print()
