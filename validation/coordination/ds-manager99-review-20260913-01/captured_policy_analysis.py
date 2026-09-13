"""Read the captured owned-scheduling policies for the manager-99 boundary question.

Read-only. Uses the two captures from the successful v3 run
(``last-callbacks-run-20260913-01/flight``) plus the run's frozen targets file, which is
what the candidate's comment appeals to ("the 99-priority work-queue/hrtimer service
threads observed on this host"). Nothing is scheduled here.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

FLIGHT = ROOT / 'validation/coordination/last-callbacks-run-20260913-01/flight'
BEFORE = FLIGHT / 'owned-scheduling-before.json'
AFTER = FLIGHT / 'owned-scheduling-after.json'
TARGETS = FLIGHT / 'owned-scheduling-targets.json'
DELTA = (ROOT / 'validation/coordination/ds-live-thread-cpu-accounting-20260913-01'
         / 'owned-scheduling-delta.json')

POLICY_NAMES = {0: 'SCHED_OTHER', 1: 'SCHED_FIFO', 2: 'SCHED_RR',
                3: 'SCHED_BATCH', 5: 'SCHED_IDLE', 6: 'SCHED_DEADLINE'}
RESET_ON_FORK = 0x40000000


def policy_name(policy):
    if policy is None:
        return None
    base = policy & ~RESET_ON_FORK
    name = POLICY_NAMES.get(base, 'policy:%d' % base)
    return name + ('|RESET_ON_FORK' if policy & RESET_ON_FORK else '')


def load(path):
    return json.loads(Path(path).read_bytes())


def summarise(document):
    """Per-role leader and per-priority thread histogram from one capture."""
    roles = {}
    for role, entry in sorted(document['procs'].items()):
        threads = entry.get('threads') or []
        leader_stat = (threads[0].get('stat') if threads else None) or {}
        histogram = collections.Counter()
        comms = collections.defaultdict(list)
        for thread in threads:
            stat = thread.get('stat') or {}
            priority = stat.get('rt_priority')
            histogram[priority] += 1
            comms[priority].append(thread.get('comm'))
        roles[role] = dict(
            status=entry.get('status'),
            thread_count=entry.get('thread_count'),
            leader=dict(comm=(threads[0].get('comm') if threads else None),
                        tid=(threads[0].get('tid') if threads else None),
                        policy=leader_stat.get('policy'),
                        policy_name=policy_name(leader_stat.get('policy')),
                        rt_priority=leader_stat.get('rt_priority'),
                        nice=leader_stat.get('nice'),
                        kernel_prio=(threads[0].get('sched') or {}).get('kernel_prio')
                        if threads else None),
            rt_histogram=dict(sorted(histogram.items(),
                                     key=lambda item: (item[0] is None, item[0]))),
            comms_by_priority={str(key): sorted(value) for key, value in comms.items()},
        )
    return dict(phase=document.get('phase'), boot_id=document.get('host', {}).get('boot_id'),
                uptime_seconds=document.get('host', {}).get('uptime_seconds'),
                sched_rt_runtime_us=document.get('host', {}).get('sched_rt_runtime_us'),
                sched_rt_period_us=document.get('host', {}).get('sched_rt_period_us'),
                summary=document.get('summary'), roles=roles)


def high_priority_threads(document, floor=50):
    """Every thread at or above the floor, with pid/role/tid/comm/policy/priority."""
    found = []
    for role, entry in sorted(document['procs'].items()):
        pid = (entry.get('expected') or {}).get('pid')
        for thread in entry.get('threads') or []:
            stat = thread.get('stat') or {}
            priority = stat.get('rt_priority')
            if priority is not None and priority >= floor:
                found.append(dict(pid=pid, role=role, tid=thread.get('tid'),
                                  comm=thread.get('comm'), policy=stat.get('policy'),
                                  policy_name=policy_name(stat.get('policy')),
                                  rt_priority=priority, nice=stat.get('nice'),
                                  state=stat.get('state')))
    return sorted(found, key=lambda row: (-row['rt_priority'], row['role'], row['tid'] or 0))


def manager_identity(document):
    entry = document['procs']['manager']
    threads = entry.get('threads') or []
    return dict(expected=entry.get('expected'),
                leader=dict(comm=threads[0].get('comm'), tid=threads[0].get('tid'),
                            policy=(threads[0].get('stat') or {}).get('policy'),
                            rt_priority=(threads[0].get('stat') or {}).get('rt_priority'))
                if threads else None)


def targets_roles():
    document = load(TARGETS)
    return {role: dict(identity=value.get('identity'), argv=value.get('argv'))
            for role, value in document.items()}


def boundary_analysis():
    before = load(BEFORE)
    after = load(AFTER)
    summary_before, summary_after = summarise(before), summarise(after)
    high_before = high_priority_threads(before)
    high_after = high_priority_threads(after)
    priorities = sorted({row['rt_priority'] for row in high_before + high_after})
    top_before = max((row['rt_priority'] for row in high_before), default=None)
    top_after = max((row['rt_priority'] for row in high_after), default=None)
    fc99 = [row for row in high_before + high_after if row['rt_priority'] == 99]
    fc98 = [row for row in high_before + high_after if row['rt_priority'] == 98]
    return dict(
        captures=dict(before=summary_before, after=summary_after),
        manager=dict(before=manager_identity(before), after=manager_identity(after)),
        high_priority_threads=dict(before=high_before, after=high_after),
        observed_rt_priorities=priorities,
        highest_observed_before=top_before,
        highest_observed_after=top_after,
        threads_at_98={role: sum(1 for row in fc98 if row['role'] == role)
                       for role in sorted({row['role'] for row in fc98})},
        threads_at_99={role: sum(1 for row in fc99 if row['role'] == role)
                       for role in sorted({row['role'] for row in fc99})},
        comms_at_99=sorted({row['comm'] for row in fc99}),
        comms_at_98=sorted({row['comm'] for row in fc98}),
        roles_at_99=sorted({row['role'] for row in fc99}),
        targets=targets_roles(),
        candidate_manager_target=99,
        manager_priority_observed=50,
        delta_present=DELTA.exists(),
    )
