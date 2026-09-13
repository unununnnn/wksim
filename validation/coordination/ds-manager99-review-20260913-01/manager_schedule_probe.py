"""Independent checks for the manager-only FIFO 50 -> 99 candidate.

Read-only over the author's candidate and the frozen v3 snapshot; writes nothing.
Nothing here schedules a real process: ``scheduling()`` is compiled from the recorded
source text and executed against a fake ``os`` ledger that only records calls.

The point is to answer four questions from evidence rather than from the candidate's
own prose:

  1. is the candidate byte-for-byte the frozen snapshot plus the manager change only?
  2. does the recorded ``scheduling()`` still emit exactly the same calls for every
     role except manager, and for the manager only the priority value?
  3. does the candidate schedule only its own PID, with nice/policy/reset-on-fork
     exactly as before?
  4. do nice and scheduler failures stay recorded verbatim (EPERM etc.) without being
     swallowed, reordered or turned into success?
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

CANDIDATE_DIR = ROOT / 'validation/coordination/ds-manager99-candidate-20260913-01'
CANDIDATE = CANDIDATE_DIR / 'candidate.py.txt'
CANDIDATE_JSON = CANDIDATE_DIR / 'candidate.json'
CANDIDATE_DIFF = CANDIDATE_DIR / 'candidate.diff'
BUILDER = CANDIDATE_DIR / 'build_candidate.py'
SNAPSHOT = (ROOT / 'validation/coordination/claude-owned-snapshot-wiring-20260913-01'
            / 'run_joint_flight-owned-snapshot-candidate-v3.py.txt')
SNAPSHOT_SHA256 = '1c600d7f018376f5c6fe333f0fd5da75798834c5f09e843078b0939142774373'

FUNCTION_NAME = 'scheduling'
ALL_ROLES = ('manager', 'model', 'fc', 'task', 'agent', 'service')
FIFO_ROLES = ('manager', 'model', 'fc')
NICE_TARGET = -10
NICE_OTHER = -5
MODEL_FC_FIFO = 40
SNAPSHOT_MANAGER_FIFO = 50
CANDIDATE_MANAGER_FIFO = 99

SNAPSHOT_FIFO_LINE = "        value['target_fifo_priority'] = 50 if role=='manager' else 40"
CANDIDATE_FIFO_LINE = "        value['target_fifo_priority'] = 99 if role=='manager' else 40"


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def read_text(path):
    return Path(path).read_bytes().decode('utf-8')


def function_block(text, name=FUNCTION_NAME):
    """(source_text, first_lineno) for one top-level function by its real span."""
    tree = ast.parse(text)
    lines = text.splitlines()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return '\n'.join(lines[node.lineno - 1:node.end_lineno]) + '\n', node.lineno
    raise LookupError('function %s not found' % name)


class FakeOS:
    """Ledger-only stand-in for the ``os`` scheduling surface.

    Every call is recorded with its exact arguments. Failures are raised as the
    configured OSError; on success the ledger is mutated so that the follow-up
    getters report what a real kernel would report for the accepted request.
    No process, thread or kernel interface is touched.
    """

    PRIO_PROCESS = 0
    SCHED_OTHER = 0
    SCHED_FIFO = 1
    SCHED_RESET_ON_FORK = 0x40000000

    def __init__(self, *, nice_error=None, sched_error=None, actual_nice=None,
                 actual_policy=None, actual_priority=None, sched_error_pids=()):
        self.calls = []
        self.nice_error = nice_error
        self.sched_error = sched_error
        self.sched_error_pids = set(sched_error_pids)
        self.actual_nice = actual_nice
        self.actual_policy = actual_policy
        self.actual_priority = actual_priority
        self.nice_state = {}
        self.scheduler_state = {}
        self.sched_param = SchedParam

    def _record(self, name, *args):
        self.calls.append(dict(call=name, args=list(args)))

    def named(self, name):
        return [entry for entry in self.calls if entry['call'] == name]

    def call_names(self):
        return [entry['call'] for entry in self.calls]

    def setpriority(self, which, pid, value):
        self._record('setpriority', which, pid, value)
        if self.nice_error is not None:
            raise self.nice_error
        self.nice_state[pid] = value

    def getpriority(self, which, pid):
        self._record('getpriority', which, pid)
        if pid in self.nice_state:
            return self.nice_state[pid]
        return self.actual_nice if self.actual_nice is not None else 0

    def sched_setscheduler(self, pid, policy, param):
        self._record('sched_setscheduler', pid, policy, param.sched_priority)
        if self.sched_error is not None and (not self.sched_error_pids
                                             or pid in self.sched_error_pids):
            raise self.sched_error
        self.scheduler_state[pid] = (policy, param.sched_priority)

    def sched_getscheduler(self, pid):
        self._record('sched_getscheduler', pid)
        if pid in self.scheduler_state:
            return self.scheduler_state[pid][0]
        return self.actual_policy if self.actual_policy is not None else self.SCHED_OTHER

    def sched_getparam(self, pid):
        self._record('sched_getparam', pid)
        priority = (self.scheduler_state[pid][1] if pid in self.scheduler_state
                    else (self.actual_priority if self.actual_priority is not None else 0))
        return SchedParam(priority)


class SchedParam:
    def __init__(self, priority):
        self.sched_priority = priority


def load_scheduling(path, os_module):
    """Compile the recorded scheduling() text against the given os module."""
    source, lineno = function_block(read_text(path))
    namespace = {'os': os_module}
    exec(compile(source, '<%s:%d>' % (Path(path).name, lineno), 'exec'), namespace)
    return namespace[FUNCTION_NAME], lineno


def run_scheduling(path, role, pid=4242, async_model_evidence=False, ledger=None):
    """Call the recorded scheduling() once and return (value, ledger)."""
    ledger = ledger if ledger is not None else FakeOS()
    function, _ = load_scheduling(path, ledger)
    value = function(pid, role, async_model_evidence=async_model_evidence)
    return value, ledger


def audit_source():
    """Structural comparison: candidate versus frozen snapshot, line by line."""
    baseline_raw = SNAPSHOT.read_bytes()
    candidate_raw = CANDIDATE.read_bytes()
    baseline_text = baseline_raw.decode('utf-8')
    candidate_text = candidate_raw.decode('utf-8')
    baseline_lines = baseline_text.splitlines()
    candidate_lines = candidate_text.splitlines()

    opcodes = []
    added, removed = [], []
    matcher = difflib.SequenceMatcher(a=baseline_lines, b=candidate_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            continue
        opcodes.append(dict(tag=tag, old=[i1 + 1, i2], new=[j1 + 1, j2]))
        removed.extend(range(i1 + 1, i2 + 1))
        added.extend(range(j1 + 1, j2 + 1))

    def fifo_assignments(text):
        body, _ = function_block(text)
        return [line.strip() for line in body.splitlines()
                if 'target_fifo_priority' in line and '=' in line]

    removed_text = [baseline_lines[index - 1] for index in removed]
    added_text = [candidate_lines[index - 1] for index in added]
    semantic_added = [line for line in added_text
                      if line.strip() and not line.strip().startswith('#')]
    semantic_removed = [line for line in removed_text
                        if line.strip() and not line.strip().startswith('#')]
    non_fifo_semantic = [line for line in semantic_added + semantic_removed
                         if 'target_fifo_priority' not in line]
    return dict(
        candidate_sha256=sha256_bytes(candidate_raw),
        candidate_bytes=len(candidate_raw),
        candidate_lines=len(candidate_lines),
        snapshot_sha256=sha256_bytes(baseline_raw),
        snapshot_matches_frozen_pin=sha256_bytes(baseline_raw) == SNAPSHOT_SHA256,
        snapshot_bytes=len(baseline_raw),
        snapshot_lines=len(baseline_lines),
        changed_hunks=len(opcodes),
        opcodes=opcodes,
        removed_line_numbers=removed,
        added_line_numbers=added,
        removed_text=removed_text,
        added_text=added_text,
        semantic_removed=semantic_removed,
        semantic_added=semantic_added,
        non_fifo_semantic_lines=non_fifo_semantic,
        fifo_assignments_snapshot=fifo_assignments(baseline_text),
        fifo_assignments_candidate=fifo_assignments(candidate_text),
        snapshot_fifo_line_present=baseline_text.count(SNAPSHOT_FIFO_LINE) == 1,
        candidate_fifo_line_present=candidate_text.count(CANDIDATE_FIFO_LINE) == 1,
    )


def declared_identity():
    return json.loads(CANDIDATE_JSON.read_bytes())
