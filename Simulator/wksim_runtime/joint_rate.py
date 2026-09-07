"""Wall pacing of complete four-tick groups; never changes physical time."""
import time


RATES=(0.5,1.0)
LATE_LIMIT_NS=100_000_000


def validate_rate(value):
    if type(value) not in (int,float) or value not in RATES:
        raise ValueError('requested_rate must be 0.5 or 1')
    return float(value)


class RateUnmet(RuntimeError):
    def __init__(self, lateness_ns):
        self.lateness_ns=lateness_ns
        super().__init__('rate_unmet/resource_insufficient')


class JointRate:
    def __init__(self, epoch, requested_rate, record, now=time.monotonic_ns, sleep=time.sleep):
        self.epoch,self.record,self.now,self.sleep=epoch,record,now,sleep
        self.requested_rate=validate_rate(requested_rate)
        self.request_id='config'
        self.segment_id=0
        self.anchor=None
        self.group=None
        self.latched=False
        self.last_summary=None
        self.record('rate_request',request_id=self.request_id,requested_rate=self.requested_rate)

    @property
    def period_ns(self):
        return int(4_000_000/self.requested_rate)

    def close_segment(self, reason, tick):
        if self.anchor is not None:
            self.last_summary=self.snapshot(tick)
            self.record('rate_segment_end',reason=reason,**self.last_summary)
        self.anchor=self.group=None

    def reanchor(self, tick, reason, *, transition=False, recovery=False):
        if self.latched and not recovery:
            raise ValueError('Latched rate failure requires explicit recovery')
        if tick%4:
            raise ValueError('Rate anchor requires a complete four-tick boundary')
        if not recovery: self.check_boundary(tick)
        self.close_segment(reason,tick)
        if recovery: self.latched=False
        self.segment_id+=1
        self.anchor=dict(tick=tick,wall_ns=self.now(),transition=transition)
        self.previous_start=None
        self.completed=0
        self.last_end=None
        self.worst_lateness_ns=0
        self.record('rate_anchor',reason=reason,**self.snapshot(tick))

    def set_rate(self, value, request_id, tick):
        if self.latched or self.group is not None or tick%4:
            raise ValueError('Rate change requires a healthy completed boundary')
        value=validate_rate(value)
        self.check_boundary(tick)
        self.close_segment('set-rate',tick)
        self.requested_rate,self.request_id=value,request_id
        self.record('rate_request',request_id=request_id,requested_rate=value)

    def check_boundary(self, tick):
        # Time spent processing an action or its final ACK still belongs to
        # the old active plan. A paused scene has no wall-rate obligation.
        if self.anchor is None: return
        if self.group is not None or tick!=self.anchor['tick']+self.completed*4:
            raise ValueError('Rate boundary check requires all four ticks completed')
        ideal=self.anchor['wall_ns']+self.completed*self.period_ns
        now=self.now();lateness=max(0,now-ideal)
        self.record('rate_boundary_check',segment_id=self.segment_id,request_id=self.request_id,
                    requested_rate=self.requested_rate,boundary_tick=tick,ideal_boundary_ns=ideal,
                    actual_check_ns=now,lateness_ns=lateness)
        self.check(lateness)

    def check(self, lateness):
        self.worst_lateness_ns=max(self.worst_lateness_ns,lateness)
        if lateness>LATE_LIMIT_NS:
            self.latched=True
            self.record('rate_unmet',reason='resource_insufficient',lateness_ns=lateness,
                        **self.snapshot(self.anchor['tick']+self.completed*4))
            raise RateUnmet(lateness)

    def begin_group(self, tick, health):
        probe_entry=self.now()
        if self.latched or self.anchor is None or self.group is not None or tick!=self.anchor['tick']+self.completed*4:
            raise ValueError('Rate group lacks a current complete anchor')
        ideal=self.anchor['wall_ns']+self.completed*self.period_ns
        earliest=max(ideal,ideal if self.previous_start is None else self.previous_start+self.period_ns)
        health()
        probe_health_done=self.now()
        probe_wait_health=probe_sleep=probe_sleep_overshoot=0
        next_health=self.now()+2_000_000
        while True:
            now=self.now()
            self.check(max(0,now-ideal))
            if now>=earliest: break
            # Avoid scheduling a callback on the group's exact release edge.
            # The next physical step immediately services health again.
            if now>=next_health and earliest-now>1_000_000:
                probe_before=self.now()
                health()
                now=self.now()
                probe_wait_health+=now-probe_before
                next_health=now+2_000_000
            self.check(max(0,now-ideal))
            if now>=earliest: break
            # Final 1ms uses the monotonic clock: sleep overshoot on every
            # group otherwise accumulates even when the FCs meet their budget.
            # Long waits service health every 2ms; the release guard adds at
            # most 1ms, far below the unchanged 100ms permission cadence.
            remaining=earliest-now
            if remaining>1_000_000:
                seconds=min((remaining-1_000_000)/1e9,.002)
                probe_before=self.now()
                self.sleep(seconds)
                probe_elapsed=self.now()-probe_before
                probe_sleep+=probe_elapsed
                probe_sleep_overshoot=max(probe_sleep_overshoot,probe_elapsed-round(seconds*1e9))
        self.group=dict(start_tick=tick,end_tick=tick+4,ideal_start_ns=ideal,
                        ideal_end_ns=ideal+self.period_ns,earliest_start_ns=earliest,actual_start_ns=now)
        self.previous_start=now
        self.record('rate_group_start',segment_id=self.segment_id,request_id=self.request_id,
                    requested_rate=self.requested_rate,transition=self.anchor['transition'],
                    timing_probe=dict(entry_ns=probe_entry,initial_health_end_ns=probe_health_done,
                        wait_health_ns=probe_wait_health,sleep_ns=probe_sleep,sleep_max_overshoot_ns=probe_sleep_overshoot),
                    lateness_ns=max(0,now-ideal),**self.group)

    def end_group(self, tick):
        if self.group is None or tick!=self.group['end_tick']:
            raise ValueError('Rate group did not complete exactly four ticks')
        now=self.now()
        lateness=max(0,now-self.group['ideal_end_ns'])
        self.record('rate_group_end',segment_id=self.segment_id,request_id=self.request_id,
                    requested_rate=self.requested_rate,transition=self.anchor['transition'],
                    actual_end_ns=now,lateness_ns=lateness,**self.group)
        self.completed+=1
        self.last_end=now
        self.group=None
        self.check(lateness)

    def snapshot(self, tick):
        value=dict(requested_rate=self.requested_rate,request_id=self.request_id,
                   segment_id=self.segment_id,latched=self.latched,anchor=self.anchor,
                   measured_rate=None,measurement='no_complete_timed_group')
        if self.anchor is not None:
            duration=None if self.last_end is None else self.last_end-self.anchor['wall_ns']
            value.update(completed_groups=self.completed,worst_lateness_ns=self.worst_lateness_ns,
                         steady_after_ns=self.anchor['wall_ns']+2_000_000_000,
                         measured_rate=self.completed*4_000_000/duration if duration and duration>0 else None,
                         measurement='transition' if self.anchor['transition'] else 'timed_segment')
        return value
