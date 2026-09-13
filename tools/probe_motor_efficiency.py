"""Native-model bench, no ROS/FC/UE: actual ODE4 eta, reset and random-state evidence."""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_core.motor_efficiency_model import EfficiencyModel
from Simulator.wksim_core.motor_efficiency_event import EfficiencyEvent,make_plan,publish_plan,canonical
from Simulator.wksim_core.model import Model


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(library,case,output):
    if output.exists(): raise ValueError('Use a fresh native bench output directory')
    output.mkdir(parents=True)
    model=Model(library) if case=='reference' else EfficiencyModel(library)
    summary=dict(case=case,library=str(library),library_sha256=digest(library),pid=os.getpid(),
        run_id='efficiency-'+uuid.uuid4().hex,control_epoch=uuid.uuid4().hex,instance_id=1,
        proc_stat=Path('/proc/self/stat').read_text(),bench_only=True,flown=False,steps=0,status='failed',
        input16=[.55]*4+[0.]*12,source_sha256={name:digest(REPO/name) for name in (
            'tools/probe_motor_efficiency.py','Simulator/wksim_core/motor_efficiency_model.py',
            'Simulator/wksim_core/motor_efficiency_event.py','Simulator/wksim_core/motor_efficiency_native.cpp',
            'Simulator/wksim_core/motor_efficiency_native.h')})
    event=None
    if case!='reference':
        summary['initial_eta']=model.efficiency()
        summary['initial_random_state']=model.initial_random_state
        if case!='normal':
            manifest=model.manifest
            identity=dict(run_id=summary['run_id'],instance_id=1,control_epoch=summary['control_epoch'],
                model_identity='sha256:'+model.library_sha256,library_sha256=model.library_sha256,
                config_sha256=hashlib.sha256(canonical(summary['input16'])).hexdigest(),
                protocol_sha256=digest(REPO/'docs/plan/44-motor-efficiency-contract.md'),
                original_source_sha256=manifest['files_sha256']['original.cpp'],
                parameterized_source_sha256=manifest['files_sha256']['Exp1_MinModelTemp.cpp'],
                wrapper_sha256=manifest['files_sha256']['motor_efficiency_native.cpp'])
            # Bench origin zero validates interval mechanics only. Flight origin
            # remains gated by the contract's real six-second stable hover.
            plan=make_plan(identity,0)
            publish_plan(output/'event.json',plan)
            event=EfficiencyEvent(plan,identity,loaded_tick=0,path=output/'event.json')
            summary['plan']=plan
    try:
        with (output/'raw.jsonl').open('x') as raw:
            for tick in range(4000):
                if case=='tamper' and tick==2500:
                    (output/'event.json').write_bytes(canonical(dict(event.plan,seed=1)))
                try:
                    result=(model.step(summary['input16']) if event is None else
                        event.step(model,summary['input16'],tick=tick,
                                   revoke=(case=='revoke-pending' and tick==1000 or case=='revoke-active' and tick==2500)))
                except ValueError as error:
                    if case!='tamper' or tick!=2500: raise
                    summary.update(expected_rejection=str(error),restored_eta=model.efficiency(),
                                   event_state=event.state,native_tick=model.library.wk_model_tick(model.handle))
                    try:
                        event.step(model,summary['input16'],tick=tick)
                    except ValueError:
                        summary['failure_latched']=True
                    else: raise AssertionError('Failed event resumed')
                    break
                row=dict(interval_tick=tick,output120=result)
                if case!='reference':
                    row.update(eta=model.efficiency(),stages=model.stages,random_state=model.random_state(),
                               state=event.state if event else 'baseline')
                raw.write(json.dumps(row,allow_nan=False)+'\n')
                summary['steps']+=1
        if case!='reference':
            summary['final_eta']=model.efficiency()
            summary['final_random_state']=model.random_state()
            # Native invalid writes must not change a coefficient or time.
            before=model.efficiency()
            for motor,eta in ((1,.97),(0,float('nan')),(0,.5),(-1,1.)):
                if model.library.wk_model_set_efficiency(model.handle,motor,eta)!=1:
                    raise AssertionError('Invalid native coefficient write accepted')
                if model.efficiency()!=before: raise AssertionError('Invalid write changed native eta')
            summary['invalid_native_writes_rejected']=True
        summary['status']='observed'
    finally:
        model.close()
        if case!='reference':
            summary['same_process_recreate_rejected']=not bool(model.library.wk_model_create())
        summary['raw_sha256']=digest(output/'raw.jsonl')
        (output/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(dict(status=summary['status'],case=case,steps=summary['steps'],output=str(output))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--case',choices=('reference','normal','event','revoke-pending','revoke-active','tamper'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    run(args.library,args.case,args.output)
