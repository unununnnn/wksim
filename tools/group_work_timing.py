"""Bounded group work-timing recorder (diagnostic-only; never wired by default).

Consumes existing wire rows - rate group events (rate_group_start /
rate_group_end), the per-tick step events, and the retained
diagnostic_step_cpu_timing / diagnostic_native_input_timing samples. The frozen
producer (Simulator/wksim_core/joint.py:211-219, 248-283) emits per tick in the
order step -> diagnostic_native_input_timing -> diagnostic_step_cpu_timing and
retains the diagnostics only when a step exceeds 2ms or on tick % 250 == 0
(sampled mode), so phase/wait coverage is partial unless a census producer
(timing_census=True, a future private producer) supplies all four CPU rows.
Nothing here changes joint.py, the runner, or joint_rate.py, and no native code
runs.

A group starts at tick P and is complete with its four steps P+1..P+4. Normal
groups are counted in memory only: nothing is emitted or written. When a real
rate_group_end shows work = actual_end_ns - actual_start_ns above the original
period (8ms at rate 0.5, 4ms at rate 1.0), the recorder hands ONE report to the
injected emit callback. At most REPORT_LIMIT (16) reports; further over-budget
groups are counted as dropped. report_limit may only be lowered, never raised
past 16.

Per tick at most one CPU row and one native row are retained, in the producer
order; duplicates or out-of-order diagnostic rows are rejected and taint the
group (counted incomplete). CPU windows must lie inside the real group span
[actual_start_ns, actual_end_ns], be non-overlapping in tick order, and native
wait windows must lie inside the same tick's native_inputs stage (stage bounds
from cumulative stage wall_ns). In census mode every group needs all four CPU
rows; only then does the report carry the exact work decomposition
prefix + 4 step durations + 3 gaps + suffix = work with the original windows
preserved. In sampled mode the report honestly marks its coverage and unverified
wait stages instead.

Thread CPU is kept as recorded; no OS cause is attributed from wall-CPU, and CPU
is never required to be <= wall (the producer reads shifted measurement windows).
A zero-length wait (wall_end == wall_start) is accepted: a real clock can read
the same value twice. Business events, thresholds, inputs and clocks are never
modified and there is no early fallback. Data errors (bad rows, incomplete
groups) make summary()['valid'] False with reasons recorded; an unclosed group
is marked unfinished in summary() and finalized as incomplete by finish(). A
recorder fault invalidates this diagnostic only and never propagates; the emit
callback belongs to the caller, so its own exceptions propagate unchanged.
summary() is the intended value of the future 'group_work_timing' result field;
the formal validator already rejects that field, so enabling it keeps the
evidence diagnostic-only (classification='diagnostic_only',
full_acceptance=False).
"""

SCHEMA = 'wksim.group-work-timing.v2'
REPORT_LIMIT = 16
MAX_REASONS = 8
RATES = (0.5, 1.0)
STACKS = ('arducopter', 'px4')
STAGES = ('health_and_models', 'encode_send', 'native_inputs')
CONSUMED = ('step', 'diagnostic_step_cpu_timing', 'diagnostic_native_input_timing',
            'rate_group_start', 'rate_group_end')


def period_ns(rate):
    """Original wall period of one four-tick group; same formula as joint_rate."""
    return int(4_000_000 / rate)


class _RowRejected(Exception):
    """One consumed row failed validation; counted and noted, never propagated."""


def _require(condition, message):
    if not condition:
        raise _RowRejected(message)


def _is_int(value):
    return type(value) is int


