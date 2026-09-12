"""Prepare one isolated diagnostic; run this with Linux Python, never compile here."""
from pathlib import Path
import hashlib
import json
import re
import sys

ROOT = Path('/mnt/c/Users/PC/Documents/odid编译/wksim')
sys.path.insert(0, str(ROOT))
from tools.build_first_step_trace import build

OUT = Path('/root/wksim-first-step-diagonal-solve-20260913-01')
command = build(
    '/mnt/e/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/MulticopterModel.zip',
    ROOT / 'tools/first_step_trace_recorder.cpp', OUT,
    ROOT / 'validation/numerical-conformance-gxxh6xhr/C3G/input.csv')
raw = (OUT / 'Exp1_MinModelTemp.cpp').read_bytes()
matches = list(re.finditer(rb'\nvoid rt_mrdivide_[^(]+\([^;{}]*\)\s*\{\r\n', raw))
assert len(matches) == 1
insertion = b'''  // Diagnostic-only uniform diagonal solve; original general solve follows.
  if (u1[1] == 0.0 && u1[2] == 0.0 && u1[3] == 0.0 &&
      u1[5] == 0.0 && u1[6] == 0.0 && u1[7] == 0.0 &&
      std::isfinite(u0[0]) && std::isfinite(u0[1]) && std::isfinite(u0[2]) &&
      std::isfinite(u1[0]) && std::isfinite(u1[4]) && std::isfinite(u1[8]) &&
      u1[0] != 0.0 && u1[4] != 0.0 && u1[8] != 0.0) {
    const real_T reciprocal[3] = {1.0 / u1[0], 1.0 / u1[4], 1.0 / u1[8]};
    if (std::isfinite(reciprocal[0]) && std::isfinite(reciprocal[1]) &&
        std::isfinite(reciprocal[2])) {
      y[0] = u0[0] * reciprocal[0];
      y[1] = u0[1] * reciprocal[1];
      y[2] = u0[2] * reciprocal[2];
      return;
    }
  }
'''.replace(b'\n', b'\r\n')
at = matches[0].end()
candidate = raw[:at] + insertion + raw[at:]
assert candidate.count(insertion) == 1 and candidate.replace(insertion, b'', 1) == raw
candidate_path = OUT / 'Exp1_MinModelTemp.candidate.cpp'
with candidate_path.open('xb') as stream:
    stream.write(candidate)
command['build_argv'] = [str(candidate_path) if arg == str(OUT / 'Exp1_MinModelTemp.cpp') else arg
                         for arg in command['build_argv']]
command['identity']['baseline_instrumented_cpp_sha256'] = command['identity']['instrumented_cpp_sha256']
command['identity']['instrumented_cpp_sha256'] = hashlib.sha256(candidate).hexdigest()
command['identity']['candidate_recipe_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
command['diagnostic_only'] = True
command['production_replacement'] = False
command['candidate'] = 'Uniform reciprocal multiplication for finite invertible diagonal matrices; original fallback retained'
command['reciprocal_overflow_policy'] = 'Fall back to original solve if any reciprocal is nonfinite'
command['insertion_removed_restores_baseline'] = True
with (OUT / 'candidate-command.json').open('x', encoding='utf-8') as stream:
    json.dump(command, stream, indent=2)
    stream.write('\n')
print(json.dumps({'directory': str(OUT), 'identity': command['identity'], 'compiled': False}))
