"""Offline MATLAB/public-task/physical/UE cross-check; no command publishers."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_runtime.mission_evidence import audit_mission_truth
from Simulator.ue55.bridge import actor_errors
from Simulator.wksim_console.visual import ACTOR_LIMITS
from validate_operator_http import live_captures


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def rows(path):return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines()]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value,message):
    if not value:raise ValueError(message)


REPORT_SOURCES=('tools/validate_matlab_flight.py','matlab/validate_flight.m','matlab/WksimClient.m',
                'Simulator/wksim_matlab/server.py','Simulator/wksim_console/server.py',
                'Simulator/wksim_console/workspace.py','Simulator/wksim_console/records.py',
                'Simulator/wksim_console/visual.py')


def check_sources(root,directory,report,formal,source_archive):
    sources={name.replace('\\','/'):value for name,value in report['source_sha256'].items()}
    expected=dict(formal['runtime_sha256'])
    for name in REPORT_SOURCES:
        require(name not in expected or expected[name]==sources[name],'Conflicting source hashes: '+name)
        expected[name]=sources[name]
    if source_archive is None:
        require(all(sha(REPO/path)==digest for path,digest in formal['runtime_sha256'].items()),
                'Executed runtime dependency differs from current checked source')
        for name in REPORT_SOURCES:
            require(sha(REPO/name)==sources[name],'MATLAB/bridge/console source differs: '+name)
        return dict(mode='current-checkout',current_checkout_accepted=True)
    archive=Path(source_archive).resolve();manifest=read(archive/'manifest.json')
    require(manifest['mode']=='retained-source-audit','Not a retained source archive')
    entry=manifest['runs'][formal['run_id']]
    require(entry['report_sha256']==sha(root/'report.json') and
            entry['formal_result_sha256']==sha(directory/'result.json'),'Retained archive evidence identity differs')
    require(set(entry['sources'])==set(expected),'Retained archive source coverage differs')
    for name,digest in expected.items():
        item=entry['sources'][name];path=(archive/item['archive_path']).resolve()
        require(path.is_relative_to(archive) and path.is_file(),'Retained source escaped archive or is missing: '+name)
        require(item['sha256']==digest and sha(path)==digest,'Retained source bytes differ: '+name)
    return dict(mode='retained-source-audit',current_checkout_accepted=False,
                archive=str(archive),manifest_sha256=sha(archive/'manifest.json'),sources_checked=len(expected))


def audit(root,source_archive=None):
    root=Path(root).resolve();report=read(root/'report.json')
    launch=read(root/'launch-result.json');reconnect=read(root/'reconnect-result.json')
    require(report['ok'] and launch==report['launch'] and reconnect==report['reconnect'],'MATLAB report did not pass')
    require(launch['ok'] and reconnect['ok'] and launch['session_id']!=reconnect['session_id']
            and launch['bridge_instance']==reconnect['bridge_instance']==report['bridge_instance'],'Reconnect identity/replay differs')
    for phase in ('launch','reconnect'):
        require(report[phase+'_returncode']==0 and report[phase+'_matlab_pid_gone']
                and report[phase+'_private_startup'],'MATLAB did not exit through its private startup')
        require('WKSIM_TASK_STARTUP_ONLY' in (root/(phase+'.stdout.log')).read_text(errors='replace'),
                'Missing actual private startup marker')
    job=root/'console/jobs'/launch['job_id'];directory=job/'runs'/launch['run_id']
    require(directory.resolve().is_relative_to(job.resolve()),'Run escaped evidence directory')
    raw=(directory/'result.json').read_text(encoding='utf-8')
    require(raw==reconnect['result']['raw_json'] and sha(directory/'result.json')==reconnect['result']['sha256'],
            'MATLAB result differs from exact formal file')
    formal=json.loads(raw);task=formal['task'];mission=task['mission']
    require(formal['status']=='pass' and formal['safe_landing'] and formal['children_reaped']
            and not formal['cleanup_errors'] and mission['state']=='completed','Formal flight did not complete safely')
    require(formal['run_id']==launch['run_id'] and formal['stack']==report['stack'],'Flight identity differs')
    require(len(mission['plan']['waypoints'])==6 and all(p['dwell_s']==10 for p in mission['plan']['waypoints']),
            'Flight did not use the preselected six 10s waypoints')
    physics=audit_mission_truth(directory/'truth.jsonl',mission)
    require(all(value==formal['mission_truth'][key] for key,value in physics.items() if key!='complete_physical_records')
            and physics['complete_physical_records']>=formal['mission_truth']['complete_physical_records'],
            'Recomputed independent physical windows differ')
    source_audit=check_sources(root,directory,report,formal,source_archive)
    require(len(mission['pauses'])==1 and mission['cancel_request'] is None,'Unexpected pause/cancel sequence')
    pause=mission['pauses'][0]
    for action in ('pause','resume'):
        request=launch[action+'_submission']['request']
        require(request==pause[action+'_request'] and request['run_id']==formal['run_id']
                and request['control_epoch']==task['control_epoch'],'MATLAB action identity differs')
        require(read(directory/('mission-action-'+request['action_token']+'.json'))==request,
                'Action receipt differs from retained public mailbox')
    require(pause['publications_before']==pause['publications_after'] and pause['wait_wall_s']>=6,
            'Task published during explicit pause or observation was too short')
    truth=rows(directory/'truth.jsonl')
    window=truth[pause['start_truth']['records']:pause['end_truth']['records']]
    require(len(window)>10 and min(-r['vehicle'][8] for r in window)>2.5,'Pause lacked independent airborne truth')
    public=rows(directory/'prometheus.jsonl')
    envelopes=[r['message'] for r in public if r.get('request_envelope')]
    require(envelopes==task['request_envelopes'] and all(a['request_id']<b['request_id']
            for a,b in zip(envelopes,envelopes[1:])),'Public request identity/history differs')
    events=[json.loads(r['message']['message']) for r in public if r.get('topic','').endswith('/text_info')]
    acks=[e for e in events if e.get('event')=='native_ack' and e.get('accepted')
          and e.get('control_epoch')==task['control_epoch']]
    for request in envelopes:
        matched=[e for e in events if e.get('request_id')==request['request_id']
                 and e.get('control_epoch')==task['control_epoch']]
        require(any(e.get('event')==('setup_completed' if 'setup' in request else 'command_accepted')
                    for e in matched),'Public command/setup was not accepted')
        if 'setup' in request or request['command']['agent_cmd']==3:
            require(any(e.get('request_id')==request['request_id'] for e in acks),
                    'Setup or landing lacks its recorded accepted native ACK')
    journals={phase:rows(root/(phase+'-requests.jsonl')) for phase in ('launch','reconnect')}
    writes=[r['method'] for r in journals['launch'] if r['method'] in ('config.save','preflight','start','cancel','mission.action')]
    require(writes==['config.save','preflight','start','mission.action','mission.action'],'Unexpected MATLAB writes')
    require(all(r['method'] in ('status','result','logs') for r in journals['reconnect']),'Reconnect sent a write')
    http=rows(root/'console/http-actions.jsonl')
    require(sum(r['method']=='POST' and r['path']=='/api/start' for r in http)==1
            and sum(r['method']=='POST' and r['path'].endswith('/mission-action') for r in http)==2,
            'HTTP wrote a repeated start/action')
    observed=[r for r in rows(root/'observations.jsonl') if r['observed_unix_s']>report['launch_exit_observed_unix_s']
              and r['job']['status']=='running' and (r['job'].get('live') or {}).get('freshness',{}).get('status')=='live'
              and r['job']['live']['state']['armed'] and r['job']['live']['state']['position'][2]>1]
    require(len(observed)>=2,'No real airborne observations after MATLAB exited')
    first,last=observed[0],observed[-1]
    for item in (first,last):
        current=item['job']['live']['raw']
        require(current['run_id']==formal['run_id'] and current['control_epoch']==task['control_epoch']
                and current['source_clock']=='fc_boot','Post-exit state crossed identity/clock')
        require(item['truth_observed'] in truth,'Post-exit physical observation not in raw trace')
    require(last['truth_observed']['time']>first['truth_observed']['time']
            and last['job']['live']['raw']['sequence']>first['job']['live']['raw']['sequence'],
            'Post-exit physical/native source froze')
    visual=None
    if report['view_requested']:
        view=read(next(job.glob('view-*/view.json')))
        actors=rows(Path(view['readback_path']))
        require(len(actors)>5 and all(r['packet']['run_id']==formal['run_id'] for r in actors),'Missing/foreign actual UE Actors')
        errors=[actor_errors(r['packet'],r['ack']) for r in actors]
        maximum={key:max(e[key] for e in errors) for key in ACTOR_LIMITS}
        require(all(maximum[key]<=limit for key,limit in ACTOR_LIMITS.items()),'UE Actor differed from authoritative packet')
        capture=live_captures(view,formal['run_id'])
        require(capture==report['ue_captures'] and capture,'Native captured frames changed')
        post=[r for r in observed if (r['job'].get('view') or {}).get('state')=='live'
              and r['job']['view'].get('latest_actor')]
        require(len(post)>=2,'UE did not remain live after MATLAB exit')
        lo,hi=[r['job']['view']['latest_actor']['packet']['sequence'] for r in (post[0],post[-1])]
        require(hi>lo and any(lo<=r['sequence']<=hi for r in capture),'No actual native frame in post-exit window')
        visual=dict(actor_packets=len(actors),max_actor_error=maximum,live_frames=len(capture),post_exit_sequence=[lo,hi])
    return dict(status='pass',stack=formal['stack'],run_id=formal['run_id'],control_epoch=task['control_epoch'],
        runtime_profile=formal['config'].get('runtime_profile','retained_baseline'),firmware_sha256=formal['fc_sha256'],
        physics=physics,public_native_acks=len(acks),public_requests=len(envelopes),
        streamed_position_request_ids=[r['request_id'] for r in envelopes if r.get('command',{}).get('agent_cmd')==4],
        post_exit_observations=len(observed),post_exit_physics_seconds=last['truth_observed']['time']-first['truth_observed']['time'],
        visual=visual,source_audit=source_audit,source_dependencies_checked=len(formal['runtime_sha256']),
        limitations=['Native ACKs are recorded public events; this audit adds no independent raw DDS observer.',
                     'Streamed position targets have public command acceptance and physical completion, not a per-target native ACK.',
                     'Normal MATLAB cancel is not exercised by these completed-mission cases.',
                     ('Independent profile selects the pinned autonomous-model/firmware builds; this audit is not a whole-flight loader trace or G6/Full claim.'
                      if formal['config'].get('runtime_profile')=='independent_quad_dds_v1' else
                      'Retained reference firmware; this is not a no-Gazebo or complete Full/G5 claim.'),
                     'Process exit assertions are contemporaneous records; current-host cleanup is recorded separately.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directories',nargs='+',type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--source-archive',type=Path,help='Verify retained source bytes; does not accept the current checkout')
    args=parser.parse_args()
    require(all(not args.output.resolve().is_relative_to(p.resolve()) for p in args.directories),'Audit output must be outside evidence')
    result=dict(status='failed',runs=[],audit_sha256=sha(__file__))
    try:
        result['runs']=[audit(path,source_archive=args.source_archive) for path in args.directories];result['status']='pass'
    except (OSError,ValueError,KeyError,TypeError,StopIteration,AssertionError) as error:result['error']=repr(error)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['status']=='pass' else 1)
