"""Exercise the compiled extension, not a fake loader."""
from pathlib import Path
import hashlib
import json
import time
import types
import native_release_wait_extension as extension

HERE = Path(__file__).resolve().parent
library = HERE / (extension.MODULE_NAME + extension.EXT_SUFFIX)
wait = extension.load(library, hashlib.sha256(library.read_bytes()).hexdigest())
assert isinstance(wait, types.BuiltinFunctionType)
checks = 0
before = time.monotonic_ns()
observed = wait(0)
after = time.monotonic_ns()
assert before <= observed <= after
checks += 1

class DerivedInt(int):
    pass

for argument, expected in [(True, TypeError), (False, TypeError), (1.0, TypeError),
        ('1', TypeError), (None, TypeError), (DerivedInt(1), TypeError),
        (-1, ValueError), (2**63, OverflowError), (-(2**63)-1, OverflowError),
        (2**63-1, RuntimeError)]:
    try:
        wait(argument)
    except expected:
        checks += 1
    else:
        raise AssertionError('expected rejection: ' + repr(argument))
for _ in range(20):
    deadline = time.monotonic_ns() + 500_000
    observed = wait(deadline)
    assert deadline <= observed <= time.monotonic_ns()
    checks += 1
result = dict(status='passed', checks=checks, callable_type=type(wait).__name__,
              library_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),
              scope='Compiled CPython argument/return interface and real clock; not production pacing')
with (HERE / 'extension-check.json').open('x') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
print(json.dumps(result))
