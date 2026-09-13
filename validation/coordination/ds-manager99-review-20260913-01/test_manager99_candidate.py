"""Independent tests for the manager-only FIFO 50 -> 99 scheduling candidate.

Run:  python -B validation/coordination/ds-manager99-review-20260913-01/test_manager99_candidate.py

No real scheduling: every check executes the candidate's recorded ``scheduling()``
against a fake ``os`` ledger, or compares bytes/AST of the two source files.
"""
from pathlib import Path
import difflib
import hashlib
import json
import os
import unittest

import manager_schedule_probe as probe
from manager_schedule_probe import (
    ALL_ROLES, CANDIDATE, CANDIDATE_MANAGER_FIFO, FIFO_ROLES, MODEL_FC_FIFO,
    NICE_OTHER, NICE_TARGET, SNAPSHOT, SNAPSHOT_MANAGER_FIFO, FakeOS,
    audit_source, load_scheduling, run_scheduling,
)


class CandidateIdentity(unittest.TestCase):
    """The candidate must be the frozen snapshot plus the manager change only."""

    def setUp(self):
        self.audit = audit_source()

    def test_snapshot_still_matches_the_frozen_pin(self):
        self.assertTrue(self.audit['snapshot_matches_frozen_pin'])
        self.assertEqual(self.audit['snapshot_sha256'], probe.SNAPSHOT_SHA256)
        self.assertEqual(self.audit['snapshot_lines'], 1560)

    def test_candidate_changes_exactly_two_snapshot_lines(self):
        # line 189 (the value) and line 192 (the comment that names the level);
        # SequenceMatcher reports them as two replace opcodes because the added
        # comment block sits between them
        self.assertEqual(self.audit['changed_hunks'], 2)
        self.assertEqual(self.audit['removed_line_numbers'], [189, 192])
        self.assertEqual([op['tag'] for op in self.audit['opcodes']], ['replace', 'replace'])
        self.assertEqual(self.audit['opcodes'][0]['old'], [189, 189])
        self.assertEqual(self.audit['opcodes'][1]['old'], [192, 192])

    def test_only_semantic_change_is_the_manager_fifo_value(self):
        # the two semantic (non-comment) lines are the same statement with 50 vs 99
        self.assertEqual(len(self.audit['semantic_removed']), 1)
        self.assertEqual(len(self.audit['semantic_added']), 1)
        self.assertEqual(self.audit['semantic_removed'][0].strip(),
                         probe.SNAPSHOT_FIFO_LINE.strip().strip())
        self.assertEqual(self.audit['semantic_added'][0].strip(),
                         probe.CANDIDATE_FIFO_LINE.strip())
        self.assertEqual(self.audit['non_fifo_semantic_lines'], [])

    def test_every_other_changed_line_is_a_comment(self):
        comments = [line for line in self.audit['added_text'] + self.audit['removed_text']
                    if line.strip() and line not in self.audit['semantic_added']
                    and line not in self.audit['semantic_removed']]
        self.assertTrue(comments)
        for line in comments:
            self.assertTrue(line.strip().startswith('#'), line)

    def test_fifo_assignments_inside_scheduling(self):
        self.assertEqual(self.audit['fifo_assignments_snapshot'],
                         ["value['target_fifo_priority'] = 50 if role=='manager' else 40"])
        self.assertEqual(self.audit['fifo_assignments_candidate'],
                         ["value['target_fifo_priority'] = 99 if role=='manager' else 40"])
        self.assertTrue(self.audit['snapshot_fifo_line_present'])
        self.assertTrue(self.audit['candidate_fifo_line_present'])

    def test_author_identity_file_matches_measured_values(self):
        declared = probe.declared_identity()
        self.assertEqual(declared['snapshot']['sha256'], probe.SNAPSHOT_SHA256)
        self.assertEqual(declared['snapshot']['bytes'], self.audit['snapshot_bytes'])
        self.assertEqual(declared['snapshot']['lines'], self.audit['snapshot_lines'])
        self.assertEqual(declared['candidate_sha256'], self.audit['candidate_sha256'])
        self.assertEqual(declared['candidate_bytes'], self.audit['candidate_bytes'])
        self.assertEqual(declared['candidate_lines'], self.audit['candidate_lines'])
        self.assertEqual(declared['diff_sha256'], hashlib.sha256(probe.CANDIDATE_DIFF.read_bytes()).hexdigest())
        self.assertEqual(declared['change']['old_line_number'], 189)
        self.assertEqual(declared['change']['old'], probe.SNAPSHOT_FIFO_LINE)
        self.assertEqual(declared['change']['edited_snapshot_lines'], [189, 192])
        self.assertEqual(declared['change']['comment_lines_added'], 4)
        self.assertEqual(declared['change']['second_edit']['snapshot_line'], 192)
        self.assertEqual(declared['change']['old_side_lines_flagged_by_opcodes'],
                         self.audit['removed_line_numbers'])
        self.assertEqual(declared['change']['new_expression'],
                         "value['target_fifo_priority'] = 99 if role=='manager' else 40")
        self.assertEqual(declared['change']['roles_affected'], ['manager'])
        self.assertEqual(sorted(declared['change']['roles_unaffected']),
                         sorted([role for role in ALL_ROLES if role != 'manager']))
        self.assertEqual(declared['candidate_sha256'], probe.sha256_file(CANDIDATE))

    def test_declared_diff_is_reproducible_from_the_two_sources(self):
        expected = list(difflib.unified_diff(
            probe.read_text(SNAPSHOT).splitlines(keepends=True),
            probe.read_text(CANDIDATE).splitlines(keepends=True),
            fromfile='run_joint_flight-owned-snapshot-candidate-v3.py.txt',
            tofile='candidate.py.txt', n=6))
        declared = probe.read_text(probe.CANDIDATE_DIFF).splitlines(keepends=True)
        self.assertEqual(declared, expected)


