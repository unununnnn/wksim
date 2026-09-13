#!/usr/bin/env python3
"""Independent read-only probe of the diagnostic -> formal admission chain.

Pure Python only: no native code, no build, no ROS, no flight controller, no
model, no UE and no MATLAB. Nothing is launched as a subprocess here.

It reuses the *shipped* fixture builders to construct a self-consistent
on-disk evidence tree, then calls the real
``Simulator.wksim_runtime.joint_profile._mixed_proofs`` (the formal gate) and
the real ``tools.run_joint_flight.finalize_perf_capture`` (the runner side).

Writes only ``chain_probe.json`` next to itself.
"""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'validation'))

import test_joint_profile as tj          # noqa: E402
import test_run_joint_perf_capture as tperf  # noqa: E402
from Simulator.wksim_runtime import joint_profile as profile  # noqa: E402
from tools import run_joint_flight as runner  # noqa: E402

CASES = []


def check(name, ok, detail=''):
    CASES.append(dict(name=name, ok=bool(ok), detail=str(detail)))


def try_reject(p, recs, ids):
    """Return (raised, message, raw_called) for one _mixed_proofs call."""
    with patch.object(profile, '_raw_proof',
                      side_effect=AssertionError('must not be called')) as raw:
        try:
            profile._mixed_proofs(p, recs, ids)
            return False, '', raw.called
        except ValueError as error:
            return True, str(error), raw.called


# --------------------------------------------------------------------------
# 1. Key-presence semantics: every value shape, including None/False/{}.
# --------------------------------------------------------------------------
for value in (None, False, True, {}, [], 0, '', 'enabled', {'diagnostic': 'x'}):
    with tempfile.TemporaryDirectory() as directory:
        p, records, identities, _, _ = tj._mixed_proof_fixture(
            directory, marker=('perf_switch_capture', value))
        raised, message, raw_called = try_reject(p, records, identities)
        check('key_presence_rejects_%r' % (value,),
              raised and 'perf_switch_capture' in message and not raw_called,
              message or 'accepted')

# --------------------------------------------------------------------------
# 2. Early ordering: rejected before any raw-evidence walk.
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as directory:
    p, records, identities, _, _ = tj._mixed_proof_fixture(
        directory, marker=('perf_switch_capture', None))
    raised, message, raw_called = try_reject(p, records, identities)
    check('rejected_before_raw_proof', raised and not raw_called, message or 'accepted')

# --------------------------------------------------------------------------
# 3. Extra perf source files do not break source-set identity (no marker).
# --------------------------------------------------------------------------
PERF_EXTRA = (
    'Simulator/wksim_runtime/perf_capture.py',
    'Simulator/wksim_runtime/evidence.py',
    'validation/coordination/ds-perf-stream-recorder-20260913-01/wksim_perf_stream.c',
    'validation/coordination/ds-perf-stream-recorder-20260913-01/wksim_perf_stream.h',
    'validation/coordination/ds-perf-stream-consumer-20260913-01/perf_stream_consumer.py',
)
original_sources = tj.FIXTURE_SOURCES
try:
    tj.FIXTURE_SOURCES = original_sources + PERF_EXTRA
    with tempfile.TemporaryDirectory() as directory:
        p, records, identities, _, flights = tj._mixed_proof_fixture(directory)
        try:
            healthy, _ = profile._mixed_proofs(p, records, identities)
            extra_bound = all(
                set(PERF_EXTRA) <= set(flight['source_sha256']) for flight in flights)
            check('extra_perf_sources_bound_and_accepted',
                  extra_bound and healthy['task_profile'] == profile.MIXED_TASKS[1])
        except ValueError as error:
            check('extra_perf_sources_bound_and_accepted', False, str(error))

    # 3b. The same extra sources cannot smuggle a marker past the gate.
    with tempfile.TemporaryDirectory() as directory:
        p, records, identities, _, _ = tj._mixed_proof_fixture(
            directory, marker=('perf_switch_capture', {'status': 'sealed_for_external_consumer'}))
        raised, message, raw_called = try_reject(p, records, identities)
        check('extra_sources_do_not_bypass_marker_gate',
              raised and 'perf_switch_capture' in message and not raw_called,
              message or 'accepted')
finally:
    tj.FIXTURE_SOURCES = original_sources

# --------------------------------------------------------------------------
# 4. Runner marker can never self-certify the strict consumer.
# --------------------------------------------------------------------------
captured = {}


def capture_marker():
    return dict(requested=True, status='requested', strict_consumer_passed=False)


with tempfile.TemporaryDirectory() as directory:
    capture = tperf.FakeCapture(directory)
    value = capture_marker()
    runner.start_perf_capture(capture, value)
    captured['after_start'] = dict(value)
    result = dict(status='pass', perf_switch_capture=value)
    with patch.object(runner, 'perf_capture_boot_id', return_value=tperf.BOOT_ID):
        runner.finalize_perf_capture(result, Path(directory), capture,
                                     tperf.PerfCaptureLifecycleTests().rate())
    captured['after_finalize'] = result['perf_switch_capture']
    captured['run_status'] = result['status']

check('runner_start_leaves_consumer_unpassed',
      captured['after_start'].get('strict_consumer_passed') is False,
      captured['after_start'])
check('runner_seal_does_not_pass_consumer',
      captured['after_finalize'].get('status') == 'sealed_for_external_consumer'
      and captured['after_finalize'].get('strict_consumer_passed') is False
      and captured['after_finalize'].get('capture_lifecycle_complete') is True,
      {k: captured['after_finalize'].get(k) for k in
       ('status', 'strict_consumer_passed', 'capture_lifecycle_complete')})

# The strict-consumer contract recorded in the result claims the flag/output
# but the runner itself never executes it; verify by static source scan.
import re  # noqa: E402

runner_text = (REPO / 'tools' / 'run_joint_flight.py').read_text(encoding='utf-8')
check('strict_consumer_not_executed_by_runner',
      re.search(r'(Popen|subprocess\.(run|call)|check_output)\([^\n]*perf_stream_consumer',
                runner_text) is None,
      'no subprocess call targets the consumer source')
check('strict_consumer_flag_never_set_true',
      'strict_consumer_passed=True' not in runner_text
      and 'strict_consumer_passed=False' in runner_text,
      'True=%d False=%d' % (runner_text.count('strict_consumer_passed=True'),
                            runner_text.count('strict_consumer_passed=False')))

receipt = dict(
    tool='codebuddy-perf-admission-review chain_probe',
    mode='read-only pure Python; no native/build/ROS/flight/model/UE/MATLAB',
    repo=str(REPO),
    cases=len(CASES),
    failures=sum(1 for row in CASES if not row['ok']),
    results=CASES,
)
(HERE / 'chain_probe.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(cases=receipt['cases'], failures=receipt['failures'])))
raise SystemExit(1 if receipt['failures'] else 0)
