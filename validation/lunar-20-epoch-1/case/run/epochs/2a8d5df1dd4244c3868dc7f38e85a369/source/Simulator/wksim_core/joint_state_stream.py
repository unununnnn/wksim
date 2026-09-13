"""Bounded, view-only state of an authoritative two-vehicle scene."""
import json
import math
import re
import socket
import time

from .state_stream import METADATA,MAX_AGE,identity

MAX_PACKET=8192
MAX_INTEGER=2**53-1
STACKS={1:'arducopter',2:'px4'}
FIELDS=set(METADATA)|{'version','kind','run_id','instance_id','epoch','generation','sequence',
                      'step','sim_time_ns','phase','source_wall_time_s','vehicles'}
VEHICLE_FIELDS={'vehicle_id','stack','position_ned_m','quaternion_wxyz','rotor_rpm','model_time_s'}


def hex_identity(value):
    return isinstance(value,str) and re.fullmatch('[0-9a-f]{32}',value) is not None


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def validate(packet,run_id,instance_id,now=None):
    identity(run_id,1)
    if not hex_identity(instance_id):raise ValueError('Invalid manager instance')
    if not isinstance(packet,dict) or set(packet)!=FIELDS:
        raise ValueError('Joint state fields differ')
    if (type(packet['version']) is not int or packet['version']!=3 or packet['kind']!='joint_state'
            or packet['run_id']!=run_id or packet['instance_id']!=instance_id or not hex_identity(packet['epoch'])
            or any(packet[key]!=value for key,value in METADATA.items())):
        raise ValueError('Joint identity or physical convention differs')
    for key in ('generation','sequence','step','sim_time_ns'):
        if type(packet[key]) is not int or not 0<=packet[key]<=MAX_INTEGER:
            raise ValueError('Invalid '+key)
    if (packet['generation']<1 or packet['sim_time_ns']!=packet['step']*1_000_000
            or packet['phase'] not in ('running','paused','faulted','stopped')):
        raise ValueError('Invalid authoritative time or phase')
    wall=packet['source_wall_time_s']
    if not finite(wall) or wall<0 or not -.25<=(time.time() if now is None else now)-wall<=MAX_AGE:
        raise ValueError('Expired or future joint source')
    vehicles=packet['vehicles']
    if not isinstance(vehicles,list) or not 1<=len(vehicles)<=2:
        raise ValueError('Expected one or two vehicle records')
    seen=set()
    for item in vehicles:
        if not isinstance(item,dict) or set(item)!=VEHICLE_FIELDS:
            raise ValueError('Vehicle state fields differ')
        uid=item['vehicle_id']
        if type(uid) is not int or uid not in STACKS or uid in seen or item['stack']!=STACKS[uid]:
            raise ValueError('Duplicate or mismatched vehicle identity')
        seen.add(uid)
        for key,length in (('position_ned_m',3),('quaternion_wxyz',4),('rotor_rpm',4)):
            value=item[key]
            if not isinstance(value,list) or len(value)!=length or not all(finite(v) for v in value):
                raise ValueError('Invalid '+key)
        if (max(map(abs,item['position_ned_m']))>1e6
                or abs(sum(v*v for v in item['quaternion_wxyz'])-1)>1e-5
                or any(not 0<=v<=100000 for v in item['rotor_rpm'])
                or not finite(item['model_time_s']) or item['model_time_s']<0
                or abs(item['model_time_s']-packet['step']/1000)>1e-8):
            raise ValueError('Invalid physical state or uncommitted model time')
    return packet


def unique(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('Duplicate JSON key')
        value[key]=item
    return value


class LatestJointState:
    def __init__(self,run_id,instance_id):
        identity(run_id,1)
        if not hex_identity(instance_id):raise ValueError('Invalid manager instance')
        self.run_id,self.instance_id=run_id,instance_id
        self.packet=None
        self.rejected=0

    def accept(self,raw,now=None):
        try:
            if len(raw)>MAX_PACKET:raise ValueError('Oversize joint state')
            packet=validate(json.loads(raw,object_pairs_hook=unique),self.run_id,self.instance_id,now)
            old=self.packet
            new=old is None or packet['generation']>old['generation']
            if (new and (len(packet['vehicles'])!=2 or old is not None and packet['epoch']==old['epoch'])
                    or old is not None and packet['generation']<old['generation']
                    or old is not None and not new and (packet['epoch']!=old['epoch']
                        or packet['sequence']<=old['sequence'] or packet['step']<old['step'])):
                raise ValueError('Old scene state or incomplete new generation')
        except (ValueError,TypeError,UnicodeError,OverflowError,RecursionError):
            self.rejected+=1
            return False
        self.packet=packet
        return True

    def current(self):
        if self.packet:
            try:return validate(self.packet,self.run_id,self.instance_id)
            except ValueError:pass
        return None


class JointStateWriter:
    """One nonblocking datagram at most every 50ms, never an ACK or retry queue."""
    def __init__(self,path,run_id,instance_id,epoch,generation):
        self.socket=None;self.sequence=0;self.dropped=0;self.sent=0;self.next_send=0;self.setup_error=None;self.last_error=None
        self.run_id,self.instance_id,self.epoch,self.generation=run_id,instance_id,epoch,generation
        if path is not None:
            identity(run_id,1)
            if not hex_identity(instance_id) or not hex_identity(epoch) or type(generation) is not int or generation<1:
                raise ValueError('Invalid joint writer identity')
            self.path=str(path)
            if not self.path.startswith('/') or len(self.path.encode())>107:
                raise ValueError('Joint state socket must be an absolute Linux pathname <=107 bytes')
            try:
                self.socket=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
                self.socket.setblocking(False)
            except OSError as error:
                if self.socket:self.socket.close()
                self.socket=None;self.setup_error=repr(error)

    def emit(self,states,tick,phase,*,force=False):
        if self.socket is None or states is None:return False
        now=time.monotonic()
        if not force and now<self.next_send:return False
        self.next_send=now+.05;self.sequence+=1
        try:
            packet=dict(METADATA,version=3,kind='joint_state',run_id=self.run_id,instance_id=self.instance_id,
                epoch=self.epoch,generation=self.generation,sequence=self.sequence,step=tick,
                sim_time_ns=tick*1_000_000,phase=phase,source_wall_time_s=time.time(),vehicles=[])
            for uid,stack in STACKS.items():
                state=states[stack]
                packet['vehicles'].append(dict(vehicle_id=uid,stack=stack,position_ned_m=list(state[6:9]),
                    quaternion_wxyz=list(state[12:16]),rotor_rpm=list(state[16:20]),model_time_s=state[2]))
            validate(packet,self.run_id,self.instance_id)
            raw=json.dumps(packet,separators=(',',':'),allow_nan=False).encode()
            if len(raw)>MAX_PACKET:raise ValueError('Oversize joint state')
            self.socket.sendto(raw,self.path);self.sent+=1;self.last_error=None
            return True
        except (OSError,ValueError,TypeError,KeyError,IndexError,OverflowError) as error:
            self.dropped+=1
            self.last_error=repr(error)
            return False

    def close(self):
        if self.socket:self.socket.close()
