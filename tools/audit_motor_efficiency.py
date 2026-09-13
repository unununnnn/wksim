"""Independent equations and cross-process comparison of raw native efficiency benches."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct


def require(value,reason):
    if not value: raise ValueError(reason)


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(root):
    result=json.loads((root/'result.json').read_text())
    require(result['status']=='observed' and result['bench_only'] and not result['flown'], 'Native bench did not complete')
    require(digest(root/'raw.jsonl')==result['raw_sha256'],'Raw bench hash differs')
    require(result['input16']==[.55]*4+[0.]*12,'PWM input was changed instead of aerodynamic efficiency')
    rows=[json.loads(line) for line in (root/'raw.jsonl').read_text().splitlines()]
    require(len(rows)==result['steps']==(2500 if result['case']=='tamper' else 4000),'Native bench tick count differs')
    for i,row in enumerate(rows):
        require(type(row['interval_tick']) is int and row['interval_tick']==i and len(row['output120'])==120,'Missing/duplicate native tick')
        require(all(type(v) in (int,float) and math.isfinite(v) for v in row['output120']),'Nonfinite native output')
        require(abs(row['output120'][2]-(i+1)*.001)<1e-10,'Native output time differs')
    return result,rows


def binary_outputs(rows):
    return b''.join(struct.pack('<120d',*r['output120']) for r in rows)


def audit(reference,normal,event,repeat,pending,active,tamper):
    paths=(reference,normal,event,repeat,pending,active,tamper)
    runs=[read(Path(p)) for p in paths]
    require([r['case'] for r,_ in runs]==['reference','normal','event','event','revoke-pending','revoke-active','tamper'],
            'Select exact independent native bench roles')
    require(len({r['pid'] for r,_ in runs})==7 and len({r['control_epoch'] for r,_ in runs})==7,
            'Native reset/repetition did not use new processes and epochs')
    ref,base,fault,again,pre,mid,bad=(rows for _,rows in runs)
    require(binary_outputs(ref)==binary_outputs(base),'Eta=1 changed original model outputs')
    require(binary_outputs(fault)==binary_outputs(again),'Same source/random state/input event did not reproduce')
    require(binary_outputs(base[:2000])==binary_outputs(fault[:2000]),'Event affected physics before start')
    require(binary_outputs(base)==binary_outputs(pre),'Pending revoke changed baseline dynamics')
    require(binary_outputs(fault)!=binary_outputs(base),'Efficiency only changed records, not native physics')
    initial=runs[1][0]['initial_random_state']
    require(len(initial)==17 and all(type(v) is int and 0<v<2147483647 for v in initial),'Missing initial native random states')
    changed_steps=0
    for result,rows in runs[1:]:
        case=result['case']
        require(result['initial_random_state']==initial and result['initial_eta']==[1.]*4,'Cold native state leaked')
        require(result['final_eta']==[1.]*4 and result['same_process_recreate_rejected']
                and result['invalid_native_writes_rejected'],'Native restoration/lifetime/argument guard failed')
        for tick,row in enumerate(rows):
            eta=.97 if case in ('event','revoke-active','tamper') and 2000<=tick<(2500 if case=='revoke-active' else 3000) else 1.
            require(row['eta']==[eta,1.,1.,1.],'Wrong motor/eta/timing')
            require(row['random_state']==base[tick]['random_state'],'Event changed random draws')
            require(row['output120'][16:20]==base[tick]['output120'][16:20],'Event changed motor RPM dynamics')
            stages=row['stages']
            require(len(stages)==16,'Missing native ODE4 substages')
            for index,s in enumerate(stages):
                require(len(s)==10 and all(type(v) in (int,float) and math.isfinite(v) for v in s),'Invalid native stage')
                t,major,motor,factor,omega,thrust0,torque0,thrust,torque,spin=s
                substage=index//4; rotor=index%4
                expected_time=tick*.001+(0.,.0005,.0005,.001)[substage]
                expected_eta=eta if rotor==0 else 1.
                require(motor==rotor and major==(1 if substage==0 else 0)
                        and abs(t-expected_time)<1e-10 and factor==expected_eta,'ODE4 stage/timing/eta differs')
                require(spin==(-1 if rotor<2 else 1),'Rotor mapping changed')
                require(abs(thrust0-1.681e-5*omega*omega)<1e-12
                        and abs(torque0-2.783e-7*omega*omega)<1e-12,'Unscaled force coefficients differ')
                require(abs(thrust-expected_eta*thrust0)<1e-12
                        and abs(torque+expected_eta*torque0*spin)<1e-12,'Actual force/torque do not apply one eta')
            if case=='event' and eta==.97: changed_steps+=1
        if case=='tamper':
            require(result['event_state']=='failed' and result['failure_latched'] and result['native_tick']==2500
                    and result['restored_eta']==[1.]*4,'Mutated plan was not latched before native advance')
    require(changed_steps==2000,'Each repeated event must affect exactly 1000 intervals')
    return dict(status='pass',scope='native efficiency mechanics only; no flight/recovery-budget/G6 claim',
        eta1_original_binary64_equal=True,repeated_event_binary64_equal=True,changed_intervals_per_event=1000,
        native_rng_initial_state=initial,bench_runs=7,
        position_peak_delta_m=max(abs(a-b) for left,right in zip(base,fault)
            for a,b in zip(left['output120'][6:9],right['output120'][6:9])),
        velocity_peak_delta_mps=max(abs(a-b) for left,right in zip(base,fault)
            for a,b in zip(left['output120'][3:6],right['output120'][3:6])),
        audit_sha256=digest(__file__),sources={str(p):digest(Path(p)/'result.json') for p in paths})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','normal','event','repeat','pending','active','tamper','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    require(not args.output.exists(),'Use a fresh audit output')
    try:
        result=audit(args.reference,args.normal,args.event,args.repeat,args.pending,args.active,args.tamper)
    except Exception as error:
        result=dict(status='failed',error=repr(error),audit_sha256=digest(__file__))
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    raise SystemExit(0 if result['status']=='pass' else 1)
