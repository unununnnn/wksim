"""Read-only formal P+V/mixed audit; reuse raw gates with actual formal facts.

The small context below aliases epoch/authority and keys actual task reports by
stack. It carries no experimental admission, fabricated history or rewritten
files. Task evidence remains in tasks/<id>/<stack>; CDR bytes remain original.
"""
import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
sys.path.insert(0,str(REPO/'tools'))
from audit_joint_flight import digest,lines,require
from audit_pv_trajectory import decode,rate_windows,stamp
from Simulator.wksim_runtime.joint_config import FIXED_TASKS,validate_joint_config
from Simulator.wksim_runtime.joint_trajectory import RECORDER,validate_initialized


def read(path):
    return json.loads(Path(path).read_text())


def formal_context(directory,result):
    """Validate the actual formal config, admission, task/go and source identities."""
    config=validate_joint_config(read(directory.parent.parent/'config.json'))
    require(result['run_id']==config['run_id'] and result['epoch']==directory.name
            and result['task_profile']==config['task'] and config['task'] in FIXED_TASKS
            and result['requested_rate']==config['requested_rate']==.5
            and result['task_dwell_seconds']==config['task_dwell_seconds']=={'hold':5,'waypoint':2},
            'Formal task/config/frozen timing identity differs')
    require(result['status']=='stopped' and not result.get('faults') and not result['cleanup_errors']
            and result['changed_sources']==[], 'Formal epoch contains a fault, changed source or unclean retirement')
    final=result['authority'];terminal=result['terminal_transition']
    require(final['epoch']==result['epoch'] and final['phase']=='stopped' and final['pending_tick'] is None
            and final['tick']>0 and final['tick']%4==0 and not final['fault']
            and terminal['action']=='stop' and terminal['phase']=='stopped' and terminal['tick']==final['tick']
            and type(terminal['issued_monotonic_ns']) is int, 'Formal terminal authority differs')
    admission=read(directory/'preflight.json')
    require(admission==result['preflight'] and admission['ok'] and not admission['reasons']
            and admission['children_created']==0 and admission['profile']['id']==config['runtime_profile']
            and set(FIXED_TASKS)<=set(admission['capabilities'])
            and admission['capabilities']==admission['profile']['capabilities'], 'Actual formal admission differs')
    for key,pin in admission['profile']['manifests'].items():
        require(digest(directory/(key+'-build.json'))==pin['sha256'], 'Admitted retained build differs: '+key)
    control=read(directory/'control-build.json')
    actual={p.relative_to(directory/'control-source').as_posix():digest(p)
            for p in (directory/'control-source').rglob('*') if p.is_file()}
    require(actual==control['python_sha256'] and control['package']==admission['control_package'],
            'Retained installed control source differs')
    prepared=read(directory/'mixed-source.json')
    require(digest(directory/'mixed-source.json')==admission['identities']['ap_mixed']['source_manifest_sha256']
            and prepared['candidate_root']==admission['configs']['arducopter']['ap_candidate'],
            'Retained native prebuild source seal differs')
    require(result['native_source_sha256']=={'ArduCopter/Log.cpp':digest(directory/'native-source/ArduCopter/Log.cpp')}
            and result['native_source_sha256']['ArduCopter/Log.cpp']==prepared['source']['files']['ArduCopter/Log.cpp']['sha256'],
            'Native GUIP decoder source is not bound to the admitted native source')
    mandatory={'Simulator/wksim_runtime/'+name for name in ('joint_runtime.py','joint_task.py','joint_trajectory.py',
        'joint_config.py','joint_profile.py','joint_evidence.py','task.py','runtime.py','joint_rate.py','scene_clock.py')}
    mandatory|={'tools/'+name for name in ('pv_trajectory_task.py','mixed_control_task.py','audit_joint_trajectory.py',
        'audit_pv_trajectory.py','audit_mixed_control.py','audit_joint_flight.py','audit_joint_rate.py')}
    require(mandatory<=result['source_sha256'].keys(), 'Missing executed formal/task/audit source')
    for name,sha in result['source_sha256'].items():
        path=directory/'source'/name
        require(path.resolve().is_relative_to((directory/'source').resolve()) and digest(path)==sha,
                'Retained executed source differs: '+name)
    task_children={}
    for name,child in result['children'].items():
        require(child['returncode'] is not None, 'Unretired formal child: '+name)
        if '-task-' in name:
            stack=name.split('-task-')[0]
            require(stack in ('arducopter','px4') and stack not in task_children and child['returncode']==0,
                    'Repeated, foreign or failed fixed task worker')
            task_children[stack]=child
    require(set(task_children)=={'arducopter','px4'} and len(result['tasks'])==2, 'Missing dual formal tasks')
    # Recorded cwd is an absolute runtime path; a retained run can be relocated.
    task_ids={Path(child['cwd']).parent.name for child in task_children.values()}
    require(len(task_ids)==1,'Task workers used different formal task groups')
    task_root=directory/'tasks'/task_ids.pop()
    require(task_root.is_dir() and set(p.name for p in (directory/'tasks').iterdir())=={task_root.name},
            'Unexpected formal task directory')
    tasks={};initial={}
    for stack,uid in (('arducopter',1),('px4',2)):
        report=read(task_root/stack/'result.json');settings=read(task_root/stack/'task-config.json')
        ready=read(task_root/stack/'ready.json')
        require(report==result['tasks'][stack+'-task-'+task_root.name] and report['stack']==stack
                and report['task_mode']=='initial' and report['task_profile']==config['task']
                and report['task_dwell_seconds']==config['task_dwell_seconds'], 'Formal worker result differs')
        require(settings['run_id']==config['run_id'] and settings['epoch']==result['epoch'] and settings['uav_id']==uid
                and settings['stack']==stack and settings['mode']=='initial' and settings['task_type']==config['task']
                and settings['control_package']==admission['control_package']
                and settings['task_dwell_seconds']==config['task_dwell_seconds'], 'Formal worker configuration differs')
        validate_initialized(read(task_root/stack/'initialized.json'),settings)
        require(ready==dict(version=1,run_id=config['run_id'],epoch=result['epoch'],uav_id=uid,
                control_epoch=report['task']['control_epoch'],request_high_water=0,token=settings['token']),
                'Initial formal task readiness differs')
        initial[stack]=ready;tasks[stack]=report
    require(read(task_root/'go.json')==dict(run_id=config['run_id'],epoch=result['epoch'],tasks=initial),
            'Explicit formal task go differs')
    starts=[action for action in result['action_results'] if action['action']=='start-task']
    require(len(starts)==1 and starts[0]['state']=='completed' and starts[0]['effect']=='new_tasks_started',
            'Missing explicit operator start-task completion')
    require(all(action['action'] in ('start-task','stop','cold-reset') for action in result['action_results']),
            'Unsupported fixed-task lifecycle action was accepted')
    request_path=directory.parent.parent/'actions'/f"{starts[0]['command_id']:020d}-{starts[0]['token']}.json"
    start_request=read(request_path)
    from Simulator.wksim_runtime.joint_actions import validate_request
    validate_request(start_request,result['run_id'],result['epoch'])
    require(start_request['action']=='start-task' and start_request['command_id']==starts[0]['command_id']
            and start_request['token']==starts[0]['token'], 'Start action file differs')
    initialized=result['initialization']
    require(initialized['physical_tick']==0 and initialized['task_execution_requires_explicit_go']
            and all(row['tick']==0 and row['state'] is None for row in initialized['models']['models'].values()),
            'Formal transport initialization advanced physical time')
    from audit_mixed_control import control_profiles
    control_profiles(result,require_pv=True)
    for label in ('ready','stopping'):
        images=result['runtime_images'][label]
        require(set(images)=={'arducopter-fc','px4-fc','arducopter-model','px4-model'},'Missing actual native/model images')
        for name,image in images.items():
            child=result['children'][name]
            require(image.get('state')!='exited' and all(image['identity'][key]==child['identity'][key]
                    for key in ('pid','pgid','start_ticks')) and not image['forbidden_libraries']
                    and digest(directory/image['maps_file'])==image['maps_sha256'], 'Runtime image identity differs')
            maps=(directory/image['maps_file']).read_text()
            require(any(line.split()[-1]==image['executable'] and 'x' in line.split()[1] for line in maps.splitlines())
                    and not any(token in maps.lower() for token in ('libgz-','libgazebo','libignition','matlab','coptersim.exe','(deleted)')),
                    'Runtime mapping lacks admitted executable or contains forbidden image')
            if name.endswith('-fc'):
                pin=admission['identities']['ap' if name.startswith('arducopter') else 'px4']
                require(image['executable']==child['argv'][0]==pin['path'] and image['executable_sha256']==pin['sha256'],
                        'Actual firmware differs from formal admission')
            else:
                require(admission['model_library'] in maps,'Admitted model missing from native maps')
    # These aliases are actual fields, for shared task/physics/rate functions only.
    return dict(run_id=result['run_id'],scene_epoch=result['epoch'],final_authority=final,tasks=tasks,
        clock_publications=result['clock_publications'],terminal_transition=terminal),task_root,start_request


