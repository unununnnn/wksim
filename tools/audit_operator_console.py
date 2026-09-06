"""Offline service/UE evidence and current owned-process audit; never UI proof."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from Simulator.wksim_console.records import read_result
from Simulator.wksim_console.workspace import wsl_path
from Simulator.ue55.bridge import actor_errors
from Simulator.wksim_console.visual import ACTOR_LIMITS
from tools.validate_operator_http import audit_http_lifecycle


def sha(path):
    value=hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):
            value.update(chunk)
    return value.hexdigest()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('--case',action='append',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--verify-current-sources',action='store_true',
                        help='Fail if retained console/runtime/Prometheus source hashes differ from this checkout')
    args=parser.parse_args(argv)
    root=args.root.resolve(); repo=Path(__file__).resolve().parents[1]
    report=dict(scope='HTTP service and actual UE evidence; browser/UI gate NOT passed',status='failed',runs=[])
    groups=set(); pids=set(); sockets=set(); run_ids=set()
    try:
        for name in args.case:
            if not re.fullmatch('[A-Za-z0-9_-]+',name):
                raise ValueError('Case must be a direct directory name')
            case_path=root/name/'acceptance.json'
            case=json.loads(case_path.read_text(encoding='utf-8'))
            assert case['status']=='pass' and all(case['checks'].values()),name
            scenario=case['case']
            assert scenario in ('mission','cancel','pause-resume','pause-cancel')
            lifecycle=scenario in ('pause-resume','pause-cancel')
            directory=Path(case['directory'])
            record=read_result(directory/'result.json'); result=record['values']
            assert record['sha256']==case['result_sha256']
            assert result['status']==('cancelled' if scenario in ('cancel','pause-cancel') else 'pass')
            assert result['safe_landing'] is True and result['children_reaped'] is True
            mission=result['task']['mission']
            assert len(mission['waypoints'])==(1 if scenario=='cancel' else 3)
            if scenario in ('mission','pause-resume'):
                assert all(point['status']=='completed' for point in mission['waypoints'])
                assert result['mission_truth']['ok'] is True
            else:
                assert mission['cancel_request']['mission_id']==mission['mission_id']
            lifecycle_evidence=None
            if lifecycle:
                lifecycle_evidence=audit_http_lifecycle(result,directory,scenario,
                                                       case['pause_request'],case['resume_request'])
                assert lifecycle_evidence==case['lifecycle_audit']
                for action in ('pause','resume'):
                    request=case[action+'_request']
                    assert json.loads((directory/('mission-action-'+request['action_token']+'.json')).read_text())==request
                    event=case[action+'_confirmed']
                    assert any(row==event for row in mission['progress']), 'HTTP feedback must be original mission evidence'
                requests=[json.loads(line) for line in (root/'workspace/http-actions.jsonl').read_text(encoding='utf-8').splitlines()]
                actions=[row for row in requests if row['path']=='/api/runs/'+case['job_id']+'/mission-action']
                assert [row['http_status'] for row in actions]==[200,400,200], 'Expected pause, rejected old offer, resume only'
                for row, action in zip((actions[0],actions[2]),('pause','resume')):
                    assert row['submitted'] is True and row['request']=={k:v for k,v in case[action+'_request'].items() if k!='version'}
                if scenario=='pause-cancel':
                    assert case['cancel']['request']==mission['cancel_request']
            if args.verify_current_sources:
                assert all(sha(repo/path)==digest for path,digest in result['runtime_sha256'].items())
                assert all(sha(repo/'ros2/src/prometheus_control/prometheus_control'/path)==digest
                           for path,digest in result['product_sha256'].items())
            job=root/'workspace/jobs'/case['job_id']
            observations=[json.loads(line) for line in (root/name/'observations.jsonl').read_text(encoding='utf-8').splitlines()]
            live=[row for row in observations if (row['freshness'] or {}).get('status')=='live']
            assert len({row['sequence'] for row in live})>=5
            assert all(row['run_id']==result['run_id'] for row in observations)
            views=[]
            if case['view_requested']:
                for view_file in sorted(job.glob('view-*/view.json')):
                    view=json.loads(view_file.read_text(encoding='utf-8'))
                    actor_path=Path(view['readback_path'])
                    rows=[json.loads(line) for line in actor_path.read_text().splitlines()]
                    assert len(rows)>=5
                    measured=[actor_errors(row['packet'],row['ack']) for row in rows]
                    maximum={key:max(row[key] for row in measured) for key in ACTOR_LIMITS}
                    assert all(maximum[key]<=limit for key,limit in ACTOR_LIMITS.items())
                    assert all(row['packet']['run_id']==result['run_id'] for row in rows)
                    frames=[]
                    for line in (actor_path.parent/'ue.log').read_text(errors='replace').splitlines():
                        match=re.search(r'WKSIM_CAPTURE .*?(frame-\d+\.png) sequence=(-?\d+) sim=([\d.]+) stale=(\d)',line)
                        if match and int(match[2])>=0 and match[4]=='0':
                            frame=Path(view['frames_directory'])/match[1]
                            assert frame.is_file()
                            frames.append(dict(path=str(frame),sha256=sha(frame),sequence=int(match[2]),sim_time_s=float(match[3])))
                    assert frames,'No actual rendered LIVE frame: '+str(view_file)
                    views.append(dict(path=str(view_file),sha256=sha(view_file),packets=len(rows),
                                      first_sequence=rows[0]['packet']['sequence'],last_sequence=rows[-1]['packet']['sequence'],
                                      max_error=maximum,frames=frames))
                assert len(views)==2
                views.sort(key=lambda view:view['first_sequence'])
                assert views[1]['first_sequence']>views[0]['last_sequence']
            report['runs'].append(dict(case=name,case_sha256=sha(case_path),job_id=case['job_id'],
                run_id=result['run_id'],stack=result['stack'],config_revision=case['saved']['revision'],
                status=result['status'],result_sha256=record['sha256'],directory=str(directory),
                fc_commit=result['fc_commit'],fc_sha256=result['fc_sha256'],mission_id=mission['mission_id'],
                control_epoch=result['task']['control_epoch'],live_observations=len(live),views=views,
                lifecycle=lifecycle_evidence,verified_current_sources=args.verify_current_sources))
        if args.verify_current_sources:
            servers=[]
            for path in (root/'workspace').glob('server-*.json'):
                manifest=json.loads(path.read_text(encoding='utf-8'))
                assert all(sha(repo/source)==digest for source,digest in manifest['source_sha256'].items())
                servers.append(dict(path=str(path),sha256=sha(path),pid=manifest['pid'],
                                    source_files=len(manifest['source_sha256'])))
            assert servers
            report['servers']=servers
        # Include every attempt, including intentionally retained integration failures.
        for job_path in (root/'workspace/jobs').glob('*/job.json'):
            job=json.loads(job_path.read_text(encoding='utf-8'))
            if 'pid' in job:pids.add(job['pid'])
            if job['kind']=='flight':
                result=read_result(Path(job['directory'])/'result.json')['values']
                assert result['children_reaped'] is True
                groups.update(child['pgid'] for child in result['children'].values())
                run_ids.add(result['run_id']); sockets.add(result['config']['display_socket'])
            for view_file in job_path.parent.glob('view-*/view.json'):
                view=json.loads(view_file.read_text())
                pids.update(view['pids'].values())
                if view.get('relay'):pids.add(view['relay']['pid'])
        before=json.loads((repo/'validation/product-third-wave-20260906/cleanup.json').read_text())['original_before']
        linux_code='''import json,os,sys
from pathlib import Path
from tools.validate_product_isolation import identity,group_members
v=json.loads(sys.argv[1]); print(json.dumps(dict(original_after=identity(v['before']['pid']),
remaining_groups=group_members(set(v['groups'])),remaining_sockets=[p for p in v['sockets'] if Path(p).exists()],
remaining_named=[int(p.name) for p in Path('/proc').glob('[0-9]*') if int(p.name)!=os.getpid() and (p/'cmdline').exists() and any(r in (p/'cmdline').read_bytes().decode(errors='replace') for r in v['run_ids'])])))'''
        checked=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--cd',wsl_path(repo),'--exec','python3','-c',linux_code,
            json.dumps(dict(before=before,groups=sorted(groups),sockets=sorted(sockets),run_ids=sorted(run_ids)))],capture_output=True,text=True,encoding='utf-8',timeout=20,check=True)
        linux=json.loads(checked.stdout)
        assert all(type(pid) is int and pid>1 for pid in pids)
        command='@('+','.join(map(str,sorted(pids)))+') | ForEach-Object { Get-CimInstance Win32_Process -Filter "ProcessId = $_" } | Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress'
        windows=subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,text=True,encoding='utf-8',timeout=20,check=True)
        remaining=json.loads(windows.stdout) if windows.stdout.strip() else []
        report['cleanup']=dict(original_before=before,linux=linux,windows_remaining=remaining,
                               checked_process_groups=sorted(groups),checked_windows_pids=sorted(pids))
        assert before==linux['original_after'] and not linux['remaining_groups'] and not linux['remaining_sockets'] and not linux['remaining_named'] and not remaining
        report['status']='pass'
    except Exception as error:
        report['error']=type(error).__name__+': '+str(error)
    report['auditor_sha256']=sha(Path(__file__))
    with args.output.open('x',encoding='utf-8') as output:
        json.dump(report,output,ensure_ascii=False,allow_nan=False,indent=2);output.write('\n')
    print(json.dumps(dict(status=report['status'],error=report.get('error'),runs=len(report['runs']),output=str(args.output)),ensure_ascii=False))
    return 0 if report['status']=='pass' else 1


if __name__=='__main__':
    raise SystemExit(main())
