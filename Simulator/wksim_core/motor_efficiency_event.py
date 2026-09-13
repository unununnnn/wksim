"""One immutable, identity-bound rotor-0 event consumed before each native tick."""
import json
import re
import os
import tempfile
from pathlib import Path

SCHEMA='wksim.motor-efficiency.v1'
HASH_FIELDS=('config_sha256','protocol_sha256','original_source_sha256',
             'parameterized_source_sha256','wrapper_sha256','library_sha256')
IDENTITY_FIELDS={'run_id','instance_id','control_epoch','model_identity',*HASH_FIELDS}


def integer(value):
    if type(value) is not int or not 0<=value<2**53:
        raise ValueError('Invalid integer tick')
    return value


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def make_plan(identity,origin_tick):
    if type(identity) is not dict or set(identity)!=IDENTITY_FIELDS:
        raise ValueError('Incomplete event identity')
    if (not isinstance(identity['run_id'],str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',identity['run_id'])
            or type(identity['instance_id']) is not int or not 1<=identity['instance_id']<=255
            or not isinstance(identity['control_epoch'],str) or not re.fullmatch('[0-9a-f]{32}',identity['control_epoch'])
            or any(not isinstance(identity[k],str) or not re.fullmatch('[0-9a-f]{64}',identity[k]) for k in HASH_FIELDS)
            or identity['model_identity']!='sha256:'+identity['library_sha256']):
        raise ValueError('Invalid event identity')
    origin=integer(origin_tick)
    integer(origin+11000)
    return dict(schema=SCHEMA,**identity,motor_index=0,multiplier=.97,seed=0,origin_tick=origin,
                start_tick=origin+2000,end_tick=origin+3000,recovery_deadline_tick=origin+11000,
                recovery_dwell_ticks=1500)


def publish_plan(path,plan):
    # The consumer sees either absence or the complete no-clobber publication.
    path=Path(path)
    descriptor,temporary=tempfile.mkstemp(prefix='.efficiency-',dir=path.parent)
    try:
        with os.fdopen(descriptor,'wb') as output:
            output.write(canonical(plan))
            output.flush(); os.fsync(output.fileno())
        os.link(temporary,path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_plan(path):
    def pairs(items):
        value={}
        for key,item in items:
            if key in value: raise ValueError('Duplicate event key')
            value[key]=item
        return value
    return json.loads(Path(path).read_bytes(),object_pairs_hook=pairs)


class EfficiencyEvent:
    def __init__(self,plan,identity,*,loaded_tick,path=None):
        integer(loaded_tick)
        expected=make_plan(identity,plan.get('origin_tick'))
        if canonical(plan)!=canonical(expected):
            raise ValueError('Event fields, identity or frozen timing differ')
        if loaded_tick>expected['start_tick']-1000:
            raise ValueError('Event must arrive at least 1000 ticks before start')
        self.plan=expected
        self.path=Path(path) if path is not None else None
        self.raw=canonical(plan)
        if self.path is not None and self.path.read_bytes()!=self.raw:
            raise ValueError('Event file differs from canonical admitted plan')
        self.next_tick=loaded_tick
        self.state='pending'
        self.activations=0
        self.last=None

    def step(self,model,commands,*,tick,revoke=False):
        try:
            integer(tick)
            if getattr(model,'_efficiency_failed',False): raise ValueError('Native event failure is latched')
            if getattr(model,'_efficiency_event',self) is not self:
                raise ValueError('Second event in the same native model lifetime')
            model._efficiency_event=self
            if self.state=='failed': raise ValueError('Event failure is latched')
            if type(revoke) is not bool: raise ValueError('Invalid revoke flag')
            if tick!=self.next_tick or model.ticks!=tick:
                raise ValueError('Event/native tick gap or replay')
            if model.library_sha256!=self.plan['library_sha256']:
                raise ValueError('Native model identity changed')
            if self.path is not None and self.path.read_bytes()!=self.raw:
                raise ValueError('Event file modified')
            if revoke: self.state='revoked'
            if self.state not in ('revoked','expired'):
                state='pending' if tick<self.plan['start_tick'] else 'active' if tick<self.plan['end_tick'] else 'expired'
                if state=='active' and self.state!='active': self.activations+=1
                self.state=state
            eta=.97 if self.state=='active' else 1.
            model.set_efficiency(eta)
            output=model.step(commands,1)
            self.last=dict(interval_tick=tick,post_tick=model.ticks,state=self.state,eta=model.efficiency(),
                           activations=self.activations,stages=model.stages,random_state=model.random_state())
            self.next_tick+=1
            return output
        except Exception:
            self.state='failed'
            model._efficiency_failed=True
            # Restore only the next not-yet-started native interval; never mutate
            # coefficients inside an ODE4 call. The supervisor ends this failed run.
            model.set_efficiency(1.)
            raise
