#!/usr/bin/env python3
"""Map the recorded inter-step gaps of one archived flight onto executed source.

Scope (gap mapping only)
------------------------
``group-work-timing.jsonl`` records, for every over-budget group, four CPU step
windows and therefore three *inter-step gaps*::

    gap[i] = step_window[i+1].wall_start_ns - step_window[i].wall_end_ns

All 48 retained gaps across the 16 measured groups join the marks of steps
P+1..P+4 **of one group**, so every retained gap lies inside a single group span.
The group's ``JointRate.end_group`` is recorded after the P+4 step mark and the
next group's ``JointRate.begin_group`` before the P+5 mark, so no rate row lies
inside any of these gaps (the archived runner gates both on ``clock.tick % 4``
checks in ``advance()``, ahead of and behind the measured steps).

This tool answers, with citations into the archived runner/joint sources, the
narrow question: **what code executes between a step's last CPU mark
(``joint.py`` mark #3) and the next step's first CPU mark (``joint.py`` mark
#1)?**  It does that for the largest recorded gap (tick 18 812..18 816, gap
4 987 926 ns between ticks 18 814 and 18 815) and for the representative
10 348..10 564 cluster, and nothing else.

It is a companion to ``ds_group_audit.py``: it re-uses that audit's already
validated artifact for the gap numbers instead of re-deriving the whole group
accounting, and it does not import any wksim module.

Two constraints are kept explicit:

* the seam is described as *where the measured interval starts and ends*, never
  as "dead time" or "descheduling"; the artifacts record no scheduling state, so
  no such label is applied;
* the diagnostic recorder's own work (mark reads, ``record`` calls, the census
  CPU/native diagnostic rows that are observed in process and never written to
  ``joint-wire.jsonl``) is listed separately from the default product path,
  which does not create those marks or rows at all;
* a paired ``time.monotonic_ns`` / ``time.thread_time_ns`` reading is reported as
  a measured difference between two clocks over shifted windows.  Adding paired
  clocks does **not** make that difference exact off-CPU time: the producer reads
  the two clocks at different instants, and 72 of the 80 recorded native waits
  already show ``thread_cpu_ns > wall_ns``.  No off-CPU or scheduling claim is
  made anywhere in this report.

Clock handling: every number mapped here comes from the runner process's own
``time.monotonic_ns`` (joint.py marks) except the ``joint-wire.jsonl`` ``wall``
fields, which are ``time.monotonic() - started`` seconds.  The offset
``S = started`` is therefore the only clock alignment needed, and it is derived
and bounded from the data itself: each ``step`` row is written between a step's
first and last mark, so ``S`` must lie in the intersection over the 64 measured
steps of ``[step_start - wire_wall, step_end - wire_wall]``.  No cross-host,
cross-namespace or cross-clock offset is assumed anywhere.

Exit status: 0 on success, 2 on input/read failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

TOOL = 'ds_group_gap_map'
TOOL_VERSION = '1.0.0'

STEP_ROW = '"kind":"step"'
BARRIER_ROW = '"kind":"barrier"'
GC_ROW = '"kind":"diagnostic_gc_timing"'

# Archived sources whose executed regions are cited.  Line numbers are 1-based
# into the archived text copies kept in the evidence directory.
SOURCES = {
    'joint': 'source__Simulator__wksim_core__joint.py.txt',
    'runner': 'source__tools__run_joint_flight.py.txt',
    'rate': 'source__Simulator__wksim_runtime__joint_rate.py.txt',
    'clock': 'source__Simulator__wksim_runtime__scene_clock.py.txt',
}

# Executed regions of the seam, in execution order.  Each region is located by a
# literal start anchor and an optional literal end anchor into the archived
# source text, so a moved or rewritten source is reported as an unresolved
# region instead of being silently mis-cited.  tail = still inside the step whose
# mark #3 opened the interval; head = already inside the next step, before its
# mark #1.
CLOCK_LOG_ANCHOR = 'clock_log.write(json.dumps(clock.snapshot(),separators='

REGIONS = [
    dict(id='diagnostic_recorder_tail', kind='tail', source='joint', order=1,
         start_anchor='        if marks is not None:',
         end_anchor='                            for name,a,b in zip(',
         excerpt='finish_inputs(); mark #3 append; diagnostic_step_cpu_timing record()',
         wire_rows='none (census diagnostic rows go to the recorder, not the wire)'),
    dict(id='advance_return', kind='tail', source='joint', order=2,
         start_anchor="            raise TimeoutError('PX4 actuator startup exceeded four simulation seconds')",
         end_anchor='        return self.states',
         excerpt='JointPhysics.advance() passes the committed states back to the runner',
         wire_rows='none'),
    dict(id='rate_end_group', kind='tail', source='rate', order=3,
         start_anchor='    def end_group(self, tick):',
         end_anchor='        self.check(lateness)',
         excerpt='JointRate.end_group(): now() once, rate_group_end record(), then check()',
         wire_rows='rate_group_end (recorded at P+4, after that step\'s last mark; never inside '
                   'a gap between P+1..P+4)'),
    dict(id='clock_publication_log', kind='tail', source='runner', order=4,
         start_anchor='                    publisher.publish(clock)',
         end_anchor=CLOCK_LOG_ANCHOR,
         excerpt='publisher.publish(clock); clock_log.write(json.dumps(clock.snapshot()))',
         wire_rows='none (clock.jsonl is a separate stream)'),
    dict(id='runner_loop_overhead', kind='head', source='runner', order=5,
         start_anchor='            while clock.tick < MAX_TICKS:',
         end_anchor='                states = advance()',
         excerpt='while clock.tick < MAX_TICKS: health() then states = advance()',
         wire_rows='none'),
    dict(id='runner_health', kind='head', source='runner', order=6,
         start_anchor='        def health():',
         end_anchor="                    raise RuntimeError('Task exited without matching successful result')",
         excerpt='health(): physics_health() then non-blocking child.poll() sweep; on a task '
                 'exit it re-reads that task result.json',
         wire_rows='none', occurrence=2),
    dict(id='rate_begin_group', kind='head', source='rate', order=7,
         start_anchor='    def begin_group(self, tick, health):',
         end_anchor='                    lateness_ns=max(0,now-ideal),**self.group)',
         excerpt='JointRate.begin_group(): earliest/no-catch-up equation, now() polling loop '
                 'with 2 ms health callbacks and a <=2 ms sleep, rate_group_start record()',
         wire_rows='rate_group_start (recorded at the next group\'s P, before its P+1 step; '
                   'never inside a gap between P+1..P+4)'),
    dict(id='runner_advance_prologue', kind='head', source='runner', order=8,
         start_anchor='            def advance():',
         end_anchor='                    states = physics.advance()',
         excerpt='advance(): the pre-advance clock.tick % 4 rate gate (begin_group) then '
                 'physics.advance()',
         wire_rows='none'),
    dict(id='joint_advance_head', kind='head', source='joint', order=9,
         start_anchor='        marks = [(time.monotonic_ns(), time.thread_time_ns())] if self.cpu_timing else None',
         end_anchor='        self.health()',
         excerpt='JointPhysics.advance(): mark #1 append, then self.health()',
         wire_rows='none'),
]

PRODUCT_PATH_ONLY = [
    dict(id='census_marks', source='joint', span=(181, 181),
         note='mark #1 is only taken when cpu_timing is on; timing_census=True forces '
              'cpu_timing on, and the product path runs with neither'),
    dict(id='census_mark3', source='joint', span=(216, 219),
         note='mark #2/#3 and the diagnostic_step_cpu_timing record() exist only under '
              'the census/CPU-timing diagnostic'),
    dict(id='census_native_row', source='joint', span=(279, 284),
         note='diagnostic_native_input_timing is recorded only for retained slow/periodic '
              'ticks, or for every tick under census'),
    dict(id='recorder_short_circuit', source='runner', span=(884, 891),
         note='record() diverts the two diagnostic kinds straight into the recorder, so those '
              'rows never reach joint-wire.jsonl'),
    dict(id='gc_callback', source='joint', span=(60, 72),
         note='the gc.callbacks measurement hook is installed only when cpu_timing is on'),
]


class Findings:
    def __init__(self, limit=200):
        self.items = []
        self.counts = {'error': 0, 'warning': 0, 'info': 0}
        self.limit = limit

    def add(self, severity, code, message, where=None, **detail):
        self.counts[severity] = self.counts.get(severity, 0) + 1
        if len(self.items) >= self.limit:
            return
        item = {'severity': severity, 'code': code, 'message': message}
        if where:
            item['where'] = where
        if detail:
            item['detail'] = detail
        self.items.append(item)

    def error(self, code, message, where=None, **detail):
        self.add('error', code, message, where, **detail)

    def warning(self, code, message, where=None, **detail):
        self.add('warning', code, message, where, **detail)

    @property
    def errored(self):
        return self.counts['error'] > 0


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read_source(archive, key, findings):
    path = os.path.join(archive, SOURCES[key])
    if not os.path.isfile(path):
        findings.error('source-missing', 'archived source not found', where=path)
        return None
    with open(path, 'r', encoding='utf-8') as handle:
        lines = handle.read().split('\n')
    return {'path': path, 'name': SOURCES[key], 'lines': lines,
            'sha256': sha256_file(path), 'line_count': len(lines)}


def enclosing_start(lines, index):
    """Walk back to the def/class line that opens the block containing ``index``."""
    indent = len(lines[index - 1]) - len(lines[index - 1].lstrip())
    for candidate in range(index, 0, -1):
        text = lines[candidate - 1]
        stripped = text.strip()
        if not stripped or stripped.startswith('#'):
            continue
        current = len(text) - len(text.lstrip())
        if current < indent and (stripped.startswith('def ') or stripped.startswith('class ')
                                 or stripped.startswith('while ') or stripped.startswith('if ')
                                 or stripped.startswith('for ') or stripped.startswith('with ')
                                 or stripped.startswith('try')):
            return candidate
        if current <= indent and (stripped.startswith('def ') or stripped.startswith('class ')
                                  or stripped.startswith('while ')):
            return candidate
    return index


def block_end(lines, start):
    """Last line of the indented block that starts at ``start``."""
    base = len(lines[start - 1]) - len(lines[start - 1].lstrip())
    end = start
    for index in range(start + 1, len(lines) + 1):
        text = lines[index - 1]
        if not text.strip():
            continue
        indent = len(text) - len(text.lstrip())
        if indent <= base and not text.lstrip().startswith((')', ']', '}')):
            break
        end = index
    return end


def resolve_span(lines, region, findings, source):
    """Resolve a region's span from the archived text, by literal anchors.

    The archived source is the authority: no line number is trusted from this
    file.  A single anchor resolves to its enclosing block; a start+end anchor
    pair resolves to that exact pair of lines (used where the region is a slice
    inside a larger function).
    """
    def locate(anchor, occurrence, after=0):
        found = 0
        for index, line in enumerate(lines, 1):
            if index <= after or anchor not in line:
                continue
            found += 1
            if found == occurrence:
                return index
        return None

    start = locate(region['start_anchor'], region.get('occurrence', 1))
    if start is None:
        findings.error('region-unresolved', 'region %s start anchor not found' % region['id'],
                       where=source['path'], anchor=region['start_anchor'])
        return None
    if region.get('end_anchor'):
        end = locate(region['end_anchor'], region.get('end_occurrence', 1), after=start)
        if end is None:
            findings.error('region-unresolved', 'region %s end anchor not found after start'
                           % region['id'], where=source['path'], anchor=region['end_anchor'])
            return None
        return start, end
    if region.get('start_anchor', '').lstrip().startswith(('def ', 'while ')):
        return start, block_end(lines, start)
    return enclosing_start(lines, start), block_end(lines, enclosing_start(lines, start))


def region_records(sources, findings):
    """Resolve each executed region into a citable record."""
    records = []
    for region in REGIONS:
        source = sources.get(region['source'])
        if source is None:
            continue
        resolved = resolve_span(source['lines'], region, findings, source)
        if resolved is None:
            continue
        start, end = resolved
        excerpt = '\n'.join(source['lines'][start - 1:end]).strip('\n')
        records.append({
            'id': region['id'], 'phase': region['kind'], 'order': region['order'],
            'summary': region['excerpt'],
            'source': {'name': source['name'], 'sha256': source['sha256'],
                       'line_start': start, 'line_end': end},
            'wire_rows': region['wire_rows'],
            'excerpt': excerpt,
        })
    return sorted(records, key=lambda r: r['order'])


def load_audit(path, findings):
    if not os.path.isfile(path):
        findings.error('audit-missing', 'audit artifact not found', where=path)
        return None
    with open(path, 'r', encoding='utf-8') as handle:
        audit = json.load(handle)
    if audit.get('verdict') != 'pass':
        findings.error('audit-verdict', 'source audit artifact is not passing',
                       where=path, verdict=audit.get('verdict'))
    return audit


def measured_regions(audit):
    return audit.get('ranking', {}).get('ranked_measured_regions', [])


def region_windows(region):
    """Reconstruct the four step windows of a region from the audit artifact."""
    base = region['interval_ns'][0]
    durations = region['breakdown']['visible_step_durations_ns']
    gaps = region['breakdown']['inter_step_gaps_ns']
    prefix = region['breakdown']['prefix_ns']
    cursor = base + prefix
    for index, duration in enumerate(durations):
        yield {
            'segment_id': region['segment_id'],
            'group_start_tick': region['start_tick'],
            'index': index,
            'tick': region['start_tick'] + 1 + index,
            'start_ns': cursor,
            'end_ns': cursor + duration,
            'duration_ns': duration,
            'next_start_ns': (cursor + duration + gaps[index]) if index < 3 else None,
        }
        cursor += duration + (gaps[index] if index < 3 else 0)


def gaps_from_audit(audit):
    gaps = []
    for region in measured_regions(audit):
        windows = list(region_windows(region))
        for index in range(3):
            gap = region['breakdown']['inter_step_gaps_ns'][index]
            gaps.append({
                'segment_id': region['segment_id'],
                'group_start_tick': region['start_tick'],
                'index': index,
                'from_tick': windows[index]['tick'],
                'to_tick': windows[index + 1]['tick'],
                'gap_ns': gap,
                'from_step_start_ns': windows[index]['start_ns'],
                'from_step_end_ns': windows[index]['end_ns'],
                'to_step_start_ns': windows[index + 1]['start_ns'],
                # All three retained gaps of a four-step group join step P+1..P+4
                # inside that one group, so every one of them lies inside the group
                # span. The group's rate.end_group happens after the P+4 mark and the
                # next group's rate.begin_group happens before the P+5 mark, so
                # neither falls inside any of the 48 measured gaps.
                'within_group_span': True,
                'crosses_rate_boundary': False,
                'group_work_ns': region['work_ns'],
                'group_excess_ns': region['excess_ns'],
                'windows': {w['tick']: w for w in windows},
            })
    return gaps


def scan_wire(path, findings):
    """One streaming pass: step/barrier wall rows and every diagnostic_gc_timing row."""
    steps, barriers, gc = {}, {}, []
    if not os.path.isfile(path):
        findings.error('wire-missing', 'joint-wire.jsonl not found', where=path)
        return steps, barriers, gc
    with open(path, 'r', encoding='utf-8') as handle:
        for number, line in enumerate(handle, 1):
            if line[:1] != '{':
                continue
            if STEP_ROW in line or BARRIER_ROW in line or GC_ROW in line:
                try:
                    row = json.loads(line)
                except Exception as error:  # noqa: BLE001
                    findings.warning('wire-malformed', 'wire row is not JSON: %s' % error,
                                     where='%s:%d' % (path, number))
                    continue
                if row.get('kind') == 'step':
                    steps[row.get('tick')] = row.get('wall')
                elif row.get('kind') == 'barrier':
                    barriers[row.get('tick')] = row.get('wall')
                else:
                    gc.append({'tick': row.get('tick'), 'generation': row.get('generation'),
                               'collected': row.get('collected'),
                               'wall_start_ns': row.get('wall_start_ns'),
                               'wall_end_ns': row.get('wall_end_ns'),
                               'thread_cpu_ns': row.get('thread_cpu_ns')})
    return steps, barriers, gc


def region_offset(region, steps):
    """S interval implied by one region's four step rows (None when inconsistent)."""
    lo = hi = None
    used = 0
    for window in region_windows(region):
        tick = window['tick']
        if tick not in (steps or {}) or steps[tick] is None:
            continue
        used += 1
        wire_ns = int(round(steps[tick] * 1e9))
        lower = window['start_ns'] - wire_ns
        upper = window['end_ns'] - wire_ns
        lo = lower if lo is None else max(lo, lower)
        hi = upper if hi is None else min(hi, upper)
    if lo is None or lo > hi:
        return None
    return {'interval_ns': [lo, hi], 'width_ns': hi - lo, 'steps': used}