class LedgerDifferential(unittest.TestCase):
    """Same calls, same order, same arguments: except the manager priority value."""

    def ledger_for(self, path, role, **kwargs):
        return run_scheduling(path, role, **kwargs)

    def test_non_manager_roles_are_byte_identical_in_behaviour(self):
        for role in ALL_ROLES:
            if role == 'manager':
                continue
            for evidence in (False, True):
                snapshot_value, snapshot_ledger = run_scheduling(
                    SNAPSHOT, role, async_model_evidence=evidence)
                candidate_value, candidate_ledger = run_scheduling(
                    CANDIDATE, role, async_model_evidence=evidence)
                self.assertEqual(snapshot_ledger.calls, candidate_ledger.calls,
                                 (role, evidence))
                self.assertEqual(snapshot_value, candidate_value, (role, evidence))

    def test_manager_ledger_differs_only_in_the_priority_argument(self):
        snapshot_value, snapshot_ledger = run_scheduling(SNAPSHOT, 'manager')
        candidate_value, candidate_ledger = run_scheduling(CANDIDATE, 'manager')
        self.assertEqual(len(snapshot_ledger.calls), len(candidate_ledger.calls))
        differing = [(left, right) for left, right in
                     zip(snapshot_ledger.calls, candidate_ledger.calls) if left != right]
        self.assertEqual(len(differing), 1)
        self.assertEqual(differing[0][0]['call'], 'sched_setscheduler')
        self.assertEqual(differing[0][0]['args'], [4242, FakeOS.SCHED_FIFO, 50])
        self.assertEqual(differing[0][1]['args'], [4242, FakeOS.SCHED_FIFO, 99])
        self.assertEqual(snapshot_value['target_fifo_priority'], SNAPSHOT_MANAGER_FIFO)
        self.assertEqual(candidate_value['target_fifo_priority'], CANDIDATE_MANAGER_FIFO)

    def test_nice_targets_are_unchanged_for_every_role(self):
        for role in ALL_ROLES:
            expected = NICE_TARGET if role in FIFO_ROLES else NICE_OTHER
            value, ledger = run_scheduling(CANDIDATE, role)
            self.assertEqual(value['target_nice'], expected, role)
            setpriority = ledger.named('setpriority')
            self.assertEqual(len(setpriority), 1, role)
            self.assertEqual(setpriority[0]['args'], [FakeOS.PRIO_PROCESS, 4242, expected], role)
            self.assertEqual(value['actual_nice'], expected, role)

    def test_manager_and_model_only_are_touched_when_async_evidence_is_on(self):
        for evidence in (False, True):
            for role in ALL_ROLES:
                value, ledger = run_scheduling(CANDIDATE, role,
                                               async_model_evidence=evidence)
                if role in FIFO_ROLES:
                    self.assertIn('target_fifo_priority', value, (role, evidence))
                    self.assertIn('actual_policy', value, (role, evidence))
                else:
                    self.assertNotIn('target_fifo_priority', value, (role, evidence))
                    self.assertNotIn('sched_setscheduler',
                                     ledger.call_names(), (role, evidence))

    def test_reset_on_fork_rule_is_unchanged(self):
        for role in ALL_ROLES:
            for evidence in (False, True):
                value, ledger = run_scheduling(CANDIDATE, role, async_model_evidence=evidence)
                scheduler = ledger.named('sched_setscheduler')
                if role not in FIFO_ROLES:
                    self.assertEqual(scheduler, [], (role, evidence))
                    continue
                expected_reset = role in ('manager', 'model') and evidence
                expected_policy = FakeOS.SCHED_FIFO | (
                    FakeOS.SCHED_RESET_ON_FORK if expected_reset else 0)
                self.assertEqual(scheduler[0]['args'][1], expected_policy, (role, evidence))
                self.assertEqual('reset_on_fork' in value, bool(expected_reset), (role, evidence))
                self.assertEqual(value.get('reset_on_fork'), True if expected_reset else None,
                                 (role, evidence))

    def test_model_and_fc_keep_fifo_40_exactly(self):
        for role in ('model', 'fc'):
            value, ledger = run_scheduling(CANDIDATE, role, async_model_evidence=True)
            self.assertEqual(value['target_fifo_priority'], MODEL_FC_FIFO, role)
            self.assertEqual(ledger.named('sched_setscheduler')[0]['args'][2],
                             MODEL_FC_FIFO, role)

    def test_reset_on_fork_key_appears_only_when_the_rule_holds(self):
        for role in ALL_ROLES:
            for evidence in (False, True):
                value, _ = run_scheduling(CANDIDATE, role, async_model_evidence=evidence)
                expected = role in ('manager', 'model') and evidence
                self.assertEqual('reset_on_fork' in value, bool(expected), (role, evidence))


