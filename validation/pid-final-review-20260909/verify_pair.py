"""Bind dual-stack acceptance to retained strict reports and one source set."""
import hashlib
import json
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
cases = {'arducopter': repo/'validation/35-pid-arducopter/ap-shaped-feedback-20260909',
         'px4': repo/'validation/pid-final-px4-20260909'}
shared = ('Simulator/wksim_runtime/pid_task.py', 'Simulator/wksim_control/position_pid.py',
          'Simulator/wksim_runtime/pid-flight-v1.json', 'tools/run_pid_flight.py', 'tools/pid_physics.py')
verdict = dict(status='passed', stacks={}, shared_source_sha256={})
for stack, case in cases.items():
    result_raw = (case/'result.stdout.log').read_bytes()
    result = json.loads(result_raw)
    report_raw = (case/'strict-audit-report.json').read_bytes()
    audit = json.loads(report_raw)
    assert audit['schema'] == 'wksim.pid.audit.v1' and audit['status'] == 'recorded_evidence_pass'
    assert audit['run_id'] == result['run_id'] and audit['stack'] == result['stack'] == stack
    assert audit['input_sha256']['result.json'] == hashlib.sha256(result_raw).hexdigest()
    assert result['safe_landing'] and result['children_reaped'] and not result['cleanup_errors']
    assert result['source_unchanged'] and result['candidate_unchanged'] and result['stop_kind'] == 'landed_stop'
    assert result['config']['controller'] == result['config']['external_pid']['controller'] == 'pid'
    assert result['task']['external_pid']['status'] == 'completed_pending_raw_audit'
    for name in shared:
        actual = hashlib.sha256((repo/name).read_bytes()).hexdigest()
        assert result['source_sha256'][name] == audit['checks']['identity'][name] == actual
        verdict['shared_source_sha256'][name] = actual
    verdict['stacks'][stack] = dict(run_id=result['run_id'], run_dir=result['run_dir'],
        strict_audit_sha256=hashlib.sha256(report_raw).hexdigest(),
        result_sha256=hashlib.sha256(result_raw).hexdigest(),
        physics_ticks=audit['checks']['physics']['ticks'], pid_updates=audit['checks']['pid_recomputed'],
        native_associations=len(audit['checks']['native']['request_associations']),
        metrics=audit['checks']['metrics'], cleanup='landed_stop; all owned children reaped')
with (Path(__file__).with_name('pair-acceptance.json')).open('x') as f:
    json.dump(verdict,f,indent=2,allow_nan=False)
print(json.dumps(verdict,indent=2))
