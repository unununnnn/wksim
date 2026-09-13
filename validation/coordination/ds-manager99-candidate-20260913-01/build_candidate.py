"""Build the manager-only FIFO priority candidate from the frozen runner snapshot.

Reads the frozen snapshot (never modifies it), applies exactly one line change to the
manager branch of ``scheduling()``, and writes:

  candidate.py.txt   the candidate runner source
  candidate.diff     a unified diff against the snapshot, with exact line context
  candidate.json     identity: source and candidate SHA-256, the single change, and
                     the byte-identical remainder check

Nothing here is applied to any process or runtime: the candidate is a file only.

    python build_candidate.py
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SNAPSHOT = os.path.join(
    ROOT, 'validation', 'coordination', 'claude-owned-snapshot-wiring-20260913-01',
    'run_joint_flight-owned-snapshot-candidate-v3.py.txt')
SNAPSHOT_SHA256 = '1c600d7f018376f5c6fe333f0fd5da75798834c5f09e843078b0939142774373'
CANDIDATE = os.path.join(HERE, 'candidate.py.txt')
DIFF = os.path.join(HERE, 'candidate.diff')
IDENTITY = os.path.join(HERE, 'candidate.json')

OLD_LINE = "        value['target_fifo_priority'] = 50 if role=='manager' else 40\n"
NEW_LINE = (
    "        # Manager-only change under test: raise the manager target to FIFO/99,\n"
    "        # just below the 99-priority work-queue/hrtimer service threads observed on\n"
    "        # this host.  The model target stays 40, nice/-10 and the reset-on-fork rule\n"
    "        # are unchanged, so only the manager's own priority differs.\n"
    "        value['target_fifo_priority'] = 99 if role=='manager' else 40\n")
# The existing comment block names the manager's FIFO level twice; it must follow the
# new value or the source would misdescribe itself.
OLD_COMMENT_1 = "        # and inherit FIFO/50.  The model leader is then explicitly promoted to\n"
NEW_COMMENT_1 = "        # and inherit FIFO/99.  The model leader is then explicitly promoted to\n"
OLD_COMMENT_2 = "        # FIFO/40 with the same reset flag while its existing writer stays\n"
NEW_COMMENT_2 = "        # FIFO/40 with the same reset flag while its existing writer stays\n"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    raw = open(SNAPSHOT, 'rb').read()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != SNAPSHOT_SHA256:
        raise SystemExit('snapshot drifted: %s' % actual)
    text = raw.decode('utf-8')
    if text.count(OLD_LINE) != 1 or text.count(OLD_COMMENT_1) != 1:
        raise SystemExit('a targeted line does not appear exactly once')
    candidate = text.replace(OLD_LINE, NEW_LINE).replace(OLD_COMMENT_1, NEW_COMMENT_1)
    with open(CANDIDATE, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(candidate)
    diff = list(difflib.unified_diff(
        text.splitlines(keepends=True), candidate.splitlines(keepends=True),
        fromfile='run_joint_flight-owned-snapshot-candidate-v3.py.txt',
        tofile='candidate.py.txt', n=6))
    with open(DIFF, 'w', encoding='utf-8', newline='\n') as handle:
        handle.writelines(diff)
    # old/new line accounting.  SequenceMatcher may align a moved block, so the
    # editable-region anchors are stated explicitly and the unified diff is the
    # authoritative record; opcodes are reported for the new side only.
    old_lines = text.splitlines(keepends=True)
    new_lines = candidate.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    added_new_lines = []
    removed_old_lines = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ('insert', 'replace'):
            added_new_lines.extend(range(j1 + 1, j2 + 1))
        if tag in ('delete', 'replace'):
            removed_old_lines.extend(range(i1 + 1, i2 + 1))
    if not removed_old_lines:
        raise SystemExit('no snapshot line differs: nothing was changed')
    # the two edited source lines, located by content rather than by opcode
    old_priority_line = text.splitlines().index(OLD_LINE.rstrip('\n')) + 1
    old_comment_line = text.splitlines().index(OLD_COMMENT_1.rstrip('\n')) + 1
    identity = {
        'candidate': os.path.basename(CANDIDATE),
        'purpose': ('minimal manager-only scheduling candidate: manager target FIFO 50 -> 99; '
                    'not applied to any runtime or process'),
        'snapshot': {
            'path': os.path.relpath(SNAPSHOT, ROOT).replace(os.sep, '/'),
            'sha256': SNAPSHOT_SHA256,
            'bytes': len(raw),
            'lines': len(old_lines),
        },
        'candidate_sha256': sha256_file(CANDIDATE),
        'candidate_bytes': os.path.getsize(CANDIDATE),
        'candidate_lines': len(new_lines),
        'diff_sha256': sha256_file(DIFF),
        'change': {
            'function': 'scheduling',
            'edited_snapshot_lines': [old_priority_line, old_comment_line],
            'old_line_number': old_priority_line,
            'old': OLD_LINE.rstrip('\n'),
            'new_expression': "value['target_fifo_priority'] = 99 if role=='manager' else 40",
            'second_edit': {
                'snapshot_line': old_comment_line,
                'old': OLD_COMMENT_1.rstrip('\n'),
                'new': NEW_COMMENT_1.rstrip('\n'),
                'reason': 'the existing comment names the manager level and must follow the new value',
            },
            'comment_lines_added': 4,
            'diff_is_authoritative': ('candidate.diff and its sha256 are the record of the change; '
                                      'the SequenceMatcher opcodes below are indicative because a '
                                      'moved block can be aligned differently'),
            'new_side_lines_flagged_by_opcodes': added_new_lines,
            'old_side_lines_flagged_by_opcodes': removed_old_lines,
            'roles_affected': ['manager'],
            'roles_unaffected': ['model', 'fc', 'task', 'agent', 'service'],
        },
        'preserved_verbatim': [
            'target_nice: -10 for manager/model/fc, -5 otherwise',
            'model and fc target_fifo_priority: 40',
            'reset_on_fork: role in (manager, model) and async_model_evidence',
            'policy: SCHED_FIFO, plus SCHED_RESET_ON_FORK only when reset_on_fork',
            'nice setpriority and getpriority calls and their error handling',
            'sched_setscheduler / sched_getscheduler / sched_getparam calls and their error handling',
            'every other line of the runner, including all clock, 1 ms, four-tick, no-catch-up, '
            '100 ms, command and physical gates',
        ],
        'not_done': [
            'no new flag or command-line option was added',
            'no framework, harness or test hook was added to the runner',
            'the change was not applied to the live runner, the staging copy, or any process',
            'no native, scheduling or model operation was performed',
            'no performance or acceptance claim is made from this candidate',
        ],
    }
    with open(IDENTITY, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(identity, handle, indent=2, sort_keys=True)
        handle.write('\n')
    print(json.dumps({'candidate_sha256': identity['candidate_sha256'],
                      'diff_sha256': identity['diff_sha256'],
                      'edited_snapshot_lines': identity['change']['edited_snapshot_lines'],
                      'diff_lines': len(diff)}, sort_keys=True))


if __name__ == '__main__':
    main()