class PidTargeting(unittest.TestCase):
    """Only the caller's own PID may be scheduled, and the caller PID is the only one."""

    def test_every_call_targets_the_requested_pid(self):
        for pid in (1, 4242, 99999):
            for role in ALL_ROLES:
                value, ledger = run_scheduling(CANDIDATE, role, pid=pid)
                self.assertTrue(ledger.calls, (pid, role))
                for entry in ledger.calls:
                    self.assertIn(pid, entry['args'], (pid, role, entry))

    def test_no_scheduling_call_happens_for_the_other_roles_pid(self):
        pid = 4242
        other = 4243
        for role in ALL_ROLES:
            _, ledger = run_scheduling(CANDIDATE, role, pid=pid)
            self.assertNotIn(other, [arg for entry in ledger.calls for arg in entry['args']])

    def test_call_surface_is_exactly_the_reviewed_five(self):
        _, ledger = run_scheduling(CANDIDATE, 'manager')
        self.assertEqual(ledger.call_names(),
                         ['setpriority', 'getpriority', 'sched_setscheduler',
                          'sched_getscheduler', 'sched_getparam'])
        self.assertEqual([entry['args'][0] for entry in ledger.named('setpriority')],
                         [FakeOS.PRIO_PROCESS])
        self.assertEqual([entry['args'][0] for entry in ledger.named('getpriority')],
                         [FakeOS.PRIO_PROCESS])

    def test_scheduling_uses_only_its_os_argument(self):
        """The function must not reach the real os module through any other name."""
        import ast
        source, _ = probe.function_block(probe.read_text(CANDIDATE))
        tree = ast.parse(source)
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertEqual(names - {'OSError', 'repr', 'dict', 'True'},
                         {'os', 'pid', 'role', 'async_model_evidence', 'value',
                          'error', 'reset_on_fork', 'policy'})
        # every os attribute access hangs off the injected os object
        os_attributes = {node.attr for node in ast.walk(tree)
                         if isinstance(node, ast.Attribute)
                         and isinstance(node.value, ast.Name) and node.value.id == 'os'}
        self.assertEqual(os_attributes,
                         {'setpriority', 'getpriority', 'PRIO_PROCESS', 'SCHED_FIFO',
                          'SCHED_RESET_ON_FORK', 'sched_setscheduler', 'sched_getscheduler',
                          'sched_getparam', 'sched_param'})
        # the only other attribute is the sched_param member read off a call result
        self.assertEqual(attributes - os_attributes, {'sched_priority'})