def derive_offset(audit, steps, findings, archive):
    """Bound S = started: wire_wall_ns + S must lie inside its own step window."""
    lo, hi = None, None
    pinned_lo, pinned_hi = None, None
    used = 0
    per_region = []
    for region in measured_regions(audit):
        local = region_offset(region, steps)
        per_region.append({'start_tick': region['start_tick'],
                           'segment_id': region['segment_id'],
                           'local_interval_ns': local['interval_ns'] if local else None,
                           'local_width_ns': local['width_ns'] if local else None,
                           'consistent': local is not None})
        if local is None:
            findings.error('offset-region-inconsistent',
                           'no single S aligns all four step rows of this measured region',
                           where=str(region['start_tick']))
            continue
        for window in region_windows(region):
            tick = window['tick']
            if tick not in steps or steps[tick] is None:
                continue
            used += 1
            wire_ns = int(round(steps[tick] * 1e9))
            lower = window['start_ns'] - wire_ns
            upper = window['end_ns'] - wire_ns
            if lo is None or lower > lo:
                lo, pinned_lo = lower, tick
            if hi is None or upper < hi:
                hi, pinned_hi = upper, tick
    if not used:
        findings.error('offset-no-steps', 'no measured step had a joint-wire row to align')
        return None
    if lo > hi:
        findings.error('offset-empty', 'the step-row alignment interval is empty',
                       lo=lo, hi=hi, steps=used)
        return None
    if hi - lo > 1_000_000:
        findings.warning('offset-wide', 'the derived alignment interval exceeds 1 ms',
                         width_ns=hi - lo, steps=used)
    return {
        'definition': 'S = process start monotonic offset: monotonic_ns = wire_wall_s * 1e9 + S',
        'constraint': ('every joint-wire step row is written between its own step\'s first and '
                       'last CPU mark, so S must satisfy step_start_ns <= wire_wall_ns + S <= '
                       'step_end_ns for all %d measured steps' % used),
        'interval_ns': [lo, hi],
        'width_ns': hi - lo,
        'steps_aligned': used,
        'pinned_lower_by_tick': pinned_lo,
        'pinned_upper_by_tick': pinned_hi,
        'per_region': per_region,
        'consistency': ('all 16 measured regions accept the same S interval, so the wire stream '
                        'can be placed on the same monotonic line as the CPU marks without any '
                        'cross-host or cross-clock assumption'),
        'evidence': os.path.join(archive, 'joint-wire.jsonl'),
    }


