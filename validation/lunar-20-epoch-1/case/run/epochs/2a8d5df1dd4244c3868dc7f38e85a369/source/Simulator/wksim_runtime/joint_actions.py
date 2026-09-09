"""Explicit, epoch-bound joint actions. File submission is not action completion."""
import argparse
import json
from pathlib import Path
import re
import time
import uuid

from .config import _unique_object,_invalid_constant
from .evidence import write_json
from .joint_rate import validate_rate

ACTIONS=frozenset(('start-task','pause','step','resume','recover','start-recovery-task','cold-reset','stop','set-rate'))


def read_json(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>1024*1024:
        raise ValueError('Missing, oversized or symlinked joint control file')
    return json.loads(path.read_text(),object_pairs_hook=_unique_object,parse_constant=_invalid_constant)


def validate_request(value,run_id,epoch):
    keys={'version','run_id','epoch','command_id','action','offer_token','token'}
    if isinstance(value,dict) and value.get('action')=='set-rate': keys.add('requested_rate')
    if not isinstance(value,dict) or set(value)!=keys:
        raise ValueError('Invalid joint request fields')
    if (type(value['version']) is not int or value['version']!=1 or value['run_id']!=run_id
            or value['epoch']!=epoch or type(value['command_id']) is not int
            or not 0<value['command_id']<2**64 or value['action'] not in ACTIONS
            or any(not isinstance(value[key],str) or not re.fullmatch('[0-9a-f]{32}',value[key])
                   for key in ('offer_token','token'))):
        raise ValueError('Foreign, retired or malformed joint request')
    if value['action']=='set-rate': validate_rate(value['requested_rate'])
    return value


def submit(directory,action,expected_epoch=None,requested_rate=None):
    directory=Path(directory).resolve(strict=True)
    status=read_json(directory/'status.json')
    if (action not in ACTIONS or action not in status.get('allowed_actions',[])
            or expected_epoch is not None and status['epoch']!=expected_epoch):
        raise ValueError('Action is unavailable or scene epoch changed')
    age=time.monotonic()-status['issued_monotonic_s']
    if action!='stop' and not 0<=age<=2.:
        raise ValueError('Joint status is stale; inspect current status before acting')
    token=uuid.uuid4().hex
    if (action=='set-rate')!=(requested_rate is not None):
        raise ValueError('Only set-rate requires requested_rate')
    fields={'requested_rate':validate_rate(requested_rate)} if action=='set-rate' else {}
    request=validate_request(dict(version=1,run_id=status['run_id'],epoch=status['epoch'],
        command_id=time.monotonic_ns(),action=action,offer_token=status['offer_token'],token=token,**fields),
        status['run_id'],status['epoch'])
    path=directory/'actions'/f"{request['command_id']:020d}-{token}.json"
    if path.exists():
        raise FileExistsError(path)
    write_json(path,request)
    return dict(state='submitted',request=request,result_file=str(directory/'action-results'/status['epoch']/(token+'.json')))


class Mailbox:
    def __init__(self,directory,run_id,epoch):
        self.directory,self.run_id,self.epoch=Path(directory),run_id,epoch
        self.results=self.directory/'action-results'/epoch
        self.results.mkdir(parents=True,exist_ok=True)
        self.seen=set()
        self.last_command=0

    def respond(self,value,state,**fields):
        record=dict(version=1,run_id=self.run_id,epoch=self.epoch,command_id=value['command_id'],
                    action=value['action'],token=value['token'],state=state,**fields)
        write_json(self.results/(value['token']+'.json'),record)
        return record

    def poll(self,offer_token,allowed,*,only=None):
        for path in sorted((self.directory/'actions').glob('*.json')):
            if path.name in self.seen:
                continue
            if only is not None:
                try:
                    candidate=read_json(path)
                    if isinstance(candidate,dict) and candidate.get('action') not in only: continue
                except (OSError,ValueError,TypeError): pass
            self.seen.add(path.name)
            value=None
            try:
                value=read_json(path)
                validate_request(value,self.run_id,self.epoch)
                if path.name!=f"{value['command_id']:020d}-{value['token']}.json":
                    raise ValueError('Request filename differs from envelope identity')
                if (self.results/(value['token']+'.json')).exists():
                    raise ValueError('Joint action token already consumed')
                if value['command_id']<=self.last_command:
                    raise ValueError('Replayed or out-of-order joint command')
                self.last_command=value['command_id']
                if value['action'] not in allowed or value['action']!='stop' and value['offer_token']!=offer_token:
                    raise ValueError('Joint action offer changed or is unavailable')
            except (OSError,ValueError,TypeError) as error:
                write_json(self.results/('rejected-'+path.name),dict(state='rejected',reason=str(error),
                    run_id=self.run_id,epoch=self.epoch,request=value))
                # A current, valid submission needs a terminal response at the
                # advertised path. Retired or consumed identities stay intact.
                try:
                    validate_request(value,self.run_id,self.epoch)
                    if not (self.results/(value['token']+'.json')).exists():
                        self.respond(value,'rejected',reason=str(error))
                except (ValueError,TypeError):
                    pass
                continue
            self.respond(value,'accepted')
            return value
        return None


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('action',choices=sorted(ACTIONS))
    parser.add_argument('--epoch')
    parser.add_argument('--rate',type=float)
    args=parser.parse_args()
    try:
        print(json.dumps(submit(args.directory,args.action,args.epoch,args.rate),indent=2))
    except (OSError,ValueError) as error:
        parser.exit(2,str(error)+'\n')
