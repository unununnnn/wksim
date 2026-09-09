"""Offline source-sealed UDE runtime check; no FC/model/ROS nodes."""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from Simulator.wksim_control.position_pid import PIDState
from Simulator.wksim_runtime.pid_task import PIDLoop, UDE_CONFIG_PATH, load_config, reference
from tools import audit_ude_flight as audit, audit_pid_flight as shared


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args(); args.output.mkdir(parents=False, exist_ok=False)
    names=['Simulator/wksim_control/position_pid.py','Simulator/wksim_control/position_ude.py',
        'Simulator/wksim_runtime/pid_task.py','Simulator/wksim_runtime/pid-flight-v1.json',
        'Simulator/wksim_runtime/ude-flight-v1.json','tools/run_pid_flight.py','tools/pid_physics.py',
        'tools/audit_pid_flight.py','tools/audit_ude_flight.py','validation/test_ude_runtime.py',
        'validation/test_position_pid.py','validation/test_position_ude.py',
        'validation/test_pid_flight.py','validation/test_pid_flight_audit.py',
        'docs/plan/36-ude-runtime-contract.md', str(Path(__file__).relative_to(REPO).as_posix())]
    before={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in names}
    result=dict(scope='offline synthetic runtime/equations only; no native flight or installed preflight',
        source_sha256=before, protocol_sha256=audit.PROTOCOL, command=[sys.executable,*sys.argv],
        physical_budgets_changed=False, native_processes_started=False, status='failed')
    try:
        config=load_config(UDE_CONFIG_PATH); samples=0; maximum=0.
        with (args.output/'equations.jsonl').open('x') as out:
            for stack,hover in [('px4',.53),('arducopter',.32)]:
                loop=PIDLoop(config,stack,hover);loop.reset('takeover',1.)
                integral=[0.]*3
                for i in range(1,601):
                    state=PIDState((2+.4*math.sin(i/17),3+.4*math.cos(i/11),3+.6*math.sin(i/13)),
                        (.1,-.2,.3),tuple(shared.wire.q_from_euler(.1,-.12,.3)))
                    desired=reference(config,'circle' if i%5==0 else 'point',i*.02)
                    row=loop.update(1+i*.02,state,desired,active=True)
                    expected,thrust=audit.recompute(config,asdict(state),asdict(desired),row['dt_s'],integral,hover)
                    errors=[]
                    for key,value in expected.items():
                        if key=='controller': assert row['output'][key]==value;continue
                        assert shared.near(row['output'][key],value)
                        errors.extend(abs(a-b) for a,b in zip(row['output'][key],value)) if isinstance(value,list) else errors.append(abs(row['output'][key]-value))
                    assert shared.near(row['normalized_collective'],thrust)
                    errors.append(abs(row['normalized_collective']-thrust));maximum=max(maximum,*errors)
                    out.write(json.dumps(dict(stack=stack,synthetic_hover=hover,sample=i,actual=row,
                        expected=expected,expected_collective=thrust,max_error=max(errors)),allow_nan=False)+'\n')
                    integral=expected['integral'];samples+=1
        result.update(equation_samples=samples,maximum_absolute_error=maximum,absolute_tolerance=1e-10)
        commands=[['-m','unittest','validation.test_position_pid','validation.test_position_ude',
                   'validation.test_pid_flight','validation.test_pid_flight_audit','validation.test_ude_runtime','-v'],
                  ['tools/run_pid_flight.py','--help'],['tools/audit_ude_flight.py','--help']]
        result['checks']=[]
        for i,command in enumerate(commands):
            argv=[sys.executable,'-B',*command]
            done=subprocess.run(argv,cwd=REPO,capture_output=True,text=True,timeout=60)
            (args.output/f'check-{i}.stdout.txt').write_text(done.stdout,encoding='utf-8')
            (args.output/f'check-{i}.stderr.txt').write_text(done.stderr,encoding='utf-8')
            result['checks'].append(dict(argv=argv,returncode=done.returncode))
            assert done.returncode==0, str(argv)
        result['source_unchanged']=all(hashlib.sha256((REPO/name).read_bytes()).hexdigest()==sha for name,sha in before.items())
        assert result['source_unchanged']
        result['status']='offline_checks_pass'
    except Exception as error:
        result['failure']=dict(type=type(error).__name__,message=str(error))
        raise
    finally:
        (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        artifacts={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.output.iterdir() if p.is_file()}
        (args.output/'artifact-sha256.json').write_text(json.dumps(artifacts,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