def verify_epoch(directory,result):
    directory=Path(directory)
    context,task_root,start=formal_context(directory,result)
    packages=result['preflight']['identities']['message_packages']
    from Simulator.wksim_runtime.joint_profile import _overlay
    for name,pin in packages.items():
        _overlay(name,pin['prefix'])
    raw=decode(directory,context,message_packages=packages,wall_limit=result['wall_seconds'])
    # Use real authority at action completion, and real captured request clocks.
    start_tick=next(action['authority']['tick'] for action in result['action_results'] if action['action']=='start-task')
    for stack,uid in (('arducopter',1),('px4',2)):
        for suffix in ('setup','command'):
            for row,envelope in raw[f'/uav{uid}/prometheus/v2/'+suffix]:
                require(stamp(envelope[suffix])>=start_tick*1_000_000
                        and envelope['run_id']==start['run_id'],'Public request preceded explicit formal start-task')
    from audit_joint_product import lifecycle
    lifecycle_proof=lifecycle(directory,result['epoch'],result['authority']['tick'],result['clock_publications'],result['run_id'])
    require(lifecycle_proof['clock_republications']==0,'Fixed trajectory performed an unsupported clock transition')
    if result['task_profile']==FIXED_TASKS[0]:
        from audit_pv_trajectory import task_evidence,native_targets,physical
        tasks,phases,requests=task_evidence(directory,context,raw,recorder_name=RECORDER,task_root=task_root)
        native=native_targets(raw,requests);logs=None
    else:
        from audit_mixed_control import task_evidence,native_targets,native_logs,physical
        tasks,phases,requests,references=task_evidence(directory,context,raw,recorder_name=RECORDER,task_root=task_root)
        native=native_targets(raw,requests,references,tasks)
        logs=native_logs(directory,tasks,native,raw)
    physics=physical(directory,context,tasks,phases,wire_name='wire.jsonl')
    rates=rate_windows(directory,context,wire_name='wire.jsonl')
    return dict(status='pass',task_profile=result['task_profile'],run_id=result['run_id'],epoch=result['epoch'],
        raw_dds_channels={name:len(rows) for name,rows in raw.items()},native_targets=native,native_guided_submode=logs,
        lifecycle=lifecycle_proof,**physics,rate_segments=rates)


