"""Atomic evidence publication and identities of owned Linux processes."""
import json
import math
import os
from pathlib import Path
import tempfile


def host_boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def json_value(value):
    if isinstance(value,float) and not math.isfinite(value):
        return {'nonfinite_number':repr(value)}
    if isinstance(value,dict):
        return {key:json_value(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):
        return [json_value(item) for item in value]
    return value


def write_json(path,value):
    target=Path(path)
    raw=json.dumps(json_value(value),indent=2,allow_nan=False)+'\n'
    descriptor,temporary=tempfile.mkstemp(prefix='.'+target.name+'-',suffix='.tmp',dir=target.parent)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as output:
            output.write(raw)
        os.replace(temporary,target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def process_identity(pid):
    root=Path('/proc')/str(pid)
    try:
        fields=(root/'stat').read_text().rsplit(')',1)[1].split()
        return dict(pid=pid,state=fields[0],pgid=int(fields[2]),start_ticks=int(fields[19]),
                    argv=(root/'cmdline').read_bytes().split(b'\0')[:-1])
    except FileNotFoundError:
        return None


def json_identity(pid):
    value=process_identity(pid)
    if value:
        value.pop('state')
        value['argv']=[part.decode(errors='replace') for part in value['argv']]
    return value


def group_members(pgid):
    return [value for entry in Path('/proc').iterdir() if entry.name.isdecimal()
            and (value:=json_identity(int(entry.name))) and value['pgid']==pgid]
