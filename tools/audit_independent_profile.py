"""Read-only independent mission admission/command/truth/image evidence audit."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_runtime.mission_evidence import audit_mission_truth
from Simulator.wksim_runtime.mission_plan import resolve_waypoint,validate_mission
from Simulator.wksim_runtime.evidence import json_value


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value,message):
    if not value:raise ValueError(message)


def check_sources(run, wrapper, directory, source_archive):
    expected = dict(run['runtime_sha256'])
    expected['tools/validate_independent_profile.py'] = wrapper['driver_sha256']
    if source_archive is None:
        require(all(sha(REPO/name)==digest for name,digest in expected.items()), 'Executed runtime source differs')
        return dict(mode='current-checkout', current_checkout_accepted=True)
    archive = Path(source_archive).resolve()
    manifest = read(archive/'manifest.json')
    require(manifest['mode']=='retained-source-audit', 'Not a retained source archive')
    entry = manifest['runs'][run['run_id']]
    require(entry['report_sha256']==sha(directory/'report.json') and
            entry['formal_result_sha256']==sha(directory/'run/result.json'), 'Retained evidence identity differs')
    require(set(entry['sources'])==set(expected), 'Retained source coverage differs')
    for name,digest in expected.items():
        item=entry['sources'][name]; path=(archive/item['archive_path']).resolve()
        require(path.is_relative_to(archive) and path.is_file(), 'Retained source escapes archive')
        require(item['sha256']==digest and sha(path)==digest, 'Retained source bytes differ: '+name)
    return dict(mode='retained-source-audit', current_checkout_accepted=False,
                manifest_sha256=sha(archive/'manifest.json'), sources_checked=len(expected))


def audit(directory, source_archive=None):
    directory=Path(directory).resolve();wrapper=read(directory/'report.json');run=read(directory/'run/result.json')
    require(wrapper['status']=='pass' and wrapper['result']==json_value(run) and wrapper['returncode']==0,'Wrapper/result did not pass')
    require(run['status']=='pass' and run['safe_landing'] and run['children_reaped'] and not run['cleanup_errors'],
            'Mission did not finish and retire')
    require(not any(wrapper['remaining_groups'].values()),'Recorded owned groups remain')
    require(run['config']==read(directory/'config.json') and run['config']['runtime_profile']=='independent_quad_dds_v1',
            'Selected configuration differs')
    source_audit=check_sources(run,wrapper,directory,source_archive)
    task=run['task'];mission=task['mission'];points=mission['waypoints']
    require(task['run_id']==run['run_id'] and task['protocol']=='session_v1' and mission['state']=='completed'
            and not mission['pauses'] and mission['cancel_request'] is None,'Unexpected task identity/lifecycle')
    plan=validate_mission(run['config']['mission'])
    require(mission['plan']==plan and len(points)==len(plan['waypoints'])==3,'Three-waypoint plan differs')
    envelopes=task['request_envelopes']
    require([r['request_id'] for r in envelopes]==list(range(1,len(envelopes)+1)),'Request IDs were repeated or skipped')
    for request in envelopes:
        require(request['version']==1 and request['run_id']==run['run_id'] and request['control_epoch']==task['control_epoch'],
                'Request crossed a run/control epoch')
    by_id={r['request_id']:r for r in envelopes}
    for original,point in zip(plan['waypoints'],points):
        require(point['input']==original and point['status']=='completed','Waypoint input/completion changed')
        expected=resolve_waypoint(original,point['anchor']['position'],point['anchor']['yaw'])
        require(expected['position_enu_m']==point['target_enu_m'] and expected['yaw_enu_rad']==point['yaw_enu_rad'],
                'Body/ENU target was relabelled')
        command=by_id[point['request_id']]['command']
        require(command['agent_cmd']==4 and command['move_mode']==(0 if original['frame']=='enu' else 3)
                and command['command_id']==point['command_id']
                and command['position_ref']==original['position_m']
                and command['yaw_ref']==original['yaw_rad'],'Original public waypoint command differs')
    events=task['events'];log=[json.loads(line) for line in (directory/'run/prometheus.jsonl').read_text().splitlines()]
    # Task.send records the Python message before CDR serialization. Scalar
    # float32 fields retain Python's original value at this logging seam.
    recorded_requests=[r['message'] for r in log if r.get('request_envelope') is True
                       and r.get('published') in ('SetupRequest','CommandRequest')]
    require(recorded_requests==envelopes,'Task envelopes differ from original public log')
    native=[e for e in events if e.get('event')=='native_ack']
    require(native and all(e['accepted'] and e['run_id']==run['run_id'] and e['control_epoch']==task['control_epoch']
                          and e['request_id'] in by_id for e in native),'Missing/rejected native ACK')
    require(all(any(e.get('event')=='command_accepted' and e.get('request_id')==p['request_id'] for e in events) for p in points),
            'Waypoint lacked public acceptance')
    physical=audit_mission_truth(directory/'run/truth.jsonl',mission)
    recorded=run['mission_truth']
    # Runtime evaluates the mission windows before retiring physics. The final
    # trace also retains the trailing ground records produced during retirement.
    require(physical['complete_physical_records']>=recorded['complete_physical_records']>0,
            'Final truth lost records present during mission evaluation')
    require({k:v for k,v in physical.items() if k!='complete_physical_records'}==
            {k:v for k,v in recorded.items() if k!='complete_physical_records'},
            'Independent physical window recomputation differs')
    images=wrapper['images'];require(set(images)=={'supervisor','physics','fc','agent','control'},'Missing live process images')
    for role,image in images.items():
        path=directory/(role+'-maps.txt');require(sha(path)==image['maps_sha256'],'Process mapping evidence changed')
        require(image['namespaces']['net']==run['network_namespace'],'Process was outside the admitted namespace')
        maps=path.read_text()
        require(not any(token in maps.lower() for token in ('libgz-','libgazebo','libignition','libmwmcr','libmatlab','coptersim.exe')),
                'Forbidden core runtime mapping')
        if role!='supervisor':require(image['identity']['pid']==run['children'][role]['pid'],'Process identity differs')
    require(images['fc']['executable_sha256']==run['fc_sha256']==run['preflight']['identities']['firmware']['sha256'],
            'Actual FC image differs from admitted build')
    require(run['config']['model_library'] in (directory/'physics-maps.txt').read_text(),'Admitted model was not loaded')
    return dict(status='pass',run_id=run['run_id'],stack=run['stack'],control_epoch=task['control_epoch'],
        result_sha256=sha(directory/'run/result.json'),wrapper_sha256=sha(directory/'report.json'),
        firmware_sha256=run['fc_sha256'],model_sha256=run['model_build']['library_sha256'],
        product_sha256=run['product_sha256'],physical=physical,public_requests=len(envelopes),native_acks=len(native),
        source_audit=source_audit,
        scope='Three-waypoint independent public mission under the identified source; process mappings are contemporaneous snapshots',
        limitations=['No G6 dynamics equivalence, hardware, takeover, loss recovery, MATLAB or UE acceptance in this case.',
                     'Position streams report public acceptance and physical completion, not a per-setpoint native ACK.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directories',nargs='+',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--source-archive',type=Path)
    args=parser.parse_args()
    require(all(not args.output.resolve().is_relative_to(p.resolve()) for p in args.directories),'Audit output must be outside evidence')
    result=dict(status='failed',audit_sha256=sha(__file__),runs=[])
    try:result['runs']=[audit(path,args.source_archive) for path in args.directories];result['status']='pass'
    except (OSError,ValueError,KeyError,TypeError,AssertionError) as error:result['error']=repr(error)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result));raise SystemExit(0 if result['status']=='pass' else 1)