def audit(directory):
    directory=Path(directory)
    run=read(directory/'result.json')
    require(run['status']=='pass' and len(run['epochs'])==1,'Expected one completed formal fixed-task epoch')
    item=run['epochs'][0];root=directory/'epochs'/item['epoch'];result=read(root/'result.json')
    require(result==item['result'] and not item['remaining_group_members'] and result['flight_completed'],
            'Manager result/owned cleanup differs')
    require(all(child['identity']['pgid']==item['process_identity'] for child in result['children'].values()),
            'Child escaped the owned formal epoch process group')
    proof=verify_epoch(root,result)
    require(proof==result['physical_task_proof'],'Independent formal replay differs from runtime proof')
    return dict(status='pass',run_id=run['run_id'],task_profile=result['task_profile'],proof=proof,
        result_sha256=digest(directory/'result.json'),audit_source_sha256=digest(__file__),
        evidence_sha256={p.relative_to(directory).as_posix():digest(p) for p in sorted(directory.rglob('*')) if p.is_file()},
        limitations=['Fixed nominal home/origin and environment only; native timeout/fence/reset/avoidance require separate proof.',
            'Acceleration is retained but inactive; yaw-rate and trajectory pause/resume/recovery are unsupported.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    require(not args.output.resolve().is_relative_to(args.directory.resolve()),'Audit output must be outside evidence')
    try: report=audit(args.directory)
    except (OSError,ValueError,KeyError,TypeError,ImportError,AssertionError,IndexError,StopIteration,OverflowError) as error:
        report=dict(status='failed',error=repr(error),audit_source_sha256=digest(__file__))
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(status=report['status'],error=report.get('error'))))
    raise SystemExit(0 if report['status']=='pass' else 1)
