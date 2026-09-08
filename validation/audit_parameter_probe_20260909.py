from pathlib import Path
import json, hashlib, shutil, stat
ROOT=Path('/mnt/c/Users/PC/Documents/odid编译/wksim')
OUT=ROOT/'validation/parameter-probe-audit-20260909'
SOURCES=[ROOT/'validation/parameter-read-20260908/runs/parameter-read-arducopter-20260908-01']
SOURCES += [Path('/root/wksim-parameter-read-20260908')/n for n in ['parameter-read-arducopter-20260908-02','parameter-read-arducopter-20260908-03','parameter-read-px4-20260908-01']]
SOURCES += [Path('/root')/('wksim-parameter-write-'+s+'-20260908-01')/('parameter-write-'+f+'-20260908-01') for s,f in [('ap','arducopter'),('px4','px4')]]
OUT.mkdir(exist_ok=True)
manifest=[]
for src in SOURCES:
    dst=OUT/'runs'/src.name; dst.mkdir(parents=True,exist_ok=True)
    for p in src.iterdir():
        if p.suffix not in ('.json','.jsonl') or not stat.S_ISREG(p.lstat().st_mode): continue
        data=p.read_bytes(); target=dst/p.name
        if target.exists(): assert target.read_bytes()==data
        else: target.write_bytes(data)
        manifest.append({'source':str(p),'archive':str(target.relative_to(OUT)),'size':len(data),'sha256':hashlib.sha256(data).hexdigest()})
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

