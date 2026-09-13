"""Partition existing parent rate_timing_probe waits; no new instrumentation.

Reads ONLY an already-written archived rate stream (rate.jsonl or rate.jsonl.gz)
containing rate_group_start / rate_group_end / rate_timing_probe rows (the
retained spin-v2 parent run, 11737 started groups, not just the spin child).
For each started group with a prior end in the SAME segment at the SAME fixed
rate (so the no-catch-up equivalence earliest == max(ideal, prev_start+period)
applies), the interval [R, S] with

    R = earliest_start_ns   S = actual_start_ns == sample.terminal_ns
    Eprev = previous group's actual_end_ns   A = sample.entry_ns
    H = sample.initial_health_end_ns           (require Eprev <= A <= H <= S)

is partitioned by intersection with (-inf, Eprev], [Eprev, A], [A, H], [H, S]:

    priorwork_over  = [R,S] ∩ (-inf,Eprev]   previous work still running past R
    outside_begin   = [R,S] ∩ [Eprev,A]      runner work before begin_group entry
    initial_health  = [R,S] ∩ [A,H]          the initial health call
    remaining_begin = [R,S] ∩ [H,S]          loop health + sleeps + final spin

The four regions sum EXACTLY to S - R (verified per group; a violation rejects
the analysis). The probe aggregates reconcile exactly as
remaining_begin + pre_edge == loop_health + sleep_elapsed + final_spin_other,
where pre_edge = max(0, R - H) is the pre-edge begin loop; those aggregates have
no per-call timestamps, so only totals/bounds are reported and no exact late
portion inside them is ever assigned. Initial groups of a segment (no prior
end) are reported separately; priorwork equivalence is never claimed across a
segment or rate change. Non-started probe attempts (a begin_group that raised,
e.g. RateUnmet) carry no group start row by construction; they are reported
separately with their A/H/terminal/R and prior-end context, partitioned up to
terminal (the last clock read, never a release), and a completed start is never
fabricated for them. Start lateness reconciles per group as
lateness = (R - ideal) + (S - R): the no-catch-up edge carry plus the [R,S]
partition, so the largest latency region is identified without OS causal claims.

Pure stdlib; no runtime probing, no model/native/ROS/MATLAB, no OS causal claim.
The output is diagnostic-only: classification='diagnostic_only',
full_acceptance=false. CLI: --archive DIR --output FRESH.json (never overwrites).
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

SCHEMA = 'wksim.parent-probe-partition.v2'
RATES = (0.5, 1.0)
# Source identity: the archive's own snapshots are preferred; a repo file is only
# a marked fallback. If neither exists the analysis is rejected -- an unknown
# source is never accepted silently.
SNAPSHOT_FIRST = (
    ('tools/run_joint_flight.py', 'source__tools__run_joint_flight.py.txt'),
    ('Simulator/wksim_runtime/joint_rate.py',
     'source__Simulator__wksim_runtime__joint_rate.py.txt'),
    ('Simulator/wksim_runtime/joint_rate_probe.py',
     'source__Simulator__wksim_runtime__joint_rate_probe.py.txt'),
)
OPTIONAL_SNAPSHOTS = ('source__tools__rate_spin_cpu_probe.py.txt',)  # spin-child runs only


class Rejected(Exception):
    """The archived stream violates the contract this partition relies on."""


def require(condition, message):
    if not condition:
        raise Rejected(message)


def is_int(value):
    return type(value) is int


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def read_rate_rows(archive):
    archive = Path(archive)
    plain = archive / 'rate.jsonl'
    packed = archive / 'rate.jsonl.gz'
    if plain.is_file():
        raw = plain.read_bytes()
        text = raw.decode('utf-8')
        name = 'rate.jsonl'
    elif packed.is_file():
        raw = packed.read_bytes()
        text = gzip.decompress(raw).decode('utf-8')
        name = 'rate.jsonl.gz'
    else:
        raise Rejected('archive holds neither rate.jsonl nor rate.jsonl.gz')
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        require(isinstance(row, dict), 'row %d is not an object' % number)
        rows.append(row)
    return rows, raw, name


def partition_regions(R, S, Eprev, A, H):
    """The four-region intersection partition of [R, S]; sum must equal S-R."""
    require(Eprev <= A <= H <= S, 'chain Eprev<=A<=H<=S violated')
    priorwork_over = max(0, min(Eprev, S) - R)
    outside_begin = max(0, A - max(R, Eprev))
    initial_health = max(0, min(H, S) - max(R, A))
    remaining_begin = max(0, S - max(R, H))
    total = priorwork_over + outside_begin + initial_health + remaining_begin
    require(total == S - R, 'partition does not close: %d != %d' % (total, S - R))
    return dict(priorwork_over_ns=priorwork_over, outside_begin_ns=outside_begin,
                initial_health_ns=initial_health, remaining_begin_ns=remaining_begin)


def analyze(rows):
    """Validate the stream and partition every eligible started group."""
    epochs = {row.get('epoch') for row in rows}
    require(len(epochs) == 1 and isinstance(rows[0].get('epoch'), str) and rows[0]['epoch'],
            'stream is not single-epoch')
    epoch = rows[0]['epoch']
    starts = [row for row in rows if row.get('kind') == 'rate_group_start']
    unmet = [row for row in rows if row.get('kind') == 'rate_unmet']
    require(starts, 'missing group rows')

    # Single ordered pass over the rows as written: the previous list-split
    # validation could not see file order at all (it accepted a stream with
    # every end row moved to the tail). Invariant: at most one open started
    # group; start -> its started probe -> end in actual row order. A
    # non-started attempt never has an open started group.
    by_group = {}
    probe_by_tick = {}
    orphan_probes = []  # (row, closed_groups_so_far)
    previous_start = previous_end_tick = previous_segment = None
    open_group = None
    open_probe_attached = False
    closed_count = 0
    for row in rows:
        kind = row.get('kind')
        if kind == 'rate_group_start':
            require(open_group is None, 'rate_group_start while a group is still open')
            for key in ('segment_id', 'start_tick', 'end_tick', 'ideal_start_ns',
                        'ideal_end_ns', 'earliest_start_ns', 'actual_start_ns', 'lateness_ns'):
                require(is_int(row.get(key)), 'group start lacks integer %s' % key)
            rate = row.get('requested_rate')
            require(type(rate) is float and rate in RATES, 'group rate is not a frozen rate')
            period = int(4_000_000 / rate)
            start = row['start_tick']
            require(start % 4 == 0 and row['end_tick'] == start + 4, 'group ticks differ')
            require(row['tick'] == start if is_int(row.get('tick')) else False,
                    'group start row tick differs')
            require(row['ideal_end_ns'] == row['ideal_start_ns'] + period, 'ideal end equation')
            require(row['earliest_start_ns'] >= row['ideal_start_ns'], 'earliest precedes ideal')
            require(row['actual_start_ns'] >= row['earliest_start_ns'], 'actual precedes earliest')
            require(row['lateness_ns'] == max(0, row['actual_start_ns'] - row['ideal_start_ns']),
                    'start lateness equation')
            key = (row['segment_id'], start)
            require(key not in by_group, 'duplicate group %r' % (key,))
            if previous_segment == row['segment_id']:
                require(start == previous_end_tick, 'groups not contiguous in segment')
                require(row['earliest_start_ns']
                        == max(row['ideal_start_ns'], previous_start + period),
                        'no-catch-up equation differs')
            else:
                require(row['earliest_start_ns'] == row['ideal_start_ns'],
                        'segment-initial group must have earliest == ideal')
            by_group[key] = dict(start=row, end=None, period_ns=period)
            previous_start = row['actual_start_ns']
            previous_end_tick = row['end_tick']
            previous_segment = row['segment_id']
            open_group = key
            open_probe_attached = False
        elif kind == 'rate_timing_probe':
            for key in ('start_tick', 'end_tick', 'entry_ns', 'initial_health_end_ns',
                        'terminal_ns', 'ideal_start_ns', 'earliest_start_ns',
                        'entry_to_initial_health_ns', 'loop_health_ns', 'loop_health_calls',
                        'sleep_requested_ns', 'sleep_elapsed_ns', 'sleep_calls',
                        'final_spin_other_ns', 'release_excess_ns', 'observed_elapsed_ns',
                        'phase_total_ns'):
                require(is_int(row.get(key)), 'probe lacks integer %s' % key)
            require(row.get('outcome') in ('started', 'rejected', 'rate_unmet'),
                    'probe outcome differs')
            require(row['tick'] == row['start_tick'], 'probe row tick differs from start_tick')
            require(row['start_tick'] % 4 == 0 and row['end_tick'] == row['start_tick'] + 4,
                    'probe group ticks differ')
            if row['outcome'] == 'started':
                require(open_group is not None, 'started probe without an open group')
                require(row['start_tick'] == open_group[1],
                        'started probe tick differs from the open group')
                require(not open_probe_attached, 'duplicate started probe for the open group')
                probe_by_tick[row['start_tick']] = row
                open_probe_attached = True
            else:
                require(open_group is None, 'nonstarted attempt while a group is open')
                orphan_probes.append((row, closed_count))
        elif kind == 'rate_group_end':
            require(open_group is not None, 'rate_group_end without an open group')
            require((row.get('segment_id'), row.get('start_tick')) == open_group,
                    'rate_group_end does not match the open group')
            require(open_probe_attached, 'rate_group_end before its started probe')
            begin = by_group[open_group]['start']
            require(row['tick'] == begin['end_tick'], 'group end row tick differs')
            for key_name in ('ideal_start_ns', 'ideal_end_ns', 'earliest_start_ns',
                             'actual_start_ns'):
                require(row.get(key_name) == begin[key_name], 'end/start boundary mismatch')
            require(is_int(row.get('actual_end_ns')), 'end lacks integer actual_end_ns')
            require(row['actual_end_ns'] >= begin['actual_start_ns'], 'end regresses')
            require(row.get('lateness_ns')
                    == max(0, row['actual_end_ns'] - begin['ideal_end_ns']),
                    'end lateness equation')
            by_group[open_group]['end'] = row
            open_group = None
            open_probe_attached = False
            closed_count += 1
        elif kind == 'rate_unmet':
            # Collected in the header scan above; here only the field contract.
            require(is_int(row.get('tick')) and is_int(row.get('lateness_ns')),
                    'rate_unmet row lacks integer tick/lateness')
        # every other kind is unrelated to the group order and allowed in place
    require(open_group is None, 'stream ends with an open group')
    ends = [by_group[key]['end'] for key in by_group if by_group[key]['end'] is not None]
    probes = list(probe_by_tick.values())
    require(ends and probes, 'missing group end or probe rows')

    # Link each group's previous actual end inside its segment (stream order).
    previous_end_by_segment = {}
    previous_rate_by_segment = {}
    for row in starts:
        key = (row['segment_id'], row['start_tick'])
        by_group[key]['previous_actual_end_ns'] = previous_end_by_segment.get(row['segment_id'])
        by_group[key]['prior_same_segment'] = (
            row['segment_id'] in previous_end_by_segment
            and previous_rate_by_segment[row['segment_id']] == row['requested_rate'])
        end = by_group[key]['end']
        if end is not None:
            previous_end_by_segment[row['segment_id']] = end['actual_end_ns']
            previous_rate_by_segment[row['segment_id']] = row['requested_rate']

    groups = []
    aggregates = dict(loop_health_ns=0, sleep_elapsed_ns=0, final_spin_other_ns=0,
                      sleep_calls=0, sleep_max_overshoot_ns=0)
    closure_partition = 0
    closure_remaining = 0
    for row in starts:
        key = (row['segment_id'], row['start_tick'])
        group = by_group[key]
        sample = probe_by_tick.get(row['start_tick'])
        require(sample is not None, 'group %r has no probe sample' % (key,))
        require(sample['epoch'] == epoch and sample['tick'] == row['start_tick'],
                'probe identity differs')
        require(sample['ideal_start_ns'] == row['ideal_start_ns']
                and sample['earliest_start_ns'] == row['earliest_start_ns'],
                'probe edges differ from the group start row')
        require(sample['outcome'] == 'started',
                'probe outcome %r contradicts the recorded group start'
                % (sample['outcome'],))
        require(group['end'] is not None, 'started group %r has no end row' % (key,))
        S = row['actual_start_ns']
        require(sample['terminal_ns'] == S, 'probe terminal is not the actual start')
        require(sample['release_excess_ns'] == max(0, S - row['earliest_start_ns']),
                'release excess differs')
        A = sample['entry_ns']
        H = sample['initial_health_end_ns']
        # probe phase closure: H-A plus aggregates must rebuild S-A exactly
        require(sample['entry_to_initial_health_ns'] == H - A, 'initial health span differs')
        require(sample['observed_elapsed_ns'] == S - A
                and sample['phase_total_ns'] == S - A, 'probe elapsed differs')
        require(sample['phase_total_ns'] == sample['entry_to_initial_health_ns']
                + sample['loop_health_ns'] + sample['sleep_elapsed_ns']
                + sample['final_spin_other_ns'], 'probe phase accounting is not closed')
        for key_name in ('loop_health_ns', 'sleep_elapsed_ns', 'final_spin_other_ns'):
            require(sample[key_name] >= 0, 'negative probe aggregate')
        aggregates['loop_health_ns'] += sample['loop_health_ns']
        aggregates['sleep_elapsed_ns'] += sample['sleep_elapsed_ns']
        aggregates['final_spin_other_ns'] += sample['final_spin_other_ns']
        aggregates['sleep_calls'] += sample['sleep_calls']
        aggregates['sleep_max_overshoot_ns'] = max(aggregates['sleep_max_overshoot_ns'],
                                                   sample['sleep_max_overshoot_ns'])
        R = row['earliest_start_ns']
        record = dict(segment_id=row['segment_id'], start_tick=row['start_tick'],
                      end_tick=row['end_tick'], R_ns=R, S_ns=S, waited_ns=S - R,
                      ideal_start_ns=row['ideal_start_ns'],
                      edge_carry_ns=R - row['ideal_start_ns'],
                      lateness_ns=row['lateness_ns'],
                      entry_ns=A, initial_health_end_ns=H)
        Eprev = group['previous_actual_end_ns']
        if Eprev is None or not group['prior_same_segment']:
            record['priorwork_equivalence'] = ('not_applicable: segment-initial group'
                                               if Eprev is None else
                                               'not_applicable: rate/segment changed')
            record['partition'] = partition_regions(R, S, min(A, R), A, H)
            record['partition']['priorwork_over_ns'] = None  # never claimed
            record['initial_group'] = True
        else:
            record['priorwork_equivalence'] = 'same segment, same fixed period'
            record['partition'] = partition_regions(R, S, Eprev, A, H)
            record['Eprev_ns'] = Eprev
            record['initial_group'] = False
        partition = record['partition']
        require(partition['outside_begin_ns'] + partition['initial_health_ns']
                + partition['remaining_begin_ns']
                + (partition['priorwork_over_ns'] or 0) == S - R, 'partition not closed')
        closure_partition += 1
        # Exact accounting across the edge: the probe aggregates cover [H,S]; the
        # pre-edge part [H,R) of the begin loop sits outside [R,S] by design.
        pre_edge = max(0, R - H)
        record['pre_edge_begin_ns'] = pre_edge
        require(partition['remaining_begin_ns'] + pre_edge
                == sample['loop_health_ns'] + sample['sleep_elapsed_ns']
                + sample['final_spin_other_ns'],
                'probe aggregates do not reconcile with the begin span')
        closure_remaining += 1
        # Start lateness reconciles as edge carry (R-ideal) plus the [R,S] partition.
        require(record['lateness_ns'] == record['edge_carry_ns'] + record['waited_ns'],
                'start lateness does not reconcile with edge carry plus partition')
        record['aggregate_bounds_ns'] = dict(
            loop_health_ns=sample['loop_health_ns'], loop_health_calls=sample['loop_health_calls'],
            sleep_elapsed_ns=sample['sleep_elapsed_ns'], sleep_calls=sample['sleep_calls'],
            final_spin_other_ns=sample['final_spin_other_ns'])
        groups.append(record)

    # Non-started attempts: a begin_group that raised (e.g. RateUnmet) leaves a
    # probe sample with NO group start row. Report it with its own
    # A/H/terminal/R and prior-end context; terminal is the last clock read at
    # the failed check, never a release; no group start is ever fabricated.
    attempts = []
    unmet_by_tick = {}
    for row in unmet:
        unmet_by_tick.setdefault(row['tick'], []).append(row)
    for sample, closed_so_far in orphan_probes:
        require(sample['outcome'] != 'started',
                'probe claims started for tick %d but no group start row exists'
                % sample['start_tick'])
        require(sample['epoch'] == epoch, 'orphan probe epoch differs')
        require(sample['observed_elapsed_ns'] == sample['terminal_ns'] - sample['entry_ns']
                and sample['phase_total_ns'] == sample['observed_elapsed_ns'],
                'orphan probe elapsed differs')
        require(sample['phase_total_ns'] == sample['entry_to_initial_health_ns']
                + sample['loop_health_ns'] + sample['sleep_elapsed_ns']
                + sample['final_spin_other_ns'], 'orphan probe phase accounting not closed')
        require(sample['entry_to_initial_health_ns']
                == sample['initial_health_end_ns'] - sample['entry_ns'],
                'orphan probe initial health span differs')
        require(sample['release_excess_ns']
                == max(0, sample['terminal_ns'] - sample['earliest_start_ns']),
                'orphan probe release excess differs')
        prior = None
        for record in groups:
            if record['end_tick'] <= sample['start_tick']:
                prior = record
        if prior is not None:
            require(prior['end_tick'] == sample['start_tick'],
                    'orphan attempt does not follow the last completed group boundary')
        prior_actual_end = None
        if prior is not None:
            prior_group = by_group[(prior['segment_id'], prior['start_tick'])]
            prior_actual_end = prior_group['end']['actual_end_ns']
            if sample['earliest_start_ns'] == max(sample['ideal_start_ns'],
                                                  prior['S_ns'] + prior_group['period_ns']):
                continuity = 'same segment, same fixed period'
            elif sample['earliest_start_ns'] == sample['ideal_start_ns']:
                continuity = 'segment-initial attempt'
            else:
                raise Rejected('orphan attempt earliest equation differs')
        else:
            continuity = 'no prior group'
        A = sample['entry_ns']
        H = sample['initial_health_end_ns']
        terminal = sample['terminal_ns']
        if prior_actual_end is not None:
            require(prior_actual_end <= A, 'orphan attempt precedes the prior group end')
        require(A <= H <= terminal, 'orphan attempt A<=H<=terminal chain violated')
        R = sample['earliest_start_ns']
        if terminal > R:
            if prior_actual_end is None:
                partition = partition_regions(R, terminal, min(A, R), A, H)
                partition['priorwork_over_ns'] = None
            else:
                partition = partition_regions(R, terminal, prior_actual_end, A, H)
            crossed_edge = True
        else:
            # The failed check fired before the release edge: [R,terminal] is empty.
            partition = dict(priorwork_over_ns=None if prior_actual_end is None else 0,
                             outside_begin_ns=0, initial_health_ns=0, remaining_begin_ns=0)
            crossed_edge = False
        pre_edge = max(0, min(R, terminal) - H)
        require(partition['remaining_begin_ns'] + pre_edge
                == sample['loop_health_ns'] + sample['sleep_elapsed_ns']
                + sample['final_spin_other_ns'],
                'orphan probe aggregates do not reconcile')
        # A rate_unmet outcome is matched with its separate rate_unmet row when
        # present (recorded by the failed check just before the raise); the
        # attempt itself never fabricates a group start.
        matched_unmet = None
        if sample['outcome'] == 'rate_unmet':
            matches = unmet_by_tick.get(sample['start_tick'], [])
            require(len(matches) == 1, 'rate_unmet attempt lacks its rate_unmet row')
            matched = matches[0]
            require(matched.get('lateness_ns') == terminal - sample['ideal_start_ns'],
                    'rate_unmet lateness differs from attempt terminal minus ideal')
            require(matched.get('completed_groups') == closed_so_far,
                    'rate_unmet completed_groups differs from groups closed so far')
            matched_unmet = dict(tick=matched['tick'], lateness_ns=matched['lateness_ns'],
                                 completed_groups=matched.get('completed_groups'),
                                 reason=matched.get('reason'))
        attempts.append(dict(
            start_tick=sample['start_tick'], end_tick=sample['end_tick'],
            outcome=sample['outcome'], terminal_is_last_read_not_release=True,
            crossed_release_edge=crossed_edge,
            entry_ns=A, initial_health_end_ns=H, terminal_ns=terminal, R_ns=R,
            ideal_start_ns=sample['ideal_start_ns'],
            edge_carry_ns=R - sample['ideal_start_ns'],
            terminal_minus_R_ns=terminal - R,
            priorwork_equivalence=continuity,
            prior_group=(None if prior is None else dict(
                segment_id=prior['segment_id'], start_tick=prior['start_tick'],
                end_tick=prior['end_tick'], actual_end_ns=prior_actual_end)),
            partition_until_terminal=partition,
            matched_rate_unmet=matched_unmet,
            aggregate_bounds_ns=dict(
                loop_health_ns=sample['loop_health_ns'],
                loop_health_calls=sample['loop_health_calls'],
                sleep_elapsed_ns=sample['sleep_elapsed_ns'],
                sleep_calls=sample['sleep_calls'],
                final_spin_other_ns=sample['final_spin_other_ns'])))

    totals = dict(priorwork_over_ns=0, outside_begin_ns=0, initial_health_ns=0,
                  remaining_begin_ns=0, pre_edge_begin_ns=0, waited_ns=0)
    for record in groups:
        totals['waited_ns'] += record['waited_ns']
        totals['pre_edge_begin_ns'] += record['pre_edge_begin_ns']
        for name in ('outside_begin_ns', 'initial_health_ns', 'remaining_begin_ns'):
            totals[name] += record['partition'][name]
        if record['partition']['priorwork_over_ns'] is not None:
            totals['priorwork_over_ns'] += record['partition']['priorwork_over_ns']

    def top(name, count=5):
        eligible = [r for r in groups if r['partition'].get(name)]
        return [dict(start_tick=r['start_tick'], ns=r['partition'][name])
                for r in sorted(eligible, key=lambda r: -r['partition'][name])[:count]]

    unmet_rows = [dict(tick=row.get('tick'), lateness_ns=row.get('lateness_ns'),
                       completed_groups=row.get('completed_groups'))
                  for row in unmet]
    last_ticks = {row.get('tick') for row in unmet}
    around_unmet = [r for r in groups if r['end_tick'] in last_ticks
                    or r['start_tick'] in last_ticks] if last_ticks else []

    # Latency reconciliation: start lateness = edge carry (R-ideal) + [R,S] wait.
    latency_top = sorted(groups, key=lambda r: -r['lateness_ns'])[:5]
    largest_gap = None
    largest_gap_region = None
    for record in groups:
        for name in ('priorwork_over_ns', 'outside_begin_ns', 'initial_health_ns',
                     'remaining_begin_ns'):
            value = record['partition'].get(name)
            if value and (largest_gap is None or value > largest_gap[1]):
                largest_gap = (name, value, record['start_tick'])
                largest_gap_region = name
    edge_carry_total = sum(r['edge_carry_ns'] for r in groups)
    latency = dict(
        reconciliation='lateness_ns == (earliest-ideal) + (actual_start-earliest) '
                       'verified per started group',
        edge_carry_total_ns=edge_carry_total,
        waited_total_ns=totals['waited_ns'],
        top_start_lateness=[dict(start_tick=r['start_tick'], lateness_ns=r['lateness_ns'],
                                 edge_carry_ns=r['edge_carry_ns'], waited_ns=r['waited_ns'],
                                 partition=r['partition']) for r in latency_top],
        largest_wait_region_total=max(
            ((name, totals[name]) for name in ('priorwork_over_ns', 'outside_begin_ns',
                                               'initial_health_ns', 'remaining_begin_ns')),
            key=lambda item: item[1]),
        largest_single_wait_region=(None if largest_gap is None else dict(
            region=largest_gap[0], ns=largest_gap[1], start_tick=largest_gap[2])),
    )
    return dict(
        epoch=epoch, groups_started=len(groups),
        ordered_pass=dict(enforced=True, rows=len(rows), closed_in_order=closed_count,
                          attempts=len(attempts), rate_unmet_rows=len(unmet),
                          invariant='at most one open started group; '
                                    'start -> its started probe -> end in actual row order'),
        groups_with_priorwork_attribution=sum(1 for r in groups
                                              if r['partition']['priorwork_over_ns'] is not None),
        initial_groups=sum(1 for r in groups if r['initial_group']),
        nonstarted_probe_attempts=attempts,
        rate_unmet_rows=unmet_rows,
        partition_totals_ns=totals,
        closure=dict(partition_sum_equals_S_minus_R_groups=closure_partition,
                     aggregates_reconcile_with_begin_span_groups=closure_remaining),
        aggregate_probe_totals=aggregates,
        latency=latency,
        extremes=dict(priorwork_over=top('priorwork_over_ns'),
                      outside_begin=top('outside_begin_ns'),
                      initial_health=top('initial_health_ns'),
                      remaining_begin=top('remaining_begin_ns'),
                      waited=[dict(start_tick=r['start_tick'], waited_ns=r['waited_ns'],
                                   partition=r['partition'])
                              for r in sorted(groups, key=lambda r: -r['waited_ns'])[:5]]),
        around_unmet=[dict(start_tick=r['start_tick'], end_tick=r['end_tick'],
                           waited_ns=r['waited_ns'], partition=r['partition'],
                           aggregate_bounds_ns=r['aggregate_bounds_ns'])
                      for r in around_unmet],
    )


def analyze_archive(archive):
    archive = Path(archive)
    rows, raw, name = read_rate_rows(archive)
    analysis = analyze(rows)
    identity = {'rate_file': name, 'rate_sha256': sha256_bytes(raw),
                'rate_bytes': len(raw), 'rate_rows': len(rows)}
    root = Path(__file__).resolve().parents[3]
    for repo_name, snap_name in SNAPSHOT_FIRST:
        snap = archive / snap_name
        if snap.is_file():
            identity[snap_name] = sha256_bytes(snap.read_bytes())
        else:
            fallback = root / repo_name
            require(fallback.is_file(),
                    'no source identity available for ' + repo_name)
            identity['repo:' + repo_name] = sha256_bytes(fallback.read_bytes())
    for snap_name in OPTIONAL_SNAPSHOTS:
        path = archive / snap_name
        if path.is_file():
            identity[snap_name] = sha256_bytes(path.read_bytes())
    return identity, analysis


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--archive', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    output = Path(args.output)
    if output.exists():
        print('refusing to overwrite existing output: %s' % output)
        return 1
    result = dict(schema=SCHEMA, classification='diagnostic_only',
                  full_acceptance=False,
                  purpose=('classify a future large release gap using the EXISTING parent '
                           'probe; no new instrumentation, no OS causal claim'),
                  analyzer_sha256=sha256_bytes(Path(__file__).read_bytes()))
    try:
        identity, analysis = analyze_archive(args.archive)
        result.update(status='ok', identity=identity, **analysis)
    except (Rejected, KeyError, ValueError, json.JSONDecodeError) as error:
        result.update(status='rejected',
                      reason='%s: %s' % (type(error).__name__, error))
        code = 1
    else:
        result['limitations'] = [
            'partitions cover [earliest_start, actual_start] only; work before R is '
            'the previous group, never this one',
            'loop health / sleeps / final spin are aggregate durations without per-call '
            'timestamps; only totals and bounds are reported, no exact late portion '
            'inside them is assigned',
            'the pre-edge begin loop [H,R) sits outside the [R,S] partition by design; '
            'it is reported as pre_edge_begin_ns and reconciles exactly: '
            'remaining_begin + pre_edge == loop_health + sleep_elapsed + final_spin_other',
            'priorwork equivalence is claimed only within one segment at one fixed rate; '
            'segment-initial groups are reported separately',
            'non-started attempts (a begin_group that raised) are partitioned only up to '
            'terminal, the last clock read at the failed check - never a release, and '
            'never a fabricated group start',
            'start lateness reconciles per group as (earliest-ideal) edge carry plus the '
            '[R,S] partition; the largest latency region is identified by region totals '
            'with no OS causal claim',
            'single archived flight, single epoch; diagnostic_only, full_acceptance=false',
        ]
        code = 0
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'output': str(output)}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
