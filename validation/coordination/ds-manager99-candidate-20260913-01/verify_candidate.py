#!/usr/bin/env python3
"""Verify the manager-only candidate with a fake os-call ledger.

Extracts the real ``scheduling`` function from both the frozen snapshot and the
candidate by AST, executes each in a restricted namespace with a recording fake
``os`` module, and compares the resulting ledgers role by role.

This is a code-and-call-path check only.  It performs no scheduling operation, no
privileged call, no native or model work, and it makes no performance claim.

    python verify_candidate.py --out evidence/candidate-verification.json
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SNAPSHOT = os.path.join(
    ROOT, 'validation', 'coordination', 'claude-owned-snapshot-wiring-20260913-01',
    'run_joint_flight-owned-snapshot-candidate-v3.py.txt')
CANDIDATE = os.path.join(HERE, 'candidate.py.txt')
SNAPSHOT_SHA256 = '1c600d7f018376f5c6fe333f0fd5da75798834c5f09e843078b0939142774373'
ROLES = ('manager', 'model', 'fc', 'task', 'agent', 'service')


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


class Ledger:
    """Recording fake for the os calls scheduling() makes.

    ``fail`` selects a call to raise OSError from, so the candidate's failure
    behaviour can be compared with the snapshot's.
    """

    PRIO_PROCESS = 0
    SCHED_FIFO = 1
    SCHED_RESET_ON_FORK = 0x40000000

    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def _record(self, name, *args):
        self.calls.append({'call': name, 'args': list(args)})
        if self.fail == name:
            raise OSError('ledger-injected %s failure' % name)

    def setpriority(self, which, pid, value):
        self._record('setpriority', which, pid, value)

    def getpriority(self, which, pid):
        self._record('getpriority', which, pid)
        return -10

    def sched_setscheduler(self, pid, policy, param):
        self._record('sched_setscheduler', pid, policy, param.sched_priority)

    def sched_getscheduler(self, pid):
        self._record('sched_getscheduler', pid)
        return self.SCHED_FIFO

    def sched_getparam(self, pid):
        self._record('sched_getparam', pid)
        return FakeParam(40)

    def sched_param(self, priority):
        self._record('sched_param', priority)
        return FakeParam(priority)


class FakeParam:
    def __init__(self, priority):
        self.sched_priority = priority


def extract_function(text, name):
    """Pull one top-level function definition out of the source by AST."""
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            module = ast.Module(body=[node], type_ignores=[])
            ast.fix_missing_locations(module)
            return compile(module, '<%s>' % name, 'exec')
    raise SystemExit('function %s not found' % name)


def run_case(code, role, async_model_evidence, fail=None):
    namespace = {
        'os': Ledger(fail=fail),
        'role_value': role,
        'async_model_evidence_value': async_model_evidence,
    }
    exec(code, namespace)  # noqa: S102 - the extracted function only touches the fake os
    return namespace['scheduling'](0, role, async_model_evidence=async_model_evidence)


def ledger_of(result):
    """The recorded calls, taken from the fake os the case used."""
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', default=None)
    args = parser.parse_args(argv)
    findings = []
    snapshot_sha = sha256_file(SNAPSHOT)
    if snapshot_sha != SNAPSHOT_SHA256:
        findings.append('frozen snapshot drifted: %s' % snapshot_sha)
    candidate_text = open(CANDIDATE, 'r', encoding='utf-8').read()
    snapshot_text = open(SNAPSHOT, 'r', encoding='utf-8').read()

    snapshot_code = extract_function(snapshot_text, 'scheduling')
    candidate_code = extract_function(candidate_text, 'scheduling')

    observations = []
    for role in ROLES:
        for flag in (False, True):
            snap_ns = {'os': Ledger(), 'async_model_evidence': flag}
            exec(snapshot_code, snap_ns)
            snap = snap_ns['scheduling'](0, role, async_model_evidence=flag)
            cand_ns = {'os': Ledger(), 'async_model_evidence': flag}
            exec(candidate_code, cand_ns)
            cand = cand_ns['scheduling'](0, role, async_model_evidence=flag)
            snap_calls = snap_ns['os'].calls
            cand_calls = cand_ns['os'].calls
            same_calls = snap_calls == cand_calls
            priority_change = None
            if snap.get('target_fifo_priority') != cand.get('target_fifo_priority'):
                priority_change = {'role': role,
                                   'snapshot': snap.get('target_fifo_priority'),
                                   'candidate': cand.get('target_fifo_priority')}
                if role != 'manager':
                    findings.append('a non-manager role changed priority: %s' % role)
            elif role == 'manager':
                findings.append('the manager priority did not change')
            if not same_calls and role != 'manager':
                findings.append('os call ledger changed for role %s' % role)
            observations.append({
                'role': role, 'async_model_evidence': flag,
                'snapshot_target_fifo_priority': snap.get('target_fifo_priority'),
                'candidate_target_fifo_priority': cand.get('target_fifo_priority'),
                'snapshot_result': snap, 'candidate_result': cand,
                'os_calls_identical': same_calls,
                'priority_change': priority_change,
            })

    # manager ledgers must differ only in the priority argument
    manager_diffs = []
    for flag in (False, True):
        snap_ns = {'os': Ledger(), 'async_model_evidence': flag}
        exec(snapshot_code, snap_ns)
        snap_ns['scheduling'](0, 'manager', async_model_evidence=flag)
        cand_ns = {'os': Ledger(), 'async_model_evidence': flag}
        exec(candidate_code, cand_ns)
        cand_ns['scheduling'](0, 'manager', async_model_evidence=flag)
        for a, b in zip(snap_ns['os'].calls, cand_ns['os'].calls):
            if a != b:
                manager_diffs.append({'async_model_evidence': flag, 'snapshot': a,
                                      'candidate': b})
        if len(snap_ns['os'].calls) != len(cand_ns['os'].calls):
            findings.append('manager call count differs at flag=%s' % flag)
    for diff in manager_diffs:
        if diff['snapshot']['call'] not in ('sched_setscheduler', 'sched_param'):
            findings.append('manager ledger changed outside the scheduler priority: %r' % diff)
        elif diff['snapshot']['args'][-1] == diff['candidate']['args'][-1]:
            findings.append('a flagged manager difference is not a priority difference: %r'
                            % diff)
    if not any(diff['snapshot']['call'] == 'sched_setscheduler' for diff in manager_diffs):
        findings.append('no manager sched_setscheduler priority difference was recorded')
    if not any(diff['snapshot']['call'] == 'sched_param' for diff in manager_diffs):
        findings.append('no manager sched_param priority difference was recorded')

    # failure behaviour: each os call in turn must fail the same way in both
    failure_cases = []
    for fail in ('setpriority', 'sched_setscheduler', 'sched_getscheduler', 'sched_getparam'):
        snap_ns = {'os': Ledger(fail=fail), 'async_model_evidence': True}
        exec(snapshot_code, snap_ns)
        snap = snap_ns['scheduling'](0, 'manager', async_model_evidence=True)
        cand_ns = {'os': Ledger(fail=fail), 'async_model_evidence': True}
        exec(candidate_code, cand_ns)
        cand = cand_ns['scheduling'](0, 'manager', async_model_evidence=True)
        keys = ('nice_error', 'scheduler_error', 'actual_nice', 'actual_policy',
                'actual_priority', 'reset_on_fork')
        same_shape = all((key in snap) == (key in cand) for key in keys)
        same_errors = (('nice_error' in snap) == ('nice_error' in cand)
                       and ('scheduler_error' in snap) == ('scheduler_error' in cand))
        if not (same_shape and same_errors):
            findings.append('failure behaviour differs when %s fails' % fail)
        failure_cases.append({'failing_call': fail,
                              'snapshot_result': snap, 'candidate_result': cand,
                              'same_outcome_keys': same_shape,
                              'same_error_keys': same_errors})

    report = {
        'artifact': 'ds-manager99-candidate-verification',
        'version': 'v1',
        'snapshot': {'path': os.path.relpath(SNAPSHOT, ROOT).replace(os.sep, '/'),
                     'sha256': snapshot_sha, 'matches_pin': snapshot_sha == SNAPSHOT_SHA256},
        'candidate': {'path': os.path.basename(CANDIDATE),
                      'sha256': sha256_file(CANDIDATE)},
        'method': [('AST extraction of the scheduling function from both files'),
                   ('restricted exec with a recording fake os that performs no system call'),
                   ('role-by-role comparison of results, os call ledgers and failure paths')],
        'roles_exercised': list(ROLES),
        'observations': observations,
        'manager_ledger_differences': manager_diffs,
        'failure_cases': failure_cases,
        'conclusion': {
            'only_manager_priority_changed': not [f for f in findings
                                                  if 'non-manager' in f or 'manager priority' in f],
            'non_manager_roles_byte_identical_results': all(
                item['snapshot_result'] == item['candidate_result']
                for item in observations if item['role'] != 'manager'),
            'no_scheduling_operation_performed': True,
        },
        'not_claimed': [
            'no performance, latency or acceptance claim of any kind',
            'the evidence that motivated the candidate (11 process priorities observed '
            'before and after a real run) is not a causal proof and is not treated as one',
            'no native, scheduling, model or runtime operation was performed here',
        ],
        'status': 'candidate_verified_as_manager_only' if not findings
                  else 'verification_failed',
        'findings': findings,
    }
    if args.out:
        directory = os.path.dirname(os.path.abspath(args.out))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        with open(args.out, 'w', encoding='utf-8', newline='\n') as handle:
            json.dump(report, handle, indent=2)
            handle.write('\n')
    print(json.dumps({'status': report['status'],
                      'manager_priority': [(item['snapshot_target_fifo_priority'],
                                            item['candidate_target_fifo_priority'])
                                           for item in observations
                                           if item['role'] == 'manager'],
                      'non_manager_unchanged': report['conclusion'][
                          'non_manager_roles_byte_identical_results'],
                      'manager_ledger_differences': len(manager_diffs),
                      'failure_cases': len(failure_cases),
                      'findings': len(findings), 'out': args.out}, sort_keys=True))
    for item in findings[:6]:
        print('  finding: %s' % item)
    return 0 if not findings else 1


if __name__ == '__main__':
    sys.exit(main())
