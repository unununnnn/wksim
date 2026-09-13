"""Opt-in runtime-loop intervals around the existing physics timing probe."""
import time


class LoopTiming:
    def __init__(self, enabled, record, now=time.monotonic_ns, cpu=time.thread_time_ns):
        self.enabled,self.record,self.now,self.cpu=enabled,record,now,cpu

    def start(self,origin=None):
        if not self.enabled:return
        self.last=origin if origin is not None else (self.now(),self.cpu())
        self.started=self.last[0]
        self.stages={}

    def mark(self,name):
        if not self.enabled:return
        current=(self.now(),self.cpu())
        self.stages[name]=dict(wall_ns=current[0]-self.last[0],thread_cpu_ns=current[1]-self.last[1])
        self.last=current

    def finish(self,tick,*,complete):
        if not self.enabled:return
        work=sum(value['wall_ns'] for name,value in self.stages.items() if name!='pacing')
        if not complete or work>2_000_000 or tick%250==0:
            self.record('diagnostic_runtime_loop_timing',observed_tick=tick,complete=complete,
                wall_start_ns=self.started,wall_end_ns=self.last[0],stages=dict(self.stages),
                limitation='Sampled runtime intervals; pacing includes intended waits. '
                           'Thread CPU and wall clocks have distinct read windows; no causal classification.')