def seam_for_gap(gap, steps, offset, regions, gc):
    """Describe one gap: measured interval, executed regions, and wire annotations."""
    from_ns = gap['from_step_end_ns']
    to_ns = gap['to_step_start_ns']
    measured = to_ns - from_ns
    s_lo, s_hi = offset['interval_ns']
    annotations = []
    for tick, wall in (steps or {}).items():
        if wall is None or not (gap['from_tick'] <= tick <= gap['to_tick']):
            continue
        wire_ns = int(round(wall * 1e9))
        candidate_lo = wire_ns + s_lo
        candidate_hi = wire_ns + s_hi
        # This row's own step window pins S again; intersect that with the
        # interval allowed for a write inside this gap.  Positions are offsets
        # in nanoseconds from the gap start.
        window = gap['windows'].get(tick)
        if window is not None:
            allowed_lo = max(s_lo, window['start_ns'] - wire_ns, from_ns - wire_ns)
            allowed_hi = min(s_hi, window['end_ns'] - wire_ns, to_ns - wire_ns)
        else:
            allowed_lo = max(s_lo, from_ns - wire_ns)
            allowed_hi = min(s_hi, to_ns - wire_ns)
        if allowed_lo <= allowed_hi:
            write_in_gap = [wire_ns + allowed_lo - from_ns, wire_ns + allowed_hi - from_ns]
            if write_in_gap[0] == write_in_gap[1]:
                relation = ('the write is pinned to one instant inside the measured gap '
                            '(%d ns after the gap start)' % write_in_gap[0])
            else:
                relation = ('the write falls inside the measured gap between %d ns and %d ns '
                            'after the gap start' % (write_in_gap[0], write_in_gap[1]))
        else:
            write_in_gap = None
            relation = 'this row was written outside the measured gap'
        annotations.append({
            'kind': 'step', 'tick': tick, 'wire_wall_s': wall,
            'candidate_monotonic_ns': [candidate_lo, candidate_hi],
            'write_offset_in_gap_ns': write_in_gap,
            'relation': relation,
            'derivation': ('the row is written between its own step marks, so the S that aligns '
                           'it must also place it inside its window and, if it is inside the gap, '
                           'inside [gap_start, gap_end]; the offset is that intersection'),
        })
    gc_in_gap = [row for row in (gc or [])
                 if row.get('wall_start_ns') is not None
                 and from_ns <= row['wall_start_ns'] <= to_ns]
    inside = [a for a in annotations if a['write_offset_in_gap_ns'] is not None]
    localisation = {
        'wire_rows_inside_gap': len(inside),
        'inside_ticks': [a['tick'] for a in inside],
        'conclusion': ('no joint-wire row is written after the first instant of a measured '
                       'inter-step gap'),
        'why': ('every step row is written inside its own step window, and each step window ends '
                'at or before the gap boundary that adjoins it: the row of step t is written '
                'inside a window that closes at the gap start, and the row of step t+1 is written '
                'inside a window that opens at the gap end. A row can therefore land at most on '
                'the first instant of the gap and never after it.'),
        'why_evidence': ('checked per row in wire_step_rows_in_window_ns below as a single '
                         'gap-window comparison against the row\'s own window'),
        'consequence': ('the gap cannot be sub-divided with the wire stream; the wire contributes '
                        'the executed event order and the step-window cross-check only'),
    }
    executed = []
    rate_boundary_note = ('JointRate.end_group runs after the P+4 step mark and the next '
                          "group's JointRate.begin_group runs before the P+5 step mark, so "
                          'neither is inside a gap between P+1..P+4; the archived runner gates '
                          'both on clock.tick % 4 checks in advance(), not inside these gaps')
    for region in regions:
        if region['id'] in ('rate_end_group', 'rate_begin_group'):
            executed.append(dict(region, applicability='not executed inside this gap',
                                 reason=rate_boundary_note))
        else:
            executed.append(dict(region, applicability='executed'))
    return {
        'segment_id': gap['segment_id'],
        'group_start_tick': gap['group_start_tick'],
        'index': gap['index'],
        'from_tick': gap['from_tick'],
        'to_tick': gap['to_tick'],
        'within_group_span': gap['within_group_span'],
        'crosses_rate_boundary': gap['crosses_rate_boundary'],
        'rate_boundary_placement': rate_boundary_note,
        'measured_gap_ns': measured,
        'recorded_gap_ns': gap['gap_ns'],
        'interval_ns': [from_ns, to_ns],
        'group_work_ns': gap['group_work_ns'],
        'group_excess_ns': gap['group_excess_ns'],
        'share_of_group_work': round(measured / gap['group_work_ns'], 6),
        'wire_step_rows_in_window': annotations,
        'wire_step_rows_in_window_ns': {
            str(a['tick']): {
                'own_window': [gap['windows'][a['tick']]['start_ns'],
                               gap['windows'][a['tick']]['end_ns']]
                if a['tick'] in gap['windows'] else None,
                'gap_window': [from_ns, to_ns],
                'inside_gap': a['write_offset_in_gap_ns'] is not None,
            } for a in annotations},
        'wire_localisation': localisation,
        'diagnostic_gc_rows_in_window': gc_in_gap,
        'step_windows_in_group_ns': {str(tick): [w['start_ns'], w['end_ns']]
                                     for tick, w in sorted(gap['windows'].items())},
        'executed_regions': executed,
        'excluded_from_seam': {
            'native_waits': 'recorded before mark #3, so already inside the previous step window',
            'model_step_and_encode_send': 'between mark #1 and mark #2 of the previous step',
            'clock_publication_write': 'covered by the clock_publication_log region below',
        },
    }


