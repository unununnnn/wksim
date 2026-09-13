"""Produce the evidence bundle for the manager-99 candidate review.

Read-only over the author's candidate, the frozen v3 snapshot and the retained capture.
Nothing is scheduled; the ledger run uses the fake os module from
``manager_schedule_probe``.

  python -B validation/coordination/ds-manager99-review-20260913-01/run_manager99_review.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import captured_policy_analysis as captured      # noqa: E402
import manager_schedule_probe as probe            # noqa: E402
from manager_schedule_probe import (ALL_ROLES, CANDIDATE, CANDIDATE_DIFF, CANDIDATE_JSON,
                                    BUILDER, SNAPSHOT, FakeOS, run_scheduling)  # noqa: E402

ROOT = HERE.parents[2]
EVIDENCE = HERE / 'evidence'


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ledger_differential():
    """Per-role, per-evidence ledger comparison of candidate against snapshot."""
    rows = []
    for role in ALL_ROLES:
        for evidence in (False, True):
            baseline_value, baseline_ledger = run_scheduling(
                SNAPSHOT, role, async_model_evidence=evidence)
            candidate_value, candidate_ledger = run_scheduling(
                CANDIDATE, role, async_model_evidence=evidence)
            differing = [dict(index=index, baseline=left, candidate=right)
                         for index, (left, right) in
                         enumerate(zip(baseline_ledger.calls, candidate_ledger.calls))
                         if left != right]
            rows.append(dict(
                role=role, async_model_evidence=evidence,
                calls_identical=baseline_ledger.calls == candidate_ledger.calls,
                value_identical=baseline_value == candidate_value,
                call_names=baseline_ledger.call_names(),
                differing_calls=differing,
                baseline_value=baseline_value, candidate_value=candidate_value,
            ))
    return rows


def failure_matrix():
    scenarios = {
        'nice_eperm': dict(nice_error=PermissionError(1, 'Operation not permitted')),
        'sched_eperm': dict(sched_error=PermissionError(1, 'Operation not permitted')),
        'both_denied': dict(nice_error=PermissionError(1, 'Operation not permitted'),
                            sched_error=OSError(22, 'Invalid argument')),
        'success_readback': dict(),
    }
    rows = []
    for name, kwargs in scenarios.items():
        ledger = FakeOS(**kwargs)
        value, _ = run_scheduling(CANDIDATE, 'manager', async_model_evidence=True,
                                  ledger=ledger)
        rows.append(dict(scenario=name, value=value, call_names=ledger.call_names(),
                         calls=ledger.calls))
    return rows


def pid_targeting():
    rows = []
    for pid in (1, 4242, 99999):
        for role in ALL_ROLES:
            _, ledger = run_scheduling(CANDIDATE, role, pid=pid)
            rows.append(dict(pid=pid, role=role,
                             every_call_carries_pid=all(pid in entry['args']
                                                        for entry in ledger.calls),
                             foreign_pids=[arg for entry in ledger.calls
                                           for arg in entry['args']
                                           if isinstance(arg, int) and arg not in
                                           (pid, FakeOS.PRIO_PROCESS, FakeOS.SCHED_FIFO,
                                            FakeOS.SCHED_RESET_ON_FORK)],
                             call_names=ledger.call_names()))
    return rows


def reset_on_fork_matrix():
    rows = []
    for role in ALL_ROLES:
        for evidence in (False, True):
            value, ledger = run_scheduling(CANDIDATE, role, async_model_evidence=evidence)
            scheduler = ledger.named('sched_setscheduler')
            rows.append(dict(role=role, async_model_evidence=evidence,
                             reset_key='reset_on_fork' in value,
                             policy=(scheduler[0]['args'][1] if scheduler else None),
                             priority=(scheduler[0]['args'][2] if scheduler else None)))
    return rows


def main():
    EVIDENCE.mkdir(exist_ok=True)
    audit = probe.audit_source()
    captured_analysis = captured.boundary_analysis()
    bundle = dict(
        scope='independent review of the manager-only FIFO 50 -> 99 scheduling candidate',
        no_real_scheduling=True,
        sources={
            'candidate.py.txt': dict(path=str(CANDIDATE.relative_to(ROOT)),
                                     sha256=sha256_file(CANDIDATE),
                                     bytes=CANDIDATE.stat().st_size),
            'candidate.json': dict(sha256=sha256_file(CANDIDATE_JSON)),
            'candidate.diff': dict(sha256=sha256_file(CANDIDATE_DIFF)),
            'build_candidate.py': dict(sha256=sha256_file(BUILDER)),
            'snapshot': dict(path=str(SNAPSHOT.relative_to(ROOT)),
                             sha256=sha256_file(SNAPSHOT),
                             matches_frozen_pin=audit['snapshot_matches_frozen_pin']),
        },
        source_audit={key: value for key, value in audit.items() if key != 'opcodes'},
        source_audit_opcodes=audit['opcodes'],
        declared_identity=probe.declared_identity(),
        ledger_differential=ledger_differential(),
        pid_targeting=pid_targeting(),
        failure_matrix=failure_matrix(),
        reset_on_fork_matrix=reset_on_fork_matrix(),
        captured_policy_boundary=captured_analysis,
        findings=[
            dict(id='F1', severity='none',
                 summary='candidate is the frozen snapshot plus exactly one semantic '
                         'change: the manager FIFO target 50 -> 99; model/fc 40, nice, '
                         'reset_on_fork and every other line are unchanged'),
            dict(id='F2', severity='comment_mismatch',
                 summary='the added comment says the manager is raised to just below the '
                         '99-priority threads; 99 is the highest observed level, so the '
                         'manager would be level with them, not below; the phrase '
                         '"work-queue/hrtimer service threads" is broader than the '
                         'observed comm names wq:*, wkr_hrt, sim_rcv, sim_send'),
            dict(id='F3', severity='boundary',
                 summary='equal-priority SCHED_FIFO threads do not preempt each other, so '
                         'the change cannot outrank the 98/99 threads; the capture records '
                         'no affinity or duty data, so same-core contention is not derivable'),
            dict(id='F4', severity='evidence_boundary',
                 summary='the capture is one run on one host/boot; the 98/99 threads live '
                         'in the wrapper px4-fc process, not in the runner; nothing in the '
                         'snapshot supports a performance claim'),
        ],
        blockers=[],
    )
    (EVIDENCE / 'manager99-review.json').write_text(
        json.dumps(bundle, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    manager = [row for row in bundle['ledger_differential'] if row['role'] == 'manager']
    print('source audit: hunks=%d changed_old_lines=%s non_fifo_semantic=%s' % (
        audit['changed_hunks'], audit['removed_line_numbers'], audit['non_fifo_semantic_lines']))
    for row in manager:
        print('manager async=%s calls_identical=%s value_identical=%s differing=%d' % (
            row['async_model_evidence'], row['calls_identical'], row['value_identical'],
            len(row['differing_calls'])))
    print('captured: manager rt before/after = %s / %s ; highest observed = %s' % (
        captured_analysis['manager']['before']['leader']['rt_priority'],
        captured_analysis['manager']['after']['leader']['rt_priority'],
        captured_analysis['highest_observed_after']))
    print('threads at 99 by role:', captured_analysis['threads_at_99'])
    print('evidence:', (EVIDENCE / 'manager99-review.json').relative_to(ROOT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
