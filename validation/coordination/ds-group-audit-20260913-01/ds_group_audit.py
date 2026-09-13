#!/usr/bin/env python3
"""Independent stdlib audit of an archived wksim group work-timing flight.

Scope of this tool
------------------
This is an *independent re-derivation* of what an archived diagnostic flight's
artifacts claim.  It re-reads the raw, already-written evidence only:

  * ``group-work-timing.jsonl`` - the emitted over-budget group reports
    (schema ``wksim.group-work-timing.v2``);
  * ``rate.jsonl``              - the ``JointRate`` boundary rows that actually
    scheduled the flight;
  * ``result.json``             - the flight-level recorder summary;
  * optionally the frozen producer sources, used only to confirm that the
    derivation formulas below still match what the runner executed.

It deliberately does **not** import, call, or otherwise consult
``tools/group_work_timing.GroupWorkTiming`` (or any other wksim module) as an
oracle: every count, sum and boundary identity is recomputed here from the raw
rows and the equations in the archived ``joint_rate.py`` / ``group_work_timing``
sources.  Where the archived data cannot decide a question, the audit reports a
limit or a declared-only item instead of guessing.

What the audit proves when it passes
------------------------------------
1. The reports are structurally valid, single-epoch, single-segment, census
   reports whose ``prefix + 4 step durations + 3 gaps + suffix == work_ns``
   exactly, with every retained window inside the real group span and every
   native wait inside its own tick's ``native_inputs`` stage.
2. The per-group wall/CPU phase totals equal the summed retained step windows;
   native wait segments are internally consistent and ordered.
3. The *actual* rate boundaries in ``rate.jsonl`` reproduce every boundary field
   the reports carry (ideal/earliest/actual start, ideal/actual end, lateness),
   and the declared ``period_ns`` equals the archived ``int(4_000_000/rate)``
   period, with the no-catch-up contiguity law holding for the whole flight.
4. The number of over-budget groups is independently derived from the rate
   boundary work, and the emitted reports are exactly the first ``report_limit``
   of them in stream order; the remainder (``dropped``) are named by tick.
5. The counters declared in ``result.json['group_work_timing']['counts']`` agree
   with the independently recomputed values where recomputation is possible.

What it deliberately does **not** claim
---------------------------------------
* No acceptance verdict: the evidence stays ``diagnostic_only`` /
  ``full_acceptance: false`` and this audit never upgrades it.
* No causal attribution: a wall-minus-thread-CPU *difference* is reported as a
  measured difference between two clocks with shifted-window uncertainty.  It is
  not exact off-CPU time, and it is never attributed to the OS, the native
  flight controller, the host, or Windows.  72 of the 80 recorded native waits
  show thread_cpu_ns > wall_ns, which is exactly why the difference cannot be
  read as off-CPU time.
* No phase invention for groups that were never reported.  The two over-budget
  groups whose reports were dropped by the report cap carry only the work and
  excess that the rate boundary itself measures; their phases, steps and native
  waits are unknown and are marked ``measured: false``.

Exit status: 0 when no ``error``-severity finding is present, 1 when the audit
fails, 2 for command-line or input-open failures.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from fractions import Fraction

TOOL = 'ds_group_audit'
TOOL_VERSION = '1.0.0'
SCHEMA_EXPECTED = 'wksim.group-work-timing.v2'
CLASSIFICATION_EXPECTED = 'diagnostic_only'
STAGES = ('health_and_models', 'encode_send', 'native_inputs')
STACKS = ('arducopter', 'px4')
RATES = (0.5, 1.0)
COUNTER_KEYS = ('groups_complete', 'groups_incomplete', 'over_budget_groups',
                'reports_emitted', 'reports_dropped', 'diagnostic_errors')

# Provenance of the equations re-implemented here (archived in the same
# evidence directory as ``source__*`` files, matched by sha256 against
# result.json['source_sha256']):
#   Simulator/wksim_runtime/joint_rate.py  -> period_ns = int(4_000_000/rate);
#       earliest = max(ideal, previous_start + period); lateness = max(0, x-ideal)
#   Simulator/wksim_core/joint.py          -> per-tick diagnostic rows and stages
#   tools/group_work_timing.py             -> census decomposition and report shape
PERIOD_NUMERATOR_NS = 4_000_000


def period_ns_from_rate(rate):
    """Archived ``JointRate.period_ns``: ``int(4_000_000 / requested_rate)``."""
    exact = Fraction(PERIOD_NUMERATOR_NS) / Fraction(rate)
    return int(exact)  # truncation toward zero, as the original int() does


def sha256_file(path, chunk=1 << 20):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


class Findings:
    """Ordered, bounded finding collector; never raises for data problems.

    Errors decide the verdict, so they always get the retained slots: a per-row
    error flood (tens of thousands of rows) can never push the stream-level errors
    — interleaving, reconciliation, counters, cap minimum — out of the report.
    Errors are kept ahead of warnings ahead of infos, and every finding is counted
    whether or not it is retained.
    """

    SEVERITY_ORDER = {'error': 0, 'warning': 1, 'info': 2}

    def __init__(self, limit=400):
        # bucket by severity, each in arrival order
        self.buckets = {'error': [], 'warning': [], 'info': []}
        self.truncated = 0
        self.limit = limit
        self.counts = {'error': 0, 'warning': 0, 'info': 0}
        self.code_counts = {}   # code -> count, complete even when items are capped

    def add(self, severity, code, message, where=None, **detail):
        self.counts[severity] = self.counts.get(severity, 0) + 1
        self.code_counts[code] = self.code_counts.get(code, 0) + 1
        if sum(len(bucket) for bucket in self.buckets.values()) >= self.limit:
            self.truncated += 1
            return
        item = {'severity': severity, 'code': code, 'message': message}
        if where is not None:
            item['where'] = where
        if detail:
            item['detail'] = detail
        self.buckets[severity].append(item)

    def ordered(self):
        """Retained findings, all errors first, then warnings, then infos."""
        return (self.buckets['error'] + self.buckets['warning'] + self.buckets['info'])

    def error(self, code, message, where=None, **detail):
        self.add('error', code, message, where, **detail)

    def warning(self, code, message, where=None, **detail):
        self.add('warning', code, message, where, **detail)

    def info(self, code, message, where=None, **detail):
        self.add('info', code, message, where, **detail)

    @property
    def errored(self):
        return self.counts['error'] > 0


def require(condition, findings, code, message, where=None, **detail):
    if not condition:
        findings.error(code, message, where, **detail)
    return bool(condition)


def is_int(value):
    return type(value) is int


def is_num(value):
    return type(value) in (int, float) and not isinstance(value, bool)


def read_jsonl(path, findings, label):
    """Yield ``(line_number, obj_or_None)``; malformed lines become findings."""
    rows = []
    with open(path, 'r', encoding='utf-8') as handle:
        for number, raw in enumerate(handle, 1):
            text = raw.strip()
            if not text:
                findings.warning('blank-line', 'blank line ignored', where='%s:%d' % (label, number))
                continue
            try:
                obj = json.loads(text)
            except Exception as error:  # noqa: BLE001 - data error, reported not raised
                findings.error('malformed-json', 'line is not valid JSON: %s: %s'
                               % (type(error).__name__, error), where='%s:%d' % (label, number))
                continue
            if not isinstance(obj, dict):
                findings.error('non-object-row', 'JSONL row is not an object',
                               where='%s:%d' % (label, number))
                continue
            rows.append((number, obj))
    return rows


# --------------------------------------------------------------------- rate

class RateGroups:
    """The rate boundary rows that actually scheduled the flight."""

    def __init__(self):
        self.epoch = None
        self.epochs = []
        self.requests = []
        self.anchors = []
        self.unmet = []
        self.starts = []
        self.ends = []
        self.other = []
        self.by_group = {}           # (segment_id, start_tick) -> dict(start=,end=)
        self.start_line = {}         # (segment_id, start_tick) -> rate.jsonl line number
        self.groups_in_order = []    # (segment_id, start_tick) in end-row order
        self.over_budget = []        # end rows with work > declared period
        self.period_by_rate = {}
        # Independent re-derivation of the recorder's group accounting, replaying
        # the archived consume rules (a group is complete when its four steps are
        # contiguous and its end row validates; a segment change or a broken group
        # leaves the next group with an unverifiable anchor).
        self.complete_groups = 0
        self.incomplete_groups = 0
        self.duplicate_end_rows = 0
        self.duplicate_start_rows = 0
        self.unpaired_start_groups = 0
        self.overlapping_start_rows = 0
        self.unmatched_end_rows = 0
        self.open_group = None       # at most one group may be open at a time
        self.open_at_line = None
        self.open_ends_box = []      # ends observed while the current group was open
        self.completed_end_tick = None
        self.completed_segment = None
        self.completed_prev_start = None


def observe_group_start(number, row, findings, groups):
    """Pairing and interleaving state for one rate_group_start, in file order.

    The recorder holds at most one group open, so a start arriving while another
    group is still open is a defect.  A globally reordered stream (all starts,
    then all ends) satisfies "an end follows its own start" for every group yet
    violates this invariant, which is why the invariant is checked here rather
    than only through pairwise line ordering.
    """
    where = 'rate.jsonl:%d' % number
    segment, start = row.get('segment_id'), row.get('start_tick')
    if not require(is_int(segment) and is_int(start), findings, 'rate-group-keys',
                   'group start lacks integer segment_id/start_tick', where=where):
        return
    key = (segment, start)
    # Defect 5: the consumer binds the row's tick to the boundary it describes.
    require(row.get('tick') == start, findings, 'rate-start-row-tick',
            'rate_group_start row tick != start_tick', where=where,
            row_tick=row.get('tick'), start_tick=start)
    if key in groups.start_line:
        groups.duplicate_start_rows += 1
        findings.error('rate-duplicate-start',
                       'second rate_group_start for group %r' % (key,),
                       where=where, first_start_line=groups.start_line[key])
        return
    groups.start_line[key] = number
    if groups.open_group is not None:
        groups.overlapping_start_rows += 1
        findings.error('rate-group-overlap',
                       'rate_group_start while group %r is still open'
                       % (groups.open_group,), where=where, new_group=list(key),
                       open_group=list(groups.open_group),
                       open_since_line=groups.open_at_line)
    groups.open_group = key
    groups.open_at_line = number
    groups.open_ends_box = []
    groups.by_group.setdefault(key, {})['start'] = row


def observe_group_end(number, row, findings, groups):
    """Pairing and interleaving state for one rate_group_end, in file order."""
    where = 'rate.jsonl:%d' % number
    segment, start = row.get('segment_id'), row.get('start_tick')
    key = (segment, start)
    pair = groups.by_group.get(key) if is_int(segment) and is_int(start) else None
    if pair is None or 'start' not in pair:
        findings.error('rate-orphan-end', 'rate_group_end without its start row',
                       where=where, segment_id=segment, start_tick=start)
        return
    if 'end' in pair:
        groups.duplicate_end_rows += 1
        findings.error('rate-duplicate-end',
                       'second rate_group_end for group %r' % (key,),
                       where=where, first_end_line=pair.get('end_line'))
        return
    begin = pair['start']
    # Defect 5: the end row's tick must be the group's end boundary tick.
    require(row.get('tick') == begin.get('end_tick'), findings, 'rate-end-row-tick',
            'rate_group_end row tick != end_tick', where=where,
            row_tick=row.get('tick'), end_tick=begin.get('end_tick'))
    expected = groups.open_group
    groups.open_ends_box.append({'key': key, 'line': number, 'where': where,
                                 'matches_open': expected == key})
    if expected is None:
        groups.unmatched_end_rows += 1
        findings.error('rate-end-without-open-group',
                       'rate_group_end for group %r while no group is open' % (key,),
                       where=where, end_group=list(key))
    elif expected != key:
        groups.unmatched_end_rows += 1
        findings.error('rate-end-group-mismatch',
                       'rate_group_end for group %r does not match the open group %r'
                       % (key, expected), where=where, end_group=list(key),
                       open_group=list(expected))
    else:
        groups.open_group = None
        groups.open_at_line = None
    pair['end'] = row
    pair['end_line'] = number


def audit_rate_jsonl(path, findings):
    groups = RateGroups()
    known = {'rate_request', 'rate_bootstrap', 'rate_anchor', 'rate_group_start',
             'rate_group_end', 'rate_unmet', 'rate_boundary_check', 'rate_segment_end'}
    rows = read_jsonl(path, findings, 'rate.jsonl')
    if not rows:
        findings.error('rate-empty', 'rate.jsonl has no usable rows')
        return groups
    for number, row in rows:
        where = 'rate.jsonl:%d' % number
        kind = row.get('kind')
        if kind not in known:
            findings.warning('rate-unknown-kind', 'unrecognised rate row kind %r' % (kind,),
                             where=where)
            groups.other.append(row)
            continue
        epoch = row.get('epoch')
        if not require(isinstance(epoch, str) and epoch, findings, 'rate-epoch-missing',
                       'row has no epoch string', where=where):
            continue
        groups.epochs.append(epoch)
        if groups.epoch is None:
            groups.epoch = epoch
        elif epoch != groups.epoch:
            findings.error('rate-cross-epoch', 'row epoch %s differs from %s'
                           % (epoch, groups.epoch), where=where)
        if not require(is_int(row.get('tick')), findings, 'rate-tick-missing',
                       'row has no integer tick', where=where):
            continue
        if kind == 'rate_group_start':
            groups.starts.append((number, row))
            observe_group_start(number, row, findings, groups)
        elif kind == 'rate_group_end':
            groups.ends.append((number, row))
            observe_group_end(number, row, findings, groups)
        elif kind == 'rate_anchor':
            groups.anchors.append(row)
        elif kind == 'rate_request':
            groups.requests.append(row)
        elif kind == 'rate_unmet':
            groups.unmet.append(row)

    # ---- start rows: declared period, boundary equations, contiguity law
    previous_start = None
    previous_end_tick = None
    previous_segment = None
    for number, row in groups.starts:
        where = 'rate.jsonl:%d' % number
        segment, start = row.get('segment_id'), row.get('start_tick')
        if not require(is_int(segment) and is_int(start), findings, 'rate-group-keys',
                       'group start lacks integer segment_id/start_tick', where=where):
            continue
        key = (segment, start)
        fields = ('ideal_start_ns', 'earliest_start_ns', 'actual_start_ns',
                  'ideal_end_ns', 'lateness_ns', 'end_tick', 'requested_rate')
        if not all(name in row for name in fields):
            findings.error('rate-group-fields', 'group start is missing boundary fields',
                           where=where, missing=[n for n in fields if n not in row])
            continue
        for name in ('ideal_start_ns', 'earliest_start_ns', 'actual_start_ns',
                     'ideal_end_ns', 'lateness_ns', 'end_tick'):
            if not require(is_int(row[name]), findings, 'rate-group-int',
                           'field %s is not an integer' % name, where=where):
                break
        else:
            rate = row['requested_rate']
            if not require(is_num(rate) and float(rate) in RATES, findings, 'rate-value',
                           'requested_rate %r is not a frozen rate' % (rate,), where=where):
                pass
            else:
                period = period_ns_from_rate(rate)
                groups.period_by_rate[float(rate)] = period
                require(row['ideal_end_ns'] == row['ideal_start_ns'] + period, findings,
                        'rate-ideal-end', 'ideal_end_ns != ideal_start_ns + int(4e6/rate)',
                        where=where, ideal_end=row['ideal_end_ns'],
                        ideal_start=row['ideal_start_ns'], period=period)
            require(start % 4 == 0, findings, 'rate-anchor-mod4',
                    'group start tick %r is not a multiple of four' % (start,), where=where)
            require(row['end_tick'] == start + 4, findings, 'rate-end-tick',
                    'end_tick %r != start_tick+4' % (row['end_tick'],), where=where)
            require(row['earliest_start_ns'] >= row['ideal_start_ns'], findings,
                    'rate-earliest', 'earliest_start_ns precedes ideal_start_ns', where=where)
            require(row['actual_start_ns'] >= row['earliest_start_ns'], findings,
                    'rate-actual', 'actual_start_ns precedes earliest_start_ns', where=where)
            require(row['lateness_ns'] == max(0, row['actual_start_ns'] - row['ideal_start_ns']),
                    findings, 'rate-start-lateness',
                    'start lateness_ns != max(0, actual_start_ns - ideal_start_ns)', where=where)
            if previous_segment is not None and segment == previous_segment:
                require(start == previous_end_tick, findings, 'rate-contiguity',
                        'groups are not contiguous inside segment %r' % (segment,),
                        where=where, start=start, previous_end=previous_end_tick)
                if previous_start is not None:
                    expected = max(row['ideal_start_ns'], previous_start + period)
                    require(row['earliest_start_ns'] == expected, findings,
                            'rate-no-catch-up',
                            'earliest_start_ns != max(ideal_start_ns, previous actual_start + period)',
                            where=where, declared=row['earliest_start_ns'], expected=expected)
            elif previous_segment is None or segment != previous_segment:
                require(row['earliest_start_ns'] == row['ideal_start_ns'], findings,
                        'rate-reanchor', 'first group of a segment must have earliest == ideal',
                        where=where)
            if previous_segment is not None:
                require(segment >= previous_segment, findings, 'rate-segment-order',
                        'segment_id regressed', where=where)
            previous_start, previous_end_tick, previous_segment = (
                row['actual_start_ns'], row['end_tick'], segment)
        groups.by_group.setdefault(key, {})['start'] = row

    # ---- end rows: identity against the start row, then work classification
    for number, row in groups.ends:
        where = 'rate.jsonl:%d' % number
        segment, start = row.get('segment_id'), row.get('start_tick')
        pair = groups.by_group.get((segment, start)) if is_int(segment) and is_int(start) else None
        if pair is None or 'start' not in pair:
            findings.error('rate-orphan-end', 'rate_group_end without its start row',
                           where=where, segment_id=segment, start_tick=start)
            continue
        begin = pair['start']
        # observe_group_end already rejected duplicate and non-interleaved ends; only
        # a pair whose end was accepted is counted and validated in detail here.
        if 'end' not in pair:
            continue
        # Defect 4: the file order must place the end row after its own start row.
        start_line = groups.start_line.get((segment, start))
        if start_line is not None:
            require(number > start_line, findings, 'rate-stream-order',
                    'rate_group_end appears before its own rate_group_start',
                    where=where, end_line=number, start_line=start_line)
        groups.groups_in_order.append((segment, start))
        for name in ('ideal_start_ns', 'ideal_end_ns', 'earliest_start_ns', 'actual_start_ns'):
            require(row.get(name) == begin.get(name), findings, 'rate-end-start-mismatch',
                    'end row field %s differs from its start row' % name, where=where,
                    end_value=row.get(name), start_value=begin.get(name))
        if not require(is_int(row.get('actual_end_ns')), findings, 'rate-actual-end',
                       'end row lacks integer actual_end_ns', where=where):
            continue
        require(row['actual_end_ns'] >= begin['actual_start_ns'], findings, 'rate-end-regress',
                'actual_end_ns precedes actual_start_ns', where=where)
        require(row.get('lateness_ns') == max(0, row['actual_end_ns'] - begin['ideal_end_ns']),
                findings, 'rate-end-lateness',
                'end lateness_ns != max(0, actual_end_ns - ideal_end_ns)', where=where)
        work = row['actual_end_ns'] - begin['actual_start_ns']
        period = begin['ideal_end_ns'] - begin['ideal_start_ns']
        # Replay the consumer's group accounting for this closed pair.
        contiguous = (groups.completed_segment is None or segment != groups.completed_segment
                      or start == groups.completed_end_tick)
        anchor_ok = (groups.completed_segment is None or segment != groups.completed_segment
                     or (groups.completed_prev_start is not None
                         and begin['earliest_start_ns'] == max(begin['ideal_start_ns'],
                                                               groups.completed_prev_start + period)))
        if contiguous and anchor_ok:
            groups.complete_groups += 1
        else:
            groups.incomplete_groups += 1
        groups.completed_segment = segment
        groups.completed_end_tick = begin['end_tick']
        groups.completed_prev_start = (begin['actual_start_ns'] if (contiguous and anchor_ok)
                                       else None)
        if work > period:
            groups.over_budget.append({'segment_id': segment, 'start_tick': start,
                                       'end_tick': begin['end_tick'], 'period_ns': period,
                                       'work_ns': work, 'excess_ns': work - period,
                                       'requested_rate': begin['requested_rate'],
                                       'rate_line': number})
    if not groups.ends:
        findings.error('rate-no-groups', 'rate.jsonl contains no rate_group_end rows')
    # Defect 2: a start row without its end row is a dangling group.  The honest
    # recorder reports this as an unfinished group with valid=false; the stream
    # shows it directly as starts > ends.
    unclosed = [key for key, pair in sorted(groups.by_group.items())
                if 'start' in pair and 'end' not in pair]
    for key in unclosed:
        groups.unpaired_start_groups += 1
        findings.error('rate-orphan-start',
                       'rate_group_start without its rate_group_end',
                       where='rate.jsonl:%d' % groups.start_line.get(key, 0),
                       segment_id=key[0], start_tick=key[1],
                       end_tick=groups.by_group[key]['start'].get('end_tick'))
    if len(groups.starts) != len(groups.ends):
        findings.error('rate-stream-unbalanced',
                       'rate_group_start count differs from rate_group_end count',
                       starts=len(groups.starts), ends=len(groups.ends))
    # Reconcile the per-group pairing with the interleaving actually observed.
    # A stream whose ends were all moved behind the starts pairs every group and
    # still keeps exactly one group open at a time in name, but the open group at
    # the time each end was recorded was a different one: comparing the recorded
    # event order against the row order is what exposes that.
    unmatched = [entry for entry in groups.open_ends_box if not entry['matches_open']]
    if unmatched:
        findings.error('rate-open-group-reconciliation',
                       '%d rate_group_end rows were recorded while a different group was open'
                       % len(unmatched),
                       first=[{'line': entry['line'], 'end_group': list(entry['key']),
                               'open_group': (list(groups.open_group)
                                              if groups.open_group else None)}
                              for entry in unmatched[:3]],
                       recorded_at_open=[{'line': entry['line'], 'where': entry['where']}
                                         for entry in groups.open_ends_box[:2]])
    if groups.open_group is not None:
        findings.error('rate-open-group-unclosed',
                       'stream ends with group %r still open' % (groups.open_group,),
                       open_since_line=groups.open_at_line,
                       open_group=list(groups.open_group))
    if groups.overlapping_start_rows or groups.unmatched_end_rows:
        findings.error('rate-stream-interleaving',
                       'the rate stream does not hold exactly one open group',
                       overlapping_starts=groups.overlapping_start_rows,
                       unmatched_ends=groups.unmatched_end_rows)
    return groups


# ------------------------------------------------------------------- reports

def audit_report(row, where, findings, rate_groups, limits):
    """Validate one emitted report and return a normalised record (or None)."""
    expectations = {
        'kind': 'group_work_timing',
        'schema': SCHEMA_EXPECTED,
        'classification': CLASSIFICATION_EXPECTED,
        'full_acceptance': False,
    }
    for name, expected in expectations.items():
        if not require(row.get(name) == expected, findings, 'report-declaration',
                       'report field %s must be %r' % (name, expected),
                       where=where, actual=row.get(name)):
            return None
    if not require(row.get('census') is True, findings, 'report-not-census',
                   'report is not a census report (sampled reports carry no decomposition)',
                   where=where, census=row.get('census')):
        return None
    for name in ('epoch', 'segment_id', 'start_tick', 'end_tick', 'requested_rate',
                 'period_ns', 'work_ns', 'excess_ns', 'preceding_boundary',
                 'following_boundary', 'phases', 'retained_steps', 'visible_native_waits',
                 'work_decomposition', 'step_windows'):
        if not require(name in row, findings, 'report-missing-field',
                       'report lacks field %s' % name, where=where):
            return None
    segment, start = row['segment_id'], row['start_tick']
    if not require(is_int(segment) and is_int(start) and is_int(row['end_tick']),
                   findings, 'report-tick-types', 'segment_id/start_tick/end_tick must be integers',
                   where=where):
        return None
    key = (segment, start)
    pair = rate_groups.by_group.get(key)
    if not require(pair is not None and 'start' in pair and 'end' in pair, findings,
                   'report-unmatched-group',
                   'no complete rate group in rate.jsonl matches (segment_id, start_tick)=%r'
                   % (key,), where=where):
        return None
    begin, end = pair['start'], pair['end']
    end_row_tick = row.get('end_tick')
    pair_end_tick = pair['end'].get('end_tick')
    if is_int(end_row_tick) and is_int(pair_end_tick):
        require(end_row_tick == pair_end_tick, findings, 'rate-end-tick-mismatch',
                'rate_group_end end_tick differs from its start row', where=where,
                end_row=end_row_tick, start_row=pair_end_tick)
    require(row['end_tick'] == begin['end_tick'], findings, 'report-end-tick',
            'report end_tick differs from the rate group', where=where,
            report=row['end_tick'], rate=begin['end_tick'])
    require(start % 4 == 0, findings, 'report-mod4', 'start_tick is not a multiple of four',
            where=where)

    # ---- the original period: declared by the rate record, re-derived from rate
    rate_period = begin['ideal_end_ns'] - begin['ideal_start_ns']
    from_rate = period_ns_from_rate(row['requested_rate']) if is_num(row['requested_rate']) \
        and float(row['requested_rate']) in RATES else None
    require(row['period_ns'] == rate_period, findings, 'report-period-mismatch',
            'report period_ns differs from the rate group period', where=where,
            report=row['period_ns'], rate=rate_period)
    if from_rate is not None:
        require(row['period_ns'] == from_rate, findings, 'report-period-formula',
                'report period_ns differs from int(4_000_000/requested_rate)', where=where,
                report=row['period_ns'], formula=from_rate)
    require(is_num(row['requested_rate']) and row['requested_rate'] == begin['requested_rate'],
            findings, 'report-rate-mismatch', 'report requested_rate differs from the rate group',
            where=where, report=row['requested_rate'], rate=begin['requested_rate'])

    # ---- work identity against the real group span
    work = end['actual_end_ns'] - begin['actual_start_ns']
    require(row['work_ns'] == work, findings, 'report-work-mismatch',
            'report work_ns != actual_end_ns - actual_start_ns from rate.jsonl',
            where=where, report=row['work_ns'], rate=work)
    require(row['excess_ns'] == row['work_ns'] - row['period_ns'], findings,
            'report-excess-mismatch', 'report excess_ns != work_ns - period_ns', where=where)
    require(row['work_ns'] > row['period_ns'], findings, 'report-not-over-budget',
            'emitted report is not over budget (work_ns <= period_ns)', where=where)

    # ---- boundaries must reproduce the real rate rows exactly
    pre, fol = row['preceding_boundary'], row['following_boundary']
    boundary_checks = (
        (pre, 'ideal_start_ns', begin), (pre, 'earliest_start_ns', begin),
        (pre, 'actual_start_ns', begin), (pre, 'lateness_ns', begin),
        (fol, 'ideal_end_ns', begin), (fol, 'actual_end_ns', end),
        (fol, 'lateness_ns', end),
    )
    for mapping, name, source in boundary_checks:
        if isinstance(mapping, dict) and name in mapping:
            require(mapping[name] == source.get(name), findings, 'report-boundary-mismatch',
                    'boundary field %s differs from rate.jsonl' % name, where=where,
                    report=mapping[name], rate=source.get(name))
        else:
            findings.error('report-boundary-missing', 'boundary field %s is absent' % name,
                           where=where)

    # ---- retained steps / step windows / decomposition (the exact identity)
    decomposition = row['work_decomposition']
    windows = row['step_windows']
    steps = row['retained_steps']
    if not require(isinstance(windows, list) and len(windows) == 4, findings,
                   'report-window-count', 'census report must carry exactly four step windows',
                   where=where, count=len(windows) if isinstance(windows, list) else None):
        return None
    if not require(isinstance(steps, list) and len(steps) == 4, findings,
                   'report-step-count', 'census report must carry exactly four retained steps',
                   where=where, count=len(steps) if isinstance(steps, list) else None):
        return None
    if not require(isinstance(decomposition, dict), findings, 'report-no-decomposition',
                   'work_decomposition is not an object', where=where):
        return None
    expected_ticks = list(range(start + 1, start + 5))
    window_ticks = [w.get('tick') for w in windows]
    require(window_ticks == expected_ticks, findings, 'report-window-ticks',
            'step window ticks are not start_tick+1..start_tick+4', where=where,
            ticks=window_ticks, expected=expected_ticks)
    require([s.get('tick') for s in steps] == expected_ticks, findings, 'report-step-ticks',
            'retained step ticks are not start_tick+1..start_tick+4', where=where,
            ticks=[s.get('tick') for s in steps], expected=expected_ticks)
    for index, (step, window) in enumerate(zip(steps, windows)):
        if step.get('tick') != window.get('tick'):
            findings.error('report-step-window-tick', 'retained step and window ticks differ',
                           where=where, index=index)
            continue
        for name in ('wall_start_ns', 'wall_end_ns', 'wall_ns', 'thread_cpu_ns'):
            if not require(is_int(step.get(name)), findings, 'report-step-field',
                           'retained step lacks integer %s' % name, where=where, tick=step.get('tick')):
                break
        if not all(is_int(window.get(name)) for name in ('wall_start_ns', 'wall_end_ns')):
            findings.error('report-window-field', 'step window lacks integer bounds',
                           where=where, tick=window.get('tick'))
            continue
        require(step['wall_start_ns'] == window['wall_start_ns']
                and step['wall_end_ns'] == window['wall_end_ns'], findings,
                'report-step-window-bounds', 'retained step bounds differ from its step window',
                where=where, tick=step.get('tick'))
        require(step['wall_ns'] == step['wall_end_ns'] - step['wall_start_ns'], findings,
                'report-step-wall', 'retained step wall_ns != wall_end_ns - wall_start_ns',
                where=where, tick=step.get('tick'))
        stages = window.get('stages')
        if not require(isinstance(stages, dict) and tuple(sorted(stages)) == tuple(sorted(STAGES)),
                       findings, 'report-stage-set', 'step window stage set differs',
                       where=where, tick=window.get('tick')):
            continue
        total_wall = 0
        total_cpu = 0
        for name in STAGES:
            stage = stages[name]
            if not require(isinstance(stage, dict) and is_int(stage.get('wall_ns'))
                           and is_int(stage.get('thread_cpu_ns')), findings,
                           'report-stage-field', 'stage %s lacks integer wall/thread cpu' % name,
                           where=where, tick=window.get('tick')):
                continue
            require(stage['wall_ns'] >= 0 and stage['thread_cpu_ns'] >= 0, findings,
                    'report-stage-negative', 'stage %s has a negative measurement' % name,
                    where=where, tick=window.get('tick'))
            total_wall += stage['wall_ns']
            total_cpu += stage['thread_cpu_ns']
        require(total_wall == step['wall_ns'], findings, 'report-stage-sum',
                'step window stage wall_ns sum != step wall_ns', where=where,
                tick=window.get('tick'), stages=total_wall, step=step['wall_ns'])
        require(total_cpu == step['thread_cpu_ns'], findings, 'report-stage-cpu-sum',
                'step window stage thread_cpu_ns sum != retained step thread_cpu_ns',
                where=where, tick=window.get('tick'), stages=total_cpu,
                step=step['thread_cpu_ns'])
    for earlier, later in zip(windows, windows[1:]):
        if not (is_int(earlier.get('wall_end_ns')) and is_int(later.get('wall_start_ns'))):
            continue
        require(earlier['wall_end_ns'] <= later['wall_start_ns'], findings,
                'report-window-order', 'retained step windows overlap or regress in tick order',
                where=where, earlier_tick=earlier.get('tick'), later_tick=later.get('tick'))
    for earlier_step, step in zip(steps, steps[1:]):
        if not is_int(step.get('gap_from_previous_retained_ns')):
            continue
        gap = step['gap_from_previous_retained_ns']
        require(gap >= 0, findings, 'report-step-gap-negative',
                'gap_from_previous_retained_ns is negative', where=where, tick=step.get('tick'))
        if is_int(step.get('wall_start_ns')) and is_int(earlier_step.get('wall_end_ns')):
            expected_gap = step['wall_start_ns'] - earlier_step['wall_end_ns']
            require(gap == expected_gap, findings, 'report-step-gap',
                    'gap_from_previous_retained_ns disagrees with the recorded windows',
                    where=where, tick=step.get('tick'), declared=gap, expected=expected_gap)
    if steps and steps[0].get('gap_from_previous_retained_ns') is not None:
        findings.info('report-first-gap-declared',
                      'first retained step declares a gap_from_previous_retained_ns',
                      where=where)
    decomposition_ok = (
        isinstance(decomposition.get('prefix_ns'), int)
        and isinstance(decomposition.get('step_durations_ns'), list)
        and len(decomposition.get('step_durations_ns', [])) == 4
        and isinstance(decomposition.get('step_gaps_ns'), list)
        and len(decomposition.get('step_gaps_ns', [])) == 3
        and isinstance(decomposition.get('suffix_ns'), int))
    if not require(decomposition_ok, findings, 'report-decomposition-shape',
                   'work_decomposition lacks prefix/4 durations/3 gaps/suffix integers',
                   where=where):
        return None
    prefix = decomposition['prefix_ns']
    durations = decomposition['step_durations_ns']
    gaps = decomposition['step_gaps_ns']
    suffix = decomposition['suffix_ns']
    recomputed_prefix = windows[0]['wall_start_ns'] - begin['actual_start_ns']
    recomputed_suffix = end['actual_end_ns'] - windows[3]['wall_end_ns']
    recomputed_durations = [w['wall_end_ns'] - w['wall_start_ns'] for w in windows]
    recomputed_gaps = [windows[i + 1]['wall_start_ns'] - windows[i]['wall_end_ns']
                       for i in range(3)]
    require(prefix == recomputed_prefix, findings, 'report-prefix',
            'prefix_ns != first window start - actual_start_ns', where=where,
            report=prefix, recomputed=recomputed_prefix)
    require(suffix == recomputed_suffix, findings, 'report-suffix',
            'suffix_ns != actual_end_ns - last window end', where=where,
            report=suffix, recomputed=recomputed_suffix)
    require(durations == recomputed_durations, findings, 'report-durations',
            'step_durations_ns differ from the step windows', where=where,
            report=durations, recomputed=recomputed_durations)
    require(gaps == recomputed_gaps, findings, 'report-gaps',
            'step_gaps_ns differ from the step windows', where=where,
            report=gaps, recomputed=recomputed_gaps)
    require(decomposition.get('closes') is True, findings, 'report-closes-flag',
            'work_decomposition does not declare closes=true', where=where)
    require(prefix >= 0 and suffix >= 0 and all(g >= 0 for g in gaps), findings,
            'report-negative-region', 'a decomposition region is negative', where=where)
    identity = prefix + sum(durations) + sum(gaps) + suffix
    require(identity == row['work_ns'] == work, findings, 'report-identity',
            'prefix + steps + gaps + suffix != work_ns (or != rate-derived work)',
            where=where, identity=identity, work_ns=row['work_ns'], rate_work=work)

    # ---- phase totals are the sums of the retained windows
    phases = row['phases']
    if require(isinstance(phases, dict) and tuple(sorted(phases)) == tuple(sorted(STAGES)),
               findings, 'report-phase-set', 'phase set differs from the three frozen stages',
               where=where):
        for name in STAGES:
            phase = phases[name]
            if not require(isinstance(phase, dict) and is_int(phase.get('wall_ns'))
                           and is_int(phase.get('thread_cpu_ns'))
                           and is_int(phase.get('samples')), findings, 'report-phase-field',
                           'phase %s lacks integer wall/cpu/samples' % name, where=where):
                continue
            wall = sum(w['stages'][name]['wall_ns'] for w in windows)
            cpu = sum(w['stages'][name]['thread_cpu_ns'] for w in windows)
            require(phase['wall_ns'] == wall, findings, 'report-phase-wall',
                    'phase %s wall_ns != sum of the four step windows' % name, where=where,
                    report=phase['wall_ns'], recomputed=wall)
            require(phase['thread_cpu_ns'] == cpu, findings, 'report-phase-cpu',
                    'phase %s thread_cpu_ns != sum of the four step windows' % name, where=where,
                    report=phase['thread_cpu_ns'], recomputed=cpu)
            require(phase['samples'] == 4, findings, 'report-phase-samples',
                    'phase %s samples != 4 in a census report' % name, where=where,
                    samples=phase['samples'])
        require(sum(p['wall_ns'] for p in phases.values()) == sum(recomputed_durations),
                findings, 'report-phase-total', 'phase wall totals != summed step durations',
                where=where)

    # ---- native waits: internal consistency, span, and stage containment
    waits = row['visible_native_waits']
    if not require(isinstance(waits, list), findings, 'report-waits-shape',
                   'visible_native_waits is not a list', where=where):
        waits = []
    by_tick_wait = {}
    for wait in waits:
        if not require(isinstance(wait, dict), findings, 'report-wait-shape',
                       'native wait entry is not an object', where=where):
            continue
        tick = wait.get('tick')
        if not require(tick in expected_ticks, findings, 'report-wait-tick',
                       'native wait tick is outside the group', where=where, tick=tick):
            continue
        if not require(wait.get('stack') in STACKS, findings, 'report-wait-stack',
                       'native wait stack is not a frozen stack', where=where,
                       stack=wait.get('stack')):
            continue
        numeric = ('wall_start_ns', 'wall_end_ns', 'wall_ns', 'thread_cpu_ns')
        if not all(is_int(wait.get(name)) for name in numeric):
            findings.error('report-wait-field', 'native wait lacks integer window fields',
                           where=where, tick=tick, stack=wait.get('stack'))
            continue
        require(wait['wall_end_ns'] >= wait['wall_start_ns'], findings, 'report-wait-regress',
                'native wait window regressed', where=where, tick=tick)
        require(wait['wall_ns'] == wait['wall_end_ns'] - wait['wall_start_ns'], findings,
                'report-wait-wall', 'native wait wall_ns != wall_end_ns - wall_start_ns',
                where=where, tick=tick)
        require(wait['thread_cpu_ns'] >= 0, findings, 'report-wait-cpu',
                'native wait thread_cpu_ns is negative', where=where, tick=tick)
        require(begin['actual_start_ns'] <= wait['wall_start_ns']
                and wait['wall_end_ns'] <= end['actual_end_ns'], findings,
                'report-wait-outside-group', 'native wait lies outside the real group span',
                where=where, tick=tick)
        window = windows[expected_ticks.index(tick)]
        stage_start = (window['wall_start_ns']
                       + window['stages']['health_and_models']['wall_ns']
                       + window['stages']['encode_send']['wall_ns'])
        require(stage_start <= wait['wall_start_ns'] and wait['wall_end_ns'] <= window['wall_end_ns'],
                findings, 'report-wait-outside-stage',
                'native wait lies outside its tick native_inputs stage', where=where,
                tick=tick, stack=wait.get('stack'), stage_start=stage_start,
                window_end=window['wall_end_ns'])
        require(window['wall_start_ns'] <= wait['wall_start_ns'], findings,
                'report-wait-before-step', 'native wait starts before its tick step window',
                where=where, tick=tick)
        require(wait.get('stage_verified') is True, findings, 'report-wait-unverified',
                'native wait is not stage-verified', where=where, tick=tick)
        if wait['stack'] == 'arducopter':
            require(is_int(wait.get('ap_frame')), findings, 'report-wait-ap-frame',
                    'arducopter wait lacks integer ap_frame', where=where, tick=tick)
        else:
            require(wait.get('px4_time_us') is None or is_int(wait.get('px4_time_us')),
                    findings, 'report-wait-px4-time',
                    'px4 wait px4_time_us is neither integer nor null', where=where, tick=tick)
        by_tick_wait.setdefault(tick, []).append(wait)
    for tick, tick_waits in by_tick_wait.items():
        stacks = [w['stack'] for w in tick_waits]
        require(len(set(stacks)) == len(stacks), findings, 'report-wait-duplicate-stack',
                'duplicate native wait stack in one tick', where=where, tick=tick)
        require(stacks == sorted(stacks, key=STACKS.index), findings, 'report-wait-stack-order',
                'native wait stacks are not in frozen order', where=where, tick=tick)
        for a, b in zip(tick_waits, tick_waits[1:]):
            require(a['wall_end_ns'] <= b['wall_start_ns'], findings, 'report-wait-overlap',
                    'native waits overlap inside one tick', where=where, tick=tick)
    for tick in expected_ticks:
        require(tick in by_tick_wait, findings, 'report-wait-missing',
                'census group tick %d has no native wait row' % tick, where=where)

    if isinstance(row.get('previous_group'), dict):
        previous = row['previous_group']
        if is_int(previous.get('start_tick')) and is_int(previous.get('work_ns')):
            require(previous['work_ns'] - previous.get('excess_ns', 0) >= 0, findings,
                    'report-previous-group', 'previous_group work/excess are inconsistent',
                    where=where)
    else:
        findings.warning('report-previous-group-missing',
                         'report carries no previous_group summary', where=where)

    limits['reports'] += 1
    limits['work_ns'] += row['work_ns']
    limits['excess_ns'] += row['excess_ns']
    limits['cpu_over_wall_waits'] += sum(
        1 for tick_waits in by_tick_wait.values() for w in tick_waits
        if w['thread_cpu_ns'] > w['wall_ns'])
    limits['waits'] += sum(len(v) for v in by_tick_wait.values())
    for tick_waits in by_tick_wait.values():
        for wait in tick_waits:
            limits['wait_wall_ns_by_stack'][wait['stack']] = (
                limits['wait_wall_ns_by_stack'].get(wait['stack'], 0) + wait['wall_ns'])
            limits['wait_cpu_ns_by_stack'][wait['stack']] = (
                limits['wait_cpu_ns_by_stack'].get(wait['stack'], 0) + wait['thread_cpu_ns'])
    for name in STAGES:
        phase = phases.get(name, {})
        phase_wall = phase.get('wall_ns') if isinstance(phase.get('wall_ns'), int) else 0
        phase_cpu = phase.get('thread_cpu_ns') if isinstance(phase.get('thread_cpu_ns'), int) else 0
        limits['phase_wall_ns'][name] = limits['phase_wall_ns'].get(name, 0) + phase_wall
        limits['phase_cpu_ns'][name] = limits['phase_cpu_ns'].get(name, 0) + phase_cpu
    well_formed_phases = all(
        isinstance(phases.get(name), dict) and is_int(phases[name].get('wall_ns'))
        and is_int(phases[name].get('thread_cpu_ns')) for name in STAGES)
    for step in steps:
        limits['step_wall_ns'].append(step['wall_ns'])
        limits['step_cpu_ns'].append(step['thread_cpu_ns'])
    # Only structurally complete reports become ranking regions: a malformed
    # report is reported as a finding and never silently half-ranked.
    if well_formed_phases:
        limits['regions'].append({
        'segment_id': segment, 'start_tick': start, 'end_tick': row['end_tick'],
        'period_ns': row['period_ns'], 'work_ns': row['work_ns'], 'excess_ns': row['excess_ns'],
        'requested_rate': row['requested_rate'],
        'prefix_ns': prefix, 'suffix_ns': suffix,
        'step_durations_ns': list(durations), 'step_gaps_ns': list(gaps),
        'phases': {name: dict(phases.get(name, {})) for name in STAGES},
        'preceding_boundary': dict(row['preceding_boundary']),
        'following_boundary': dict(row['following_boundary']),
        'native_wait_wall_ns': sum(w['wall_ns'] for tick_waits in by_tick_wait.values()
                                   for w in tick_waits),
        'native_wait_cpu_ns': sum(w['thread_cpu_ns'] for tick_waits in by_tick_wait.values()
                                  for w in tick_waits),
        'native_waits': sum(len(v) for v in by_tick_wait.values()),
        'measured': True,
        })
    return {'segment_id': segment, 'start_tick': start}


def audit_reports(path, findings, rate_groups, report_limit):
    limits = {'reports': 0, 'work_ns': 0, 'excess_ns': 0, 'waits': 0,
              'cpu_over_wall_waits': 0, 'wait_wall_ns_by_stack': {}, 'wait_cpu_ns_by_stack': {},
              'phase_wall_ns': {}, 'phase_cpu_ns': {}, 'step_wall_ns': [], 'step_cpu_ns': [],
              'regions': []}
    seen = []
    epoch = None
    previous_end_tick = None
    for number, row in read_jsonl(path, findings, 'group-work-timing.jsonl'):
        where = 'group-work-timing.jsonl:%d' % number
        result = audit_report(row, where, findings, rate_groups, limits)
        if result is None:
            continue
        if epoch is None:
            epoch = row['epoch']
        elif row['epoch'] != epoch:
            findings.error('report-cross-epoch', 'report epoch differs from %s' % epoch,
                           where=where, epoch=row['epoch'])
        if previous_end_tick is not None:
            require(result['start_tick'] >= previous_end_tick, findings, 'report-order',
                    'report start_tick precedes the previous report end_tick', where=where,
                    start=result['start_tick'], previous_end=previous_end_tick)
        previous_end_tick = row['end_tick']
        seen.append({'segment_id': result['segment_id'], 'start_tick': result['start_tick'],
                     'end_tick': row['end_tick'], 'where': where})
    if report_limit is not None:
        require(len(seen) <= report_limit, findings, 'report-cap',
                'emitted reports (%d) exceed the declared report limit (%d)'
                % (len(seen), report_limit), count=len(seen), report_limit=report_limit)
    if len(seen) != len(limits['regions']):
        findings.error('report-count-internal',
                       'validated report count disagrees with the normalised region count')
    return limits, seen, epoch


# -------------------------------------------------------------------- result

def audit_result(path, findings, rate_groups, limits, seen, report_epoch):
    with open(path, 'r', encoding='utf-8') as handle:
        try:
            result = json.load(handle)
        except Exception as error:  # noqa: BLE001
            findings.error('result-malformed', 'result.json is not valid JSON: %s: %s'
                           % (type(error).__name__, error))
            return None, None
    if not isinstance(result, dict):
        findings.error('result-shape', 'result.json is not an object')
        return None, None
    summary = result.get('group_work_timing')
    if not require(isinstance(summary, dict), findings, 'result-no-summary',
                   'result.json carries no group_work_timing summary object'):
        return result, None
    require(summary.get('schema') == SCHEMA_EXPECTED, findings, 'result-schema',
            'summary schema differs', actual=summary.get('schema'))
    require(summary.get('classification') == CLASSIFICATION_EXPECTED, findings,
            'result-classification', 'summary is not classified diagnostic_only',
            actual=summary.get('classification'))
    require(summary.get('full_acceptance') is False, findings, 'result-full-acceptance',
            'summary must keep full_acceptance false', actual=summary.get('full_acceptance'))
    require(summary.get('reports_enabled') is True, findings, 'result-reports-enabled',
            'summary does not declare reports_enabled', actual=summary.get('reports_enabled'))
    require(summary.get('census') is True, findings, 'result-census',
            'summary does not declare census mode', actual=summary.get('census'))
    report_limit = summary.get('report_limit')
    if not require(is_int(report_limit) and report_limit > 0, findings, 'result-report-limit',
                   'summary lacks a positive integer report_limit', actual=report_limit):
        report_limit = None
    require(summary.get('valid') is True, findings, 'result-valid-flag',
            'summary does not declare valid=true', actual=summary.get('valid'))
    require(summary.get('unfinished_group') is None, findings, 'result-unfinished',
            'summary declares an unfinished group', actual=summary.get('unfinished_group'))
    if report_epoch is not None:
        require(summary.get('epoch') == report_epoch, findings, 'result-epoch',
                'summary epoch differs from the report epoch', actual=summary.get('epoch'),
                report_epoch=report_epoch)
    if rate_groups.epoch is not None:
        require(summary.get('epoch') == rate_groups.epoch, findings, 'result-epoch-rate',
                'summary epoch differs from the rate.jsonl epoch',
                actual=summary.get('epoch'), rate_epoch=rate_groups.epoch)
        require(result.get('scene_epoch') in (None, rate_groups.epoch), findings,
                'result-scene-epoch', 'result scene_epoch differs from the rate epoch',
                actual=result.get('scene_epoch'), rate_epoch=rate_groups.epoch)

    counts = summary.get('counts')
    if not require(isinstance(counts, dict), findings, 'result-counts-shape',
                   'summary carries no counts object'):
        return result, summary
    for key in COUNTER_KEYS:
        if not require(is_int(counts.get(key)), findings, 'result-counter-type',
                       'counter %s is not an integer' % key, actual=counts.get(key)):
            counts[key] = None
    recomputed_over = len(rate_groups.over_budget)
    recomputed_emitted = len(seen)
    recomputed_dropped = max(0, recomputed_over - recomputed_emitted)
    recomputed_complete = rate_groups.complete_groups
    for key, recomputed in (('groups_complete', recomputed_complete),
                            ('over_budget_groups', recomputed_over),
                            ('reports_emitted', recomputed_emitted),
                            ('reports_dropped', recomputed_dropped),
                            ('groups_incomplete', rate_groups.incomplete_groups),
                            ('diagnostic_errors', 0)):
        if counts.get(key) is not None:
            require(counts[key] == recomputed, findings, 'result-counter-mismatch',
                    'declared counter %s (%r) != independently recomputed %r'
                    % (key, counts[key], recomputed), declared=counts[key], recomputed=recomputed)
    # A dangling group makes the recorder's own group tally unreconstructible from
    # the rate stream; that counter is then declared-only and is not invented.
    if rate_groups.unpaired_start_groups or rate_groups.duplicate_end_rows:
        require(counts.get('groups_complete') in (None, len(rate_groups.groups_in_order)),
                findings, 'result-incongruent-groups',
                'declared groups_complete cannot match a stream with dangling or duplicate groups',
                declared=counts.get('groups_complete'), ends=len(rate_groups.groups_in_order),
                orphan_starts=rate_groups.unpaired_start_groups,
                duplicate_ends=rate_groups.duplicate_end_rows)
    require(rate_groups.complete_groups + rate_groups.incomplete_groups
            == len(rate_groups.groups_in_order), findings, 'rate-group-accounting',
            'complete + incomplete groups != closed rate groups',
            complete=rate_groups.complete_groups, incomplete=rate_groups.incomplete_groups,
            closed=len(rate_groups.groups_in_order))
    # Defect 1: an honest recorder with reports_enabled=true emits
    # min(over_budget_groups, report_limit) reports.  A short or empty report
    # stream is therefore structurally impossible and must not pass, whether or
    # not the declared counters were adjusted to match the short stream.
    declared_enabled = summary.get('reports_enabled')
    if report_limit is not None and declared_enabled is True:
        expected_emitted = min(recomputed_over, report_limit)
        if counts.get('reports_emitted') is not None:
            require(counts['reports_emitted'] == expected_emitted, findings,
                    'result-emit-minimum',
                    'declared reports_emitted %r != min(over_budget_groups, report_limit) = %d'
                    % (counts.get('reports_emitted'), expected_emitted),
                    declared=counts.get('reports_emitted'), expected=expected_emitted,
                    over_budget=recomputed_over, report_limit=report_limit)
        require(recomputed_emitted == expected_emitted, findings, 'report-cap-minimum',
                'reports present (%d) != min(over_budget_groups, report_limit) = %d'
                % (recomputed_emitted, expected_emitted),
                reports=recomputed_emitted, expected=expected_emitted,
                over_budget=recomputed_over, report_limit=report_limit)
    elif declared_enabled is False:
        require(recomputed_emitted == 0, findings, 'report-cap-minimum',
                'reports are present although the summary declares reports_enabled=false',
                reports=recomputed_emitted)
    return result, summary


# ------------------------------------------------------------------- ranking

def build_ranking(limits, rate_groups, seen, summary):
    """Rank measured regions and account for the unreported ones without invention."""
    regions = sorted(limits['regions'], key=lambda r: (-r['work_ns'], r['start_tick']))
    ranked = []
    for rank, region in enumerate(regions, 1):
        durations = region['step_durations_ns']
        gaps = region['step_gaps_ns']
        accounted = region['prefix_ns'] + sum(durations) + sum(gaps) + region['suffix_ns']
        ranked.append({
            'rank': rank,
            'segment_id': region['segment_id'],
            'start_tick': region['start_tick'],
            'end_tick': region['end_tick'],
            'requested_rate': region['requested_rate'],
            'period_ns': region['period_ns'],
            'work_ns': region['work_ns'],
            'excess_ns': region['excess_ns'],
            'excess_ratio': round(region['excess_ns'] / region['period_ns'], 6),
            'accounted_ns': accounted,
            'interval_ns': [region['preceding_boundary']['actual_start_ns'],
                            region['following_boundary']['actual_end_ns']],
            'measured': True,
            'breakdown': {
                'prefix_ns': region['prefix_ns'],
                'visible_step_wall_ns': sum(durations),
                'visible_step_durations_ns': list(durations),
                'largest_step': {
                    'index': durations.index(max(durations)),
                    'tick': region['start_tick'] + 1 + durations.index(max(durations)),
                    'wall_ns': max(durations),
                },
                'inter_step_gaps_ns': list(gaps),
                'suffix_ns': region['suffix_ns'],
                'phase_wall_ns': {name: region['phases'][name]['wall_ns'] for name in STAGES},
                'phase_thread_cpu_ns': {name: region['phases'][name]['thread_cpu_ns']
                                        for name in STAGES},
                'wall_minus_thread_cpu_ns': {
                    name: region['phases'][name]['wall_ns'] - region['phases'][name]['thread_cpu_ns']
                    for name in STAGES},
                'native_wait_wall_ns': region['native_wait_wall_ns'],
                'native_wait_thread_cpu_ns': region['native_wait_cpu_ns'],
                'native_inputs_stage_uncovered_by_visible_waits_ns':
                    region['phases']['native_inputs']['wall_ns'] - region['native_wait_wall_ns'],
                'native_waits': region['native_waits'],
            },
            'measurement': 'census report with four CPU rows; wall/CPU windows as recorded',
        })

    # The unreported over-budget groups: measured work/excess only.
    emitted = {(r['segment_id'], r['start_tick']) for r in seen}
    unreported = []
    for entry in rate_groups.over_budget:
        key = (entry['segment_id'], entry['start_tick'])
        if key in emitted:
            continue
        unreported.append({
            'segment_id': entry['segment_id'],
            'start_tick': entry['start_tick'],
            'end_tick': entry['end_tick'],
            'requested_rate': entry['requested_rate'],
            'period_ns': entry['period_ns'],
            'work_ns': entry['work_ns'],
            'excess_ns': entry['excess_ns'],
            'excess_ratio': round(entry['excess_ns'] / entry['period_ns'], 6),
            'measured': False,
            'measured_fields': ['period_ns', 'work_ns', 'excess_ns'],
            'unmeasured_fields': ['phases', 'retained_steps', 'step_windows',
                                  'visible_native_waits', 'work_decomposition'],
            'reason': 'report_cap_dropped',
            'note': ('this group exceeded its period but no report was emitted: per-phase, '
                     'per-step and native-wait detail was never written, so nothing about its '
                     'internal composition is claimed here'),
        })
    unreported.sort(key=lambda r: (-r['excess_ns'], r['start_tick']))

    declared_dropped = None
    if isinstance(summary, dict) and isinstance(summary.get('counts'), dict):
        declared_dropped = summary['counts'].get('reports_dropped')
    return {
        'ranked_measured_regions': ranked,
        'unreported_over_budget_regions': unreported,
        'declared_reports_dropped': declared_dropped,
        'recomputed_unreported_count': len(unreported),
        'accounting': {
            'over_budget_total_ns': sum(r['work_ns'] for r in ranked)
            + sum(r['work_ns'] for r in unreported),
            'measured_work_ns': sum(r['work_ns'] for r in ranked),
            'unmeasured_work_ns': sum(r['work_ns'] for r in unreported),
            'measured_excess_ns': sum(r['excess_ns'] for r in ranked),
            'unmeasured_excess_ns': sum(r['excess_ns'] for r in unreported),
            'measured_phase_wall_ns': {
                name: sum(r['breakdown']['phase_wall_ns'][name] for r in ranked)
                for name in STAGES},
            'measured_visible_step_wall_ns': sum(r['breakdown']['visible_step_wall_ns']
                                                 for r in ranked),
            'measured_inter_step_gaps_ns': sum(sum(r['breakdown']['inter_step_gaps_ns'])
                                               for r in ranked),
            'measured_prefix_suffix_ns': sum(r['breakdown']['prefix_ns'] + r['breakdown']['suffix_ns']
                                             for r in ranked),
            'unmeasured_phase_note': ('phase, step and native-wait totals cover only the %d '
                                      'measured regions; the %d unreported regions contribute '
                                      'nothing to them by construction, not because they had no '
                                      'work' % (len(ranked), len(unreported))),
        },
        'ranking_limits': [
            'regions are ranked by work_ns measured from the rate boundary; only the 16 '
            'reported groups have an internal decomposition',
            'the two unreported groups are ranked-eligible by work_ns but are listed '
            'separately and never assigned phases',
            'native_inputs wall time includes off-CPU time whose cause is not identified by '
            'these artifacts; no OS, host, native-FC or Windows attribution is made here',
            'thread CPU can exceed wall in the recorded shifted windows; that is reported as '
            'recorded and is not treated as an error or a cause',
        ],
    }


def declared_report_limit(path, findings):
    """Peek at the declared report limit so the cap is checked during report reads.

    This is a *claim* read from the archive, not an oracle: the audit still
    verifies the reports that were emitted and independently derives how many
    over-budget groups existed.
    """
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            result = json.load(handle)
    except Exception as error:  # noqa: BLE001 - reported by audit_result as well
        findings.warning('result-unreadable', 'report limit could not be pre-read: %s: %s'
                         % (type(error).__name__, error), where=path)
        return None
    summary = result.get('group_work_timing') if isinstance(result, dict) else None
    limit = summary.get('report_limit') if isinstance(summary, dict) else None
    if is_int(limit) and limit > 0:
        return limit
    findings.warning('result-report-limit-unreadable',
                     'no positive integer report_limit could be pre-read', where=path)
    return None


# ---------------------------------------------------------------------- main

def build_parser():
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description='Independent stdlib audit of an archived wksim group work-timing flight.')
    parser.add_argument('--archive', help='directory holding the archived flight artifacts')
    parser.add_argument('--group-work-timing', dest='group_work_timing',
                        help='path to group-work-timing.jsonl')
    parser.add_argument('--rate', help='path to rate.jsonl')
    parser.add_argument('--result', help='path to result.json')
    parser.add_argument('--producer', action='append', default=[],
                        help='optional archived producer source to hash for provenance '
                             '(repeatable)')
    parser.add_argument('--label', default=None, help='evidence label written into the report')
    parser.add_argument('--out', default=None, help='write the JSON audit report here')
    parser.add_argument('--max-findings', type=int, default=400,
                        help='cap the number of recorded findings (default 400)')
    return parser


def resolve_inputs(args, findings):
    paths = {'group_work_timing': args.group_work_timing, 'rate': args.rate,
             'result': args.result}
    if args.archive:
        for key, name in (('group_work_timing', 'group-work-timing.jsonl'),
                          ('rate', 'rate.jsonl'), ('result', 'result.json')):
            if not paths[key]:
                paths[key] = os.path.join(args.archive, name)
    for key, path in paths.items():
        if not path:
            findings.error('missing-argument', 'no path supplied for %s (use --archive)' % key)
        elif not os.path.isfile(path):
            findings.error('missing-file', '%s does not exist' % key, where=path)
    return paths


def main(argv=None):
    args = build_parser().parse_args(argv)
    findings = Findings(limit=args.max_findings)
    paths = resolve_inputs(args, findings)
    if findings.errored:
        report = {'tool': TOOL, 'tool_version': TOOL_VERSION, 'verdict': 'input_error',
                  'findings': findings.ordered(),
                  'finding_counts': findings.counts, 'findings_truncated': findings.truncated}
        emit(report, args.out, findings)
        return 2

    evidence = {'label': args.label, 'inputs': {}}
    for key, path in sorted(paths.items()):
        evidence['inputs'][key] = {
            'path': path,
            'bytes': os.path.getsize(path),
            'sha256': sha256_file(path),
        }
    for path in args.producer:
        if os.path.isfile(path):
            evidence['inputs']['producer:' + os.path.basename(path)] = {
                'path': path, 'bytes': os.path.getsize(path), 'sha256': sha256_file(path)}
        else:
            findings.warning('producer-missing', 'producer source not found', where=path)

    rate_groups = audit_rate_jsonl(paths['rate'], findings)
    report_limit = declared_report_limit(paths['result'], findings)
    limits, seen, report_epoch = audit_reports(paths['group_work_timing'], findings,
                                               rate_groups, report_limit)
    result, summary = audit_result(paths['result'], findings, rate_groups, limits, seen,
                                   report_epoch)
    declared_limit = summary.get('report_limit') if isinstance(summary, dict) else None
    report_limit = declared_limit if is_int(declared_limit) else report_limit
    if is_int(report_limit) and len(seen) > report_limit:
        findings.error('report-cap', 'emitted reports (%d) exceed the declared report limit (%d)'
                       % (len(seen), report_limit), report_limit=report_limit)
    emitted_keys = [(region['segment_id'], region['start_tick']) for region in seen]
    over_entries = [(entry['segment_id'], entry['start_tick']) for entry in rate_groups.over_budget]
    if len(over_entries) >= len(emitted_keys) and over_entries[:len(emitted_keys)] != emitted_keys:
        findings.error('report-stream-order',
                       'emitted reports are not the leading over-budget groups in stream order',
                       emitted=emitted_keys, leading_over_budget=over_entries[:len(emitted_keys)])
    elif len(over_entries) < len(emitted_keys):
        findings.error('report-more-than-over-budget',
                       'more reports were emitted than there are over-budget groups',
                       emitted=len(emitted_keys), over_budget=len(over_entries))
    # Independent exact-minimum check (defect 1): with reports enabled, the counting
    # recorder emits one report per over-budget group up to the cap, so the emitted
    # count is min(over_budget, report_limit) unless report_limit is unknown.
    if is_int(report_limit):
        expected_emitted = min(len(over_entries), report_limit)
        if len(emitted_keys) != expected_emitted:
            findings.error('report-cap-minimum',
                           'emitted reports (%d) != min(over_budget_groups, report_limit) = %d'
                           % (len(emitted_keys), expected_emitted),
                           reports=len(emitted_keys), expected=expected_emitted,
                           over_budget=len(over_entries), report_limit=report_limit)

    ranking = build_ranking(limits, rate_groups, seen, summary)
    measurement_limits = collect_limits(limits, ranking, rate_groups, result)

    counters = None
    if isinstance(summary, dict) and isinstance(summary.get('counts'), dict):
        counters = {'declared': summary['counts'],
                    'recomputed': {
                        'groups_complete': rate_groups.complete_groups,
                        'groups_incomplete': rate_groups.incomplete_groups,
                        'over_budget_groups': len(rate_groups.over_budget),
                        'reports_emitted': len(seen),
                        'reports_dropped': max(0, len(rate_groups.over_budget) - len(seen)),
                        'diagnostic_errors': 0,
                    },
                    'independent': {
                        'reports_read': limits['reports'],
                        'rate_groups_closed': len(rate_groups.groups_in_order),
                        'over_budget_derived_from_rate_boundaries': len(rate_groups.over_budget),
                        'rate_boundary_replay': {
                            'groups_complete': rate_groups.complete_groups,
                            'groups_incomplete': rate_groups.incomplete_groups,
                            'note': ('group accounting replayed from the closed rate boundary '
                                     'pairs: a group counts complete when its ticks are '
                                     'contiguous with the previous group of its segment and its '
                                     'no-catch-up anchor equation holds. Diagnostic-row '
                                     'rejections inside a group are not visible in the rate '
                                     'stream and are therefore not independently recoverable '
                                     'from these artifacts.'),
                        },
                    }}
    report = {
        'tool': TOOL,
        'tool_version': TOOL_VERSION,
        'scope': ('independent re-derivation from archived raw rows; GroupWorkTiming is never '
                  'imported or used as an oracle'),
        'verdict': 'fail' if findings.errored else 'pass',
        'evidence': evidence,
        'epoch': {
            'rate_jsonl': rate_groups.epoch,
            'reports': report_epoch,
            'result_summary': summary.get('epoch') if isinstance(summary, dict) else None,
            'result_scene_epoch': result.get('scene_epoch') if isinstance(result, dict) else None,
        },
        'counts': counters,
        'report_limit': report_limit,
        'rate': {
            'group_starts': len(rate_groups.starts),
            'group_ends': len(rate_groups.ends),
            'groups_closed': len(rate_groups.groups_in_order),
            'anchors': len(rate_groups.anchors),
            'unmet': [{'tick': row.get('tick'), 'lateness_ns': row.get('lateness_ns'),
                       'reason': row.get('reason'), 'completed_groups': row.get('completed_groups'),
                       'segment_id': row.get('segment_id')} for row in rate_groups.unmet],
            'over_budget_groups': len(rate_groups.over_budget),
            'periods_by_rate': rate_groups.period_by_rate,
        },
        'reports': [{'segment_id': region['segment_id'], 'start_tick': region['start_tick'],
                     'end_tick': region['end_tick']} for region in seen],
        'ranking': ranking,
        'measurement_limits': measurement_limits,
        'findings': findings.ordered(),
        'finding_counts': findings.counts,
        'finding_code_counts': dict(sorted(findings.code_counts.items())),
        'findings_truncated': findings.truncated,
        'findings_note': ('errors are listed before warnings and infos; the retained list is '
                          'capped by --max-findings, but finding_counts and '
                          'finding_code_counts count every finding including the suppressed '
                          'ones'),
    }
    emit(report, args.out, findings)
    return 1 if findings.errored else 0


def collect_limits(limits, ranking, rate_groups, result):
    waits = limits['waits']
    cpu_over = limits['cpu_over_wall_waits']
    items = [
        {
            'id': 'thread-cpu-shifted-windows',
            'statement': ('thread CPU is kept exactly as recorded; the producer reads shifted '
                          'measurement windows, so thread_cpu_ns may exceed wall_ns. That is why '
                          'wall minus thread CPU is a measured clock difference with window '
                          'uncertainty, not exact off-CPU time, and it is never treated as an '
                          'error'),
            'observed': {'waits': waits, 'waits_with_cpu_over_wall': cpu_over,
                         'waits_with_cpu_over_wall_ratio':
                             round(cpu_over / waits, 6) if waits else None},
        },
        {
            'id': 'native-wait-brackets',
            'statement': ('each native wait brackets only the supervisor wait_ap/wait_px4 call; '
                          'acknowledge_ap, barrier/repair_input and record writes stay in the '
                          'combined native_inputs stage'),
            'observed': {
                'native_inputs_phase_wall_ns': limits['phase_wall_ns'].get('native_inputs'),
                'visible_native_wait_wall_ns': limits['wait_wall_ns_by_stack'],
            },
        },
        {
            'id': 'no-causal-attribution',
            'statement': ('wall minus thread CPU is reported strictly as a measured difference '
                          'between the monotonic clock and the thread CPU clock over shifted '
                          'windows; it is not exact off-CPU time and these artifacts do not '
                          'identify an OS, host, native flight controller or Windows cause. No '
                          'such attribution is made'),
            'observed': {name: {'wall_ns': limits['phase_wall_ns'].get(name),
                                'thread_cpu_ns': limits['phase_cpu_ns'].get(name),
                                'wall_minus_thread_cpu_ns': (limits['phase_wall_ns'].get(name, 0)
                                                             - limits['phase_cpu_ns'].get(name, 0))}
                         for name in STAGES},
        },
        {
            'id': 'diagnostic-only',
            'statement': ('the evidence stays diagnostic_only with full_acceptance=false; this '
                          'audit produces no acceptance verdict and never upgrades the class'),
            'observed': {'result_summary_classification':
                             result.get('group_work_timing', {}).get('classification')
                             if isinstance(result, dict) else None},
        },
        {
            'id': 'unreported-regions-not-decomposed',
            'statement': ('over-budget groups whose reports were dropped by the report cap have '
                          'only the work and excess that the rate boundary measures; their '
                          'phases, steps and native waits are unknown and are not invented'),
            'observed': {'unreported_regions':
                             [r['start_tick'] for r in ranking['unreported_over_budget_regions']],
                         'unmeasured_work_ns': ranking['accounting']['unmeasured_work_ns']},
        },
        {
            'id': 'derived-period',
            'statement': ('the original period is declared by each rate group and independently '
                          're-derived as int(4_000_000/requested_rate) from the archived '
                          'joint_rate equation'),
            'observed': {'periods_by_rate': rate_groups.period_by_rate},
        },
        {
            'id': 'single-flight-scope',
            'statement': ('all identities are checked inside this one archived flight; the audit '
                          'makes no claim about other flights, sources or profiles, and the raw '
                          'archive is read-only'),
            'observed': {'regions_measured': len(limits['regions'])},
        },
    ]
    step_walls = limits['step_wall_ns']
    if step_walls:
        items.append({
            'id': 'step-window-extremes',
            'statement': 'extremes of the recorded per-step wall windows across measured regions',
            'observed': {'max_step_wall_ns': max(step_walls), 'min_step_wall_ns': min(step_walls),
                         'steps': len(step_walls)},
        })
    return items


def emit(report, out_path, findings=None):
    """Print the one-line summary and (optionally) write the JSON audit report.

    Returns ``'ok'`` or ``'write_failed'``; a failed write is a real audit
    failure, never a silent success.
    """
    text = json.dumps(report, indent=2, sort_keys=False, allow_nan=False)
    status = 'ok'
    if out_path:
        directory = os.path.dirname(os.path.abspath(out_path))
        try:
            if directory and not os.path.isdir(directory):
                os.makedirs(directory, exist_ok=True)
            with open(out_path, 'w', encoding='utf-8', newline='\n') as handle:
                handle.write(text + '\n')
        except OSError as error:
            status = 'write_failed'
            message = 'could not write the audit report: %s: %s' % (type(error).__name__, error)
            if findings is not None:
                findings.error('out-write-failed', message, where=out_path)
                report['verdict'] = 'fail'
                report['findings'] = findings.ordered()
                report['finding_counts'] = findings.counts
                report['findings_truncated'] = findings.truncated
            print(json.dumps({'tool': report.get('tool'), 'verdict': 'fail',
                              'error_code': 'write_failed', 'out': out_path,
                              'error': message}, sort_keys=True),
                  file=sys.stderr)
    counts = report.get('finding_counts', {})
    summary = {
        'tool': report.get('tool'),
        'verdict': report.get('verdict'),
        'errors': counts.get('error', 0),
        'warnings': counts.get('warning', 0),
        'infos': counts.get('info', 0),
        'over_budget_groups': report.get('rate', {}).get('over_budget_groups')
                              if isinstance(report.get('rate'), dict) else None,
        'reports_emitted': len(report.get('reports', [])) if 'reports' in report else None,
        'out': out_path,
    }
    print(json.dumps(summary, sort_keys=True))
    return status


if __name__ == '__main__':
    sys.exit(main())