class GroupWorkTiming:
    """Consume-only bounded recorder; see module docstring for the contract."""

    def __init__(self, emit=None, report_limit=REPORT_LIMIT, census=False):
        if not _is_int(report_limit) or not 0 <= report_limit <= REPORT_LIMIT:
            raise ValueError('report_limit must be an int in [0, %d]' % REPORT_LIMIT)
        self._emit = emit
        self._report_limit = report_limit
        self._census = bool(census)
        self.invalid = False
        self.invalid_reason = None
        self.counts = dict(groups_complete=0, groups_incomplete=0, over_budget_groups=0,
                           reports_emitted=0, reports_dropped=0, diagnostic_errors=0)
        self._reasons = []
        self._epoch = None
        self._last_step_tick = None
        self._last_segment = None
        self._last_group_end_tick = None
        self._segment_previous_start = None  # per-segment previous actual_start_ns
        self._current = None   # open group: four steps plus bounded retained samples
        self._previous = None  # at most one previous complete group summary

    # ------------------------------------------------------------------ rows

    def observe(self, row):
        """Consume one wire row; never raises for row data or recorder faults.

        Returns False once the recorder is invalid. The caller's emit callback
        runs outside the fault guard: its exceptions are the caller's own.
        """
        if self.invalid:
            return False
        try:
            report = self._process(row)
        except Exception as error:  # recorder fault: invalidate this diagnostic only
            self.invalid = True
            self.invalid_reason = '%s: %s' % (type(error).__name__, error)
            self.counts['diagnostic_errors'] += 1
            self._note('recorder fault: %s' % self.invalid_reason)
            return False
        if report is not None:
            self._emit(report)
            self.counts['reports_emitted'] += 1
        return True

    def _note(self, reason):
        if len(self._reasons) < MAX_REASONS:
            self._reasons.append(reason)

    def _process(self, row):
        try:
            return self._handle(row)
        except _RowRejected as rejected:
            self.counts['diagnostic_errors'] += 1
            kind = row.get('kind') if isinstance(row, dict) else None
            self._note('%s tick %s: %s' % (kind, row.get('tick') if isinstance(row, dict) else None,
                                           rejected))
            if kind == 'rate_group_end':
                self._finalize_incomplete(str(rejected))
            return None

    def _handle(self, row):
        _require(isinstance(row, dict), 'row is not a dict')
        kind = row.get('kind')
        if kind not in CONSUMED:
            return None
        epoch = row.get('epoch')
        _require(isinstance(epoch, str) and epoch, 'missing epoch')
        if self._epoch is None:
            self._epoch = epoch
        _require(epoch == self._epoch, 'cross-epoch row')  # one recorder per epoch
        _require(_is_int(row.get('tick')), 'missing integer tick')
        if kind == 'step':
            self._handle_step(row['tick'])
        elif kind == 'diagnostic_step_cpu_timing':
            self._handle_cpu(row)
        elif kind == 'diagnostic_native_input_timing':
            self._handle_native(row)
        elif kind == 'rate_group_start':
            self._handle_group_start(row)
        else:
            return self._handle_group_end(row)
        return None

    # ------------------------------------------------------------------ steps

    def _handle_step(self, tick):
        if self._last_step_tick is not None:
            _require(tick > self._last_step_tick,
                     'duplicate or out-of-order step tick %d' % tick)
        self._last_step_tick = tick
        group = self._current
        if group is None:
            return  # startup steps precede the first group; order still tracked
        expected = group['start_tick'] + 1 + len(group['steps'])
        if tick != expected:
            group['broken'] = 'step tick %d, expected %d' % (tick, expected)
            return
        if len(group['steps']) >= 4:
            group['broken'] = 'extra step past four-step group'
            return
        group['steps'].append(tick)

    # -------------------------------------------------------- diagnostic rows

    def _attach_window(self, group, tick, first_start_ns, kind):
        """Order/duplicate/lower-bound guard shared by both diagnostic kinds.

        Producer order per tick is step -> native -> cpu, so a native row must
        strictly advance the diagnostic tick, while a cpu row may share the tick
        of its native row. At most one row of each kind per tick; violations
        reject the row and taint the group. first_start_ns is the row's earliest
        window start (cpu: its own; native: its first wait segment's).
        """
        if not (group['start_tick'] < tick <= group['end_tick']):
            group['broken'] = '%s tick %d outside group' % (kind, tick)
            _require(False, '%s tick outside open group' % kind)
        last_tick, last_kind = group['last_diag_tick'], group['last_diag_kind']
        ordered = tick > last_tick or (kind == 'cpu' and tick == last_tick
                                       and last_kind == 'native')
        if not ordered:
            group['broken'] = 'duplicate or out-of-order %s at tick %d' % (kind, tick)
            _require(False, group['broken'])
        if first_start_ns < group['actual_start_ns']:
            group['broken'] = '%s window starts before group start' % kind
            _require(False, group['broken'])
        group['last_diag_tick'] = tick
        group['last_diag_kind'] = kind

    def _handle_cpu(self, row):
        _require(_is_int(row.get('wall_start_ns')) and _is_int(row.get('wall_end_ns')),
                 'cpu row missing integer window')
        _require(row['wall_end_ns'] >= row['wall_start_ns'], 'cpu window regressed')
        stages = row.get('stages')
        _require(isinstance(stages, dict) and tuple(sorted(stages)) == tuple(sorted(STAGES)),
                 'cpu row stage set differs')
        total = 0
        for name in STAGES:
            stage = stages[name]
            _require(isinstance(stage, dict)
                     and _is_int(stage.get('wall_ns')) and _is_int(stage.get('thread_cpu_ns')),
                     'cpu stage missing integers')
            _require(stage['wall_ns'] >= 0 and stage['thread_cpu_ns'] >= 0,
                     'cpu stage negative')
            # Thread CPU is retained as recorded; it may exceed wall (shifted
            # windows) and is never attributed to an OS cause from wall-CPU.
            total += stage['wall_ns']
        _require(total == row['wall_end_ns'] - row['wall_start_ns'],
                 'cpu stage wall_ns sum does not close')
        group = self._current
        if group is None:
            return  # before the first group: sampled rows are ignored
        self._attach_window(group, row['tick'], row['wall_start_ns'], 'cpu')
        group['cpu_rows'].append(dict(tick=row['tick'], wall_start_ns=row['wall_start_ns'],
                                      wall_end_ns=row['wall_end_ns'],
                                      stages={name: dict(stages[name]) for name in STAGES}))

    def _handle_native(self, row):
        _require(_is_int(row.get('native_wait_wall_ns')), 'native row missing total')
        waits = row.get('waits')
        _require(isinstance(waits, list) and waits, 'native row has no waits')
        seen = []
        for segment in waits:
            _require(isinstance(segment, dict) and segment.get('stack') in STACKS,
                     'native wait stack differs')
            for key in ('wall_start_ns', 'wall_end_ns', 'wall_ns', 'thread_cpu_ns'):
                _require(_is_int(segment.get(key)), 'native wait missing integer ' + key)
            # A zero-length wait is accepted: a real clock can read the same value.
            _require(segment['wall_end_ns'] >= segment['wall_start_ns'],
                     'native wait window regressed')
            _require(segment['wall_ns'] == segment['wall_end_ns'] - segment['wall_start_ns'],
                     'native wait wall_ns does not match its bracket')
            _require(segment['thread_cpu_ns'] >= 0, 'native wait CPU negative')
            if segment['stack'] == 'arducopter':
                _require(_is_int(segment.get('ap_frame')), 'AP wait missing ap_frame')
            else:
                _require(segment.get('px4_time_us') is None or _is_int(segment.get('px4_time_us')),
                         'PX4 wait px4_time_us not integer/None')
            seen.append(segment['stack'])
        _require(sum(segment['wall_ns'] for segment in waits) == row['native_wait_wall_ns'],
                 'native wait segments do not sum to the record total')
        _require(all(a['wall_end_ns'] <= b['wall_start_ns'] for a, b in zip(waits, waits[1:])),
                 'overlapping native waits in one row')
        _require(seen == sorted(seen, key=STACKS.index) and len(set(seen)) == len(seen),
                 'duplicate or misordered native wait stacks')
        group = self._current
        if group is None:
            return
        self._attach_window(group, row['tick'], waits[0]['wall_start_ns'], 'native')
        group['native_rows'].append(dict(tick=row['tick'],
            native_wait_wall_ns=row['native_wait_wall_ns'],
            waits=[dict(segment) for segment in waits]))

    # ----------------------------------------------------------------- groups

    def _handle_group_start(self, row):
        if self._current is not None:
            self._note('group at tick %d never ended' % self._current['start_tick'])
            self._finalize_incomplete('superseded by a new group start')
        start = row['start_tick']
        segment = row['segment_id']
        rate = row.get('requested_rate')
        _require(_is_int(start) and start % 4 == 0 and row['tick'] == start,
                 'group start tick differs')
        _require(_is_int(row.get('end_tick')) and row['end_tick'] == start + 4,
                 'group end tick differs')
        _require(_is_int(segment), 'group segment missing')
        _require(type(rate) is float and rate in RATES, 'group rate differs')
        period = period_ns(rate)
        ideal = row['ideal_start_ns']
        earliest = row['earliest_start_ns']
        actual = row['actual_start_ns']
        for key in ('ideal_start_ns', 'earliest_start_ns', 'actual_start_ns',
                    'ideal_end_ns', 'lateness_ns'):
            _require(_is_int(row.get(key)), 'group start missing integer ' + key)
        _require(row['ideal_end_ns'] == ideal + period, 'group ideal end equation differs')
        _require(earliest >= ideal, 'group earliest precedes ideal')
        if self._last_segment is not None:
            _require(segment >= self._last_segment, 'segment order regressed')
            if self._last_group_end_tick is not None:
                _require(start >= self._last_group_end_tick, 'group ticks regressed')
                if segment == self._last_segment:
                    _require(start == self._last_group_end_tick, 'groups not contiguous')
                    _require(earliest == max(ideal, self._segment_previous_start + period),
                             'no-catch-up earliest equation differs')
                else:  # reanchor: new segment starts without a previous start
                    _require(earliest == ideal, 'reanchor earliest equation differs')
            # after an incomplete group the continuity/anchor equations are
            # unverifiable; that group was already counted incomplete
        else:
            _require(earliest == ideal, 'first group earliest equation differs')
        _require(actual >= earliest, 'group actual start precedes earliest')
        _require(row['lateness_ns'] == max(0, actual - ideal),
                 'group start lateness equation differs')
        self._last_segment = segment
        self._current = dict(segment_id=segment, requested_rate=rate, period_ns=period,
                             start_tick=start, end_tick=row['end_tick'], ideal_start_ns=ideal,
                             ideal_end_ns=row['ideal_end_ns'], earliest_start_ns=earliest,
                             actual_start_ns=actual, start_lateness_ns=row['lateness_ns'],
                             steps=[], cpu_rows=[], native_rows=[],
                             last_diag_tick=-1, last_diag_kind=None, broken=None)

    def _check_windows(self, group, actual_end_ns):
        """Span, overlap, and native_inputs stage containment at the real group end."""
        actual_start = group['actual_start_ns']
        cpu_rows = sorted(group['cpu_rows'], key=lambda cpu: cpu['tick'])
        by_tick = {cpu['tick']: cpu for cpu in cpu_rows}
        for earlier, cpu in zip([None] + cpu_rows, cpu_rows):
            _require(actual_start <= cpu['wall_start_ns']
                     and cpu['wall_end_ns'] <= actual_end_ns,
                     'cpu window outside group span at tick %d' % cpu['tick'])
            _require(earlier is None or earlier['wall_end_ns'] <= cpu['wall_start_ns'],
                     'cpu windows overlap or regress in tick order at tick %d' % cpu['tick'])
        for native in group['native_rows']:
            for segment in native['waits']:
                _require(actual_start <= segment['wall_start_ns']
                         and segment['wall_end_ns'] <= actual_end_ns,
                         'native wait outside group span at tick %d' % native['tick'])
            cpu = by_tick.get(native['tick'])
            if cpu is None:
                _require(not self._census,
                         'census group lacks the cpu row for native tick %d' % native['tick'])
                continue  # sampled mode: stage containment unverifiable, marked in report
            stage_start = (cpu['wall_start_ns'] + cpu['stages']['health_and_models']['wall_ns']
                           + cpu['stages']['encode_send']['wall_ns'])
            for segment in native['waits']:
                _require(stage_start <= segment['wall_start_ns']
                         and segment['wall_end_ns'] <= cpu['wall_end_ns'],
                         'native wait outside the native_inputs stage at tick %d'
                         % native['tick'])

    def _handle_group_end(self, row):
        group = self._current
        _require(group is not None, 'orphan rate_group_end')
        _require(row['segment_id'] == group['segment_id'], 'group end segment differs')
        _require(row['tick'] == group['end_tick'] == row['end_tick'],
                 'group end tick differs')
        _require(row['start_tick'] == group['start_tick'], 'group end start differs')
        _require(row['requested_rate'] == group['requested_rate'], 'group end rate differs')
        for key in ('ideal_start_ns', 'ideal_end_ns', 'earliest_start_ns',
                    'actual_start_ns', 'actual_end_ns', 'lateness_ns'):
            _require(_is_int(row.get(key)), 'group end missing integer ' + key)
        _require(row['ideal_start_ns'] == group['ideal_start_ns']
                 and row['ideal_end_ns'] == group['ideal_end_ns']
                 and row['earliest_start_ns'] == group['earliest_start_ns']
                 and row['actual_start_ns'] == group['actual_start_ns'],
                 'group end boundary fields differ from the start record')
        _require(row['actual_end_ns'] >= group['actual_start_ns'], 'group end regressed')
        _require(row['lateness_ns'] == max(0, row['actual_end_ns'] - group['ideal_end_ns']),
                 'group end lateness equation differs')
        self._check_windows(group, row['actual_end_ns'])
        if self._census:
            _require(len(group['cpu_rows']) == 4,
                     'census group has %d of 4 cpu rows' % len(group['cpu_rows']))
        work = row['actual_end_ns'] - group['actual_start_ns']
        if group['broken'] is not None or group['steps'] != list(
                range(group['start_tick'] + 1, group['start_tick'] + 5)):
            reason = group['broken'] or 'missing steps'
            self._note('group at tick %d incomplete: %s' % (group['start_tick'], reason))
            self._finalize_incomplete(reason)
            return None
        decomposition = None
        if self._census:
            decomposition = self._decompose(group, row['actual_end_ns'], work)
        self.counts['groups_complete'] += 1
        report = None
        if work > group['period_ns']:
            self.counts['over_budget_groups'] += 1
            if self._emit is not None:
                if self.counts['reports_emitted'] >= self._report_limit:
                    self.counts['reports_dropped'] += 1
                else:
                    report = self._report(group, row, work, decomposition)
        # normal groups (and counted over-budget ones) are in-memory only
        self._last_group_end_tick = group['end_tick']
        self._segment_previous_start = group['actual_start_ns']
        self._previous = dict(segment_id=group['segment_id'], start_tick=group['start_tick'],
                              work_ns=work, excess_ns=work - group['period_ns'])
        self._current = None
        return report

    def _finalize_incomplete(self, reason):
        if self._current is not None:
            self.counts['groups_incomplete'] += 1
            self._last_group_end_tick = None
            self._last_segment = self._current['segment_id']
            self._segment_previous_start = None
            self._current = None

    # ----------------------------------------------------------------- report

    def _decompose(self, group, actual_end_ns, work):
        """Exact census decomposition: prefix + 4 durations + 3 gaps + suffix == work."""
        retained = sorted(group['cpu_rows'], key=lambda cpu: cpu['tick'])
        windows = [(cpu['wall_start_ns'], cpu['wall_end_ns']) for cpu in retained]
        prefix = windows[0][0] - group['actual_start_ns']
        durations = [end - start for start, end in windows]
        gaps = [windows[i + 1][0] - windows[i][1] for i in range(3)]
        suffix = actual_end_ns - windows[3][1]
        closes = prefix + sum(durations) + sum(gaps) + suffix == work
        if prefix < 0 or suffix < 0 or any(gap < 0 for gap in gaps) or not closes:
            raise _RowRejected('census work decomposition does not close')
        return dict(prefix_ns=prefix, step_durations_ns=durations,
                    step_gaps_ns=gaps, suffix_ns=suffix, closes=True)

    def _report(self, group, end_row, work, decomposition):
        phases = {}
        for name in STAGES:
            rows = [cpu['stages'][name] for cpu in group['cpu_rows']]
            phases[name] = dict(wall_ns=sum(stage['wall_ns'] for stage in rows),
                                thread_cpu_ns=sum(stage['thread_cpu_ns'] for stage in rows),
                                samples=len(rows))
        retained = sorted(group['cpu_rows'], key=lambda cpu: cpu['tick'])
        steps = [dict(tick=cpu['tick'], wall_start_ns=cpu['wall_start_ns'],
                      wall_end_ns=cpu['wall_end_ns'],
                      wall_ns=cpu['wall_end_ns'] - cpu['wall_start_ns'],
                      thread_cpu_ns=sum(cpu['stages'][name]['thread_cpu_ns'] for name in STAGES),
                      gap_from_previous_retained_ns=(
                          cpu['wall_start_ns'] - earlier['wall_end_ns'] if earlier else None))
                 for earlier, cpu in zip([None] + retained, retained)]
        by_tick = {cpu['tick']: cpu for cpu in retained}
        waits = [dict(tick=native['tick'], stage_verified=native['tick'] in by_tick, **segment)
                 for native in group['native_rows'] for segment in native['waits']]
        report = dict(kind='group_work_timing', schema=SCHEMA,
                      classification='diagnostic_only', full_acceptance=False,
                      census=self._census, epoch=self._epoch, segment_id=group['segment_id'],
                      start_tick=group['start_tick'], end_tick=group['end_tick'],
                      requested_rate=group['requested_rate'], period_ns=group['period_ns'],
                      work_ns=work, excess_ns=work - group['period_ns'],
                      preceding_boundary=dict(ideal_start_ns=group['ideal_start_ns'],
                                              earliest_start_ns=group['earliest_start_ns'],
                                              actual_start_ns=group['actual_start_ns'],
                                              lateness_ns=group['start_lateness_ns']),
                      following_boundary=dict(ideal_end_ns=group['ideal_end_ns'],
                                              actual_end_ns=end_row['actual_end_ns'],
                                              lateness_ns=end_row['lateness_ns']),
                      phases=phases, retained_steps=steps, visible_native_waits=waits)
        if self._census:
            report['work_decomposition'] = decomposition
            report['step_windows'] = [dict(tick=cpu['tick'], wall_start_ns=cpu['wall_start_ns'],
                                           wall_end_ns=cpu['wall_end_ns'],
                                           stages={name: dict(cpu['stages'][name])
                                                   for name in STAGES})
                                      for cpu in retained]
        else:
            report['phase_coverage'] = ('sampled: %d of 4 steps carry diagnostic rows; not a '
                                        'census, no work decomposition' % len(retained))
        if self._previous is not None:
            report['previous_group'] = dict(self._previous)
        return report

    # ---------------------------------------------------------------- summary

    def finish(self):
        """Finalize any unclosed group as incomplete; returns summary()."""
        if self._current is not None:
            self._note('group at tick %d unfinished at finish()' % self._current['start_tick'])
            self._finalize_incomplete('unfinished at finish()')
        return self.summary()

    def summary(self):
        """Value of the future 'group_work_timing' result field (diagnostic-only)."""
        unfinished = None
        if self._current is not None:
            unfinished = dict(start_tick=self._current['start_tick'],
                              segment_id=self._current['segment_id'],
                              steps_seen=len(self._current['steps']))
        valid = (not self.invalid and not self.counts['diagnostic_errors']
                 and not self.counts['groups_incomplete'] and self._current is None)
        return dict(schema=SCHEMA, classification='diagnostic_only', full_acceptance=False,
                    field='group_work_timing', reports_enabled=self._emit is not None,
                    report_limit=self._report_limit, census=self._census, epoch=self._epoch,
                    valid=valid, invalid_reason=self.invalid_reason,
                    reasons=list(self._reasons), unfinished_group=unfinished,
                    counts=dict(self.counts),
                    limitations=(
                        'sampled mode retains diagnostic rows only for >2ms or tick%250==0 '
                        'steps; coverage is marked, never a census; census mode requires all '
                        'four cpu rows for the exact work decomposition',
                        'thread CPU is the recorded value; no OS cause is attributed from '
                        'wall-CPU and CPU is never required to be <= wall',
                        'data errors make valid=false with reasons recorded; recorder faults '
                        'invalidate this diagnostic only and never mask caller exceptions',
                        'the formal validator rejects the group_work_timing field; enabling it '
                        'keeps the evidence diagnostic-only'))