import math, subprocess, time
summaries=[]
for src in SOURCES:
    d=OUT/'runs'/src.name
    r=json.loads((d/'result.json').read_text()); p=json.loads(next(d.glob('parameter-*.json')).read_text()); ev=p['evidence']
    truth=[json.loads(x) for x in (d/'truth.jsonl').read_text().splitlines()]
    positions=[x['vehicle'][6:9] for x in truth]
    metrics={'records':len(truth),'max_height_m':max(-x[2] for x in positions),'min_waypoint_error_m':min(math.dist(x,[3,2,-3]) for x in positions),'final_height_m':-positions[-1][2],'final_time':truth[-1]['time']}
    assert p['restart_operations']==[]
    assert r['children_reaped'] and not r['cleanup_errors']
    assert all(c['returncode'] is not None for c in r['children'].values())
    for e in ev:
        if 'raw' in e:
            b=bytes.fromhex(e['raw']['hex']); assert len(b)==e['raw']['size'] and hashlib.sha256(b).hexdigest()==e['raw']['sha256']
        if e['kind']=='ground_authority':
            assert e['context']==p['context'] and e['context']['run_id']==r['run_id']
            assert not e['public_state']['armed'] and e['public_state']['odom_valid']
            assert abs(e['truth']['final_height_m'])<.3 and 0<=e['truth_age_s']<=2
            assert 0<=e['checked_at_monotonic']-e['observed_at_monotonic']<=2
            prefix=truth[:e['truth']['records']]
            assert prefix[-1]['time']==e['truth']['final_time'] and -prefix[-1]['vehicle'][8]==e['truth']['final_height_m']
    responses=[e for e in ev if e['kind']=='response']
    requests=[e for e in ev if e['kind'] in ('request','request_sent')]
    assert len(requests)==len(responses)
    assert all(a['monotonic']<q['monotonic'] for a,q in zip(responses,requests[1:]))
    for q,a in zip(requests,responses):
        assert q['monotonic']<a['monotonic']
        if r['stack']=='px4':
            assert a['peer']==['127.0.0.1',18591] and (a['source_system'],a['source_component'])==(22,1)
            assert a['message']['param_id']=='MPC_XY_CRUISE' and a['message']['param_type']==9
        else: assert a.get('service',p.get('service')) in ('/ap/get_parameters','/ap/set_parameters')
    if p['parameter_writes']:
        assert [q['phase'] for q in requests]==['read_original','write_trial','read_trial','restore_original','read_restored']
        assert p['parameter_writes']==2 and p['pending_restore'] is False and p['retry_count']==0
        values=[a['message']['param_value'] if r['stack']=='px4' else a['message']['values'][0]['double_value'] for a in responses if a['phase'].startswith('read_')]
        assert values==[p['original_value'],4.0,p['original_value']]
        assert p['trial_readback']==4.0 and p['restored_value']==p['original_value']
        assert ev[-3]['kind']=='clients_closed' and ev[-2]['kind']=='parameter_cycle_completed' and ev[-1]['kind']=='standard_task_completed'
    else: assert p['parameter_writes']==0 and p['parameter_write_operations']==[]
    if p.get('status')=='read_pass':
        assert len(responses)==1
        assert (responses[0]['message']['param_value'] if r['stack']=='px4' else responses[0]['message']['values'][0]['double_value'])==p['original_value']
    if r['status']=='pass':
        n=r['truth']['records']; pp=positions[:n]
        assert r['truth']=={'records':n,'max_height_m':max(-x[2] for x in pp),'min_waypoint_error_m':min(math.dist(x,[3,2,-3]) for x in pp),'final_height_m':-pp[-1][2],'final_time':truth[n-1]['time']}
        assert metrics['max_height_m']>=2.5 and metrics['min_waypoint_error_m']<=.5 and abs(metrics['final_height_m'])<.3
        assert not r['task']['final']['state']['armed'] and r['safe_landing'] and r['stop_kind']=='landed_stop'
    current_matches=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit(): continue
        try:
            argv=(proc/'cmdline').read_bytes().decode(errors='replace').split('\0'); ns=(proc/'ns/net').readlink().as_posix()
            if ns==r['network_namespace'] and any(argv==c['argv']+[''] for c in r['children'].values()): current_matches.append(proc.name)
        except (OSError,PermissionError): pass
    assert not current_matches
    summaries.append({'run_id':src.name,'result_status':r['status'],'probe_status':p['status'],'original_value':p.get('original_value'),'requests':len(requests),'responses':len(responses),'ground_checks':sum(e['kind']=='ground_authority' for e in ev),'truth_recomputed':metrics,'error':r.get('error'),'cleanup':{'recorded_children_reaped':True,'recorded_cleanup_errors':[],'exact_argv_and_recorded_net_namespace_matches_now':current_matches,'limitation':'historical PID/start-time identities unavailable; namespace inode may be reused; no global PID/port inference'},'recorded_sources':p['sources_sha256']})
    if src.name.endswith('arducopter-20260908-02'):
        commands=[x for x in r['task']['sent'] if 'command_id' in x]
        stamps=[x['header']['stamp']['sec']*10**9+x['header']['stamp']['nanosec'] for x in commands]
        assert stamps[-1]<stamps[-2] and 'out_of_order_command_stamp' in (d/'prometheus.jsonl').read_text()
        summaries[-1]['command_header_regression_ns']=stamps[-1]-stamps[-2]
old=subprocess.check_output(['git','show','1fdf273:Simulator/wksim_runtime/parameter_protocol.py'],cwd=ROOT)
assert hashlib.sha256(old).hexdigest()=='733f9d1a32d56e4d48ef320d200d1c3b21da1407de4bb3ff60df2d8fbc5225ea'
(OUT/'parameter_protocol-read-phase.py').write_bytes(old)
runtime=ROOT/'validation/parameter-write-20260908/runtime-before-storage.py'
assert hashlib.sha256(runtime.read_bytes()).hexdigest()=='615f6ab01604bb9141a460b38cab0a6d81b3dda891c01c4460c9d97b3a34b888'
(OUT/'runtime-before-storage.py').write_bytes(runtime.read_bytes())
source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'Simulator/wksim_runtime/runtime.py',ROOT/'Simulator/wksim_runtime/parameter_protocol.py']}
(OUT/'audit.json').write_text(json.dumps({'audited_unix':time.time(),'assertions':'pass','runs':summaries,'current_source_snapshot_only':source_hashes},indent=2)+'\n')
print(json.dumps([{'run':x['run_id'],'probe':x['probe_status'],'result':x['result_status'],'truth':x['truth_recomputed']} for x in summaries],indent=2))