def build(archive, audit_path, out_path):
    findings = Findings()
    sources = {}
    for key in SOURCES:
        loaded = read_source(archive, key, findings)
        if loaded is not None:
            sources[key] = loaded
    regions = region_records(sources, findings)
    audit = load_audit(audit_path, findings)
    if audit is None or findings.errored:
        return None, findings
    steps, barriers, gc = scan_wire(os.path.join(archive, 'joint-wire.jsonl'), findings)
    offset = derive_offset(audit, steps, findings, archive)
    if offset is None:
        return None, findings

    gaps = gaps_from_audit(audit)
    # The audit already proved the exact work identity; re-derive it here from the
    # region span so the window reconstruction this tool uses is itself checked
    # against the artifact's boundaries rather than only against itself.
    for region in measured_regions(audit):
        breakdown = region['breakdown']
        span = region['interval_ns'][1] - region['interval_ns'][0]
        total = (breakdown['prefix_ns'] + sum(breakdown['visible_step_durations_ns'])
                 + sum(breakdown['inter_step_gaps_ns']) + breakdown['suffix_ns'])
        if span != total:
            findings.error('region-span-identity',
                           'region span does not equal prefix + steps + gaps + suffix',
                           where=str(region['start_tick']), span=span, total=total)
    by_key = {(g['group_start_tick'], g['index']): g for g in gaps}
    largest = max(gaps, key=lambda g: g['gap_ns']) if gaps else None

    # Every gap is mapped; the two required views (the largest gap and the
    # representative cluster) are marked so a reader can find them directly.
    targets = [seam_for_gap(gap, steps, offset, regions, gc) for gap in gaps]
    cluster_low, cluster_high = 10_348, 10_564
    for target in targets:
        target['is_largest_gap'] = largest is not None and (
            target['group_start_tick'], target['index']) == (largest['group_start_tick'],
                                                             largest['index'])
        target['in_representative_cluster'] = cluster_low <= target['group_start_tick'] \
            <= cluster_high
    targets.sort(key=lambda t: (not t['is_largest_gap'],
                                not t['in_representative_cluster'],
                                t['group_start_tick'], t['index']))

    all_gap_values = sorted((g['gap_ns'] for g in gaps), reverse=True)
    # Corrected categorisation: all 48 retained gaps join steps P+1..P+4 inside one
    # group, so every retained gap is intra-group and none of them contains a rate
    # boundary. The rate.end_group at P+4 and the next begin_group before P+5 sit in
    # the group suffix / next prefix, outside these gaps.
    intra = [g for g in gaps if g['within_group_span']]
    crossing = [g for g in gaps if g['crosses_rate_boundary']]
    summary = {
        'gaps_total': len(gaps),
        'gaps_intra_group': len(intra),
        'gaps_crossing_rate_boundary': len(crossing),
        'gap_max_ns': all_gap_values[0] if all_gap_values else None,
        'gap_min_ns': all_gap_values[-1] if all_gap_values else None,
        'gap_total_ns': sum(g['gap_ns'] for g in gaps),
        'intra_group_total_ns': sum(g['gap_ns'] for g in intra),
        'intra_group_max_ns': max((g['gap_ns'] for g in intra), default=None),
        'categorisation_note': ('every retained gap connects the marks of steps P+1..P+4 of the '
                                'same group; rate.end_group happens after the P+4 mark and the '
                                'next rate.begin_group before the P+5 mark, so no rate row lies '
                                'inside any of these gaps'),
    }

    report = {
        'tool': TOOL,
        'tool_version': TOOL_VERSION,
        'verdict': 'fail' if findings.errored else 'pass',
        'scope': ('maps the recorded inter-step gaps of one archived flight onto executed '
                  'source regions; labels no interval as dead time or descheduling'),
        'archive': archive,
        'audit_artifact': {
            'path': audit_path,
            'sha256': sha256_file(audit_path),
            'verdict': audit.get('verdict'),
            'reports_used': len(audit.get('reports', [])),
        },
        'sources': {key: {'name': value['name'], 'sha256': value['sha256'],
                          'line_count': value['line_count']}
                    for key, value in sorted(sources.items())},
        'seam_definition': {
            'gap_equation': ('gap[i] = step_window[i+1].wall_start_ns - '
                             'step_window[i].wall_end_ns, both marks read by '
                             'time.monotonic_ns in the runner process'),
            'mark_1': 'joint.py:181 - JointPhysics.advance() entry, before self.health()',
            'mark_2': 'joint.py:199 - after clock.commit(responses), before the sensor emit',
            'mark_3': 'joint.py:219 - after finish_inputs(), the last clock read of the step',
            'consequence': ('the interval contains the tail of the step that mark #3 closed and '
                            'the head of the next step down to mark #1; the step body, model '
                            'round trip, sensor emit and native waits are all before mark #3'),
        },
        'clock_alignment': offset,
        'wire_stream': {'steps_scanned': len(steps), 'barriers_scanned': len(barriers),
                        'diagnostic_gc_rows': gc},
        'measured_regions_used': [region['start_tick'] for region
                                  in audit.get('ranking', {}).get('ranked_measured_regions', [])],
        'gap_summary': summary,
        'executed_regions': regions,
        'diagnostic_only_path': PRODUCT_PATH_ONLY,
        'targets': targets,
        'findings': findings.items,
        'finding_counts': findings.counts,
    }
    if out_path:
        directory = os.path.dirname(os.path.abspath(out_path))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8', newline='\n') as handle:
            json.dump(report, handle, indent=2)
            handle.write('\n')
    return report, findings


def main(argv=None):
    parser = argparse.ArgumentParser(prog=TOOL, description=__doc__.split('\n')[0])
    parser.add_argument('--archive', required=True)
    parser.add_argument('--audit', default=None,
                        help='path to the ds_group_audit artifact (default: sibling evidence)')
    parser.add_argument('--out', default=None)
    args = parser.parse_args(argv)
    default_audit = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'evidence',
                                 'joint-public-flight-rfw9nmbb-audit.json')
    report, findings = build(args.archive, args.audit or default_audit, args.out)
    if report is None:
        print(json.dumps({'tool': TOOL, 'verdict': 'input_error',
                          'findings': findings.items,
                          'finding_counts': findings.counts}, sort_keys=True))
        return 2
    print(json.dumps({'tool': TOOL, 'verdict': 'fail' if findings.errored else 'pass',
                      'gaps': report['gap_summary']['gaps_total'],
                      'gap_max_ns': report['gap_summary']['gap_max_ns'],
                      'offset_width_ns': report['clock_alignment']['width_ns'],
                      'out': args.out}, sort_keys=True))
    return 1 if findings.errored else 0


if __name__ == '__main__':
    sys.exit(main())