class FailurePassThrough(unittest.TestCase):
    """EPERM and friends must be recorded verbatim, not swallowed or reordered."""

    def test_nice_eperm_is_recorded_and_the_fifo_request_still_runs(self):
        ledger = FakeOS(nice_error=PermissionError(1, 'Operation not permitted'))
        value, _ = run_scheduling(CANDIDATE, 'manager', ledger=ledger)
        self.assertIn('nice_error', value)
        self.assertIn('Operation not permitted', value['nice_error'])
        self.assertNotIn('actual_nice', value)
        self.assertNotIn('scheduler_error', value)
        self.assertEqual(value['target_fifo_priority'], CANDIDATE_MANAGER_FIFO)
        self.assertIn('sched_setscheduler', ledger.call_names())
        # getpriority lives inside the same try as setpriority, so a rejected nice
        # also skips the read-back; the FIFO request still runs
        self.assertEqual(ledger.call_names()[:2], ['setpriority', 'sched_setscheduler'])
        self.assertEqual(ledger.named('getpriority'), [])

    def test_scheduler_eperm_is_recorded_verbatim_and_leaves_nice_applied(self):
        ledger = FakeOS(sched_error=PermissionError(1, 'Operation not permitted'))
        value, _ = run_scheduling(CANDIDATE, 'manager', ledger=ledger)
        self.assertIn('scheduler_error', value)
        self.assertIn('Operation not permitted', value['scheduler_error'])
        self.assertNotIn('actual_policy', value)
        self.assertNotIn('actual_priority', value)
        self.assertEqual(value['actual_nice'], NICE_TARGET)
        self.assertEqual(value['target_fifo_priority'], CANDIDATE_MANAGER_FIFO)
        self.assertEqual(len(ledger.named('sched_setscheduler')), 1)
        self.assertEqual(ledger.named('sched_getscheduler'), [])

    def test_both_failures_are_recorded_independently(self):
        ledger = FakeOS(nice_error=PermissionError(1, 'Operation not permitted'),
                        sched_error=OSError(22, 'Invalid argument'))
        value, _ = run_scheduling(CANDIDATE, 'manager', ledger=ledger)
        self.assertIn('nice_error', value)
        self.assertIn('scheduler_error', value)
        self.assertIn('Invalid argument', value['scheduler_error'])
        self.assertEqual(sorted(key for key in value if key.endswith('_error')),
                         ['nice_error', 'scheduler_error'])

    def test_success_reads_back_the_kernel_state_not_the_target(self):
        ledger = FakeOS(actual_policy=FakeOS.SCHED_FIFO | FakeOS.SCHED_RESET_ON_FORK)
        value, _ = run_scheduling(CANDIDATE, 'manager', async_model_evidence=True, ledger=ledger)
        self.assertEqual(value['actual_policy'], FakeOS.SCHED_FIFO | FakeOS.SCHED_RESET_ON_FORK)
        self.assertEqual(value['actual_priority'], CANDIDATE_MANAGER_FIFO)
        self.assertNotIn('scheduler_error', value)

    def test_denied_priority_readback_is_recorded_rather_than_defaulted(self):
        class Denied(FakeOS):
            def sched_getparam(self, pid):
                self._record('sched_getparam', pid)
                raise PermissionError(1, 'Operation not permitted')

        ledger = Denied()
        value, _ = run_scheduling(CANDIDATE, 'manager', ledger=ledger)
        self.assertIn('scheduler_error', value)
        self.assertNotIn('actual_priority', value)
        # actual_policy was read before the failing getparam and is still recorded
        self.assertIn('actual_policy', value)

    def test_no_result_key_claims_success_for_a_failed_request(self):
        ledger = FakeOS(sched_error=PermissionError(1, 'Operation not permitted'))
        value, _ = run_scheduling(CANDIDATE, 'manager', ledger=ledger)
        self.assertEqual(set(value), {'target_nice', 'actual_nice', 'target_fifo_priority',
                                      'scheduler_error'})
        self.assertNotIn('fifo_ok', value)
        self.assertNotIn('scheduled', value)


class NoRealScheduling(unittest.TestCase):
    """Guards that this review itself never touched a real scheduler."""

    def test_probe_module_never_calls_the_real_os_for_scheduling(self):
        text = probe.read_text(probe.__file__)
        for forbidden in ('import ctypes', 'subprocess', 'sched_setaffinity'):
            self.assertNotIn(forbidden, text)
        self.assertNotIn("os.sched_setscheduler(", text.replace('def sched_setscheduler', ''))
        self.assertNotIn('os.setpriority(', text.replace('def setpriority', ''))

    def test_candidate_is_never_imported_or_executed_as_a_whole(self):
        text = probe.read_text(probe.__file__)
        self.assertNotIn('importlib', text)
        # the only exec is the recorded scheduling() block
        self.assertEqual(text.count('exec(compile('), 1)

    def test_scheduling_remains_free_of_process_creation(self):
        import ast
        source, _ = probe.function_block(probe.read_text(CANDIDATE))
        code = ast.unparse(ast.parse(source))  # comments stripped: code only
        for forbidden in ('Popen', 'fork(', 'spawn', 'system('):
            self.assertNotIn(forbidden, code)
        # reset_on_fork is a policy flag, not a fork call
        self.assertIn('reset_on_fork', code)
        self.assertNotIn('os.fork', code)


if __name__ == '__main__':
    unittest.main(verbosity=2)
