"""Submit one explicit operator takeover request for the current human GCS run."""
import argparse
import json
import os
from pathlib import Path
import re
import uuid

REPO=Path(__file__).resolve().parents[1]


def request_takeover(output, action='takeover'):
    event,filename={'takeover':('awaiting_explicit_takeover','takeover-request.json'),
                    'start_flight':('awaiting_window_ready','start-flight-request.json')}[action]
    output=Path(output).absolute()
    if (output.resolve()!=output or not output.is_relative_to(REPO/'validation')
            or (output/'report.json').exists()):
        raise ValueError('Expected an unfinished real validation run directory')
    config=json.loads((output/'config.json').read_text())
    formal=output/'formal'
    if formal.resolve()!=formal:
        raise ValueError('Formal output directory must not be an alias')
    report=json.loads((formal/'report.json').read_text())
    current=json.loads((formal/'human-handoff.json').read_text())['current']
    if report.get('status')!='running' or current.get('event')!=event:
        raise ValueError('Run is not awaiting an explicit takeover decision')
    request=current['request']
    if (set(request)!={'version','action','run_id','control_epoch','nonce'}
            or type(request['version']) is not int or request['version']!=1 or request['action']!=action
            or request['run_id']!=config['run_id'] or request['run_id']!=current['run_id']
            or request['control_epoch']!=current['control_epoch']
            or not re.fullmatch('[0-9a-f]{32}',request['control_epoch'])
            or not re.fullmatch('[0-9a-f]{32}',request['nonce'])):
        raise ValueError('Current takeover request identity differs')
    path=formal/filename
    # Exclusive creation: an existing decision is never replaced or re-labelled.
    temporary=formal/('takeover-'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('x',encoding='utf-8') as stream:
            json.dump(request,stream)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary,path)  # Atomic and exclusive on the same filesystem.
    finally:
        temporary.unlink(missing_ok=True)
    return dict(status='request_written',path=str(path),request=request,
                limitation='Publication is not native acceptance; wait for the running experiment result')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--action',choices=('takeover','start_flight'),default='takeover')
    args=parser.parse_args()
    print(json.dumps(request_takeover(args.output,args.action),indent=2))
