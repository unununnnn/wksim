"""Save bounded read-only checks. No FC/model/ROS flight process is launched."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def main():
    out = HERE / sys.argv[1]
    out.mkdir(exist_ok=False)
    results = []
    def run(argv, name, expected=0):
        done = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=180)
        (out / (name+'.stdout')).write_bytes(done.stdout)
        (out / (name+'.stderr')).write_bytes(done.stderr)
        results.append(dict(argv=argv, expected_returncode=expected, returncode=done.returncode,
            stdout=name+'.stdout', stderr=name+'.stderr'))
        if done.returncode != expected:
            raise RuntimeError(name + ': unexpected exit ' + str(done.returncode))
        return done
    try:
        run(['uname','-a'], 'kernel')
        run(['lscpu','-J'], 'cpu')
        run(['ps','-eo','pid,ppid,psr,cls,rtprio,ni,comm'], 'processes')
        run(['taskset','-c','0-7',sys.executable,'-B',str(HERE/'run-one.py'),'1','--check'], 'candidate-check')
        run(['taskset','-c','0-19',sys.executable,'-B',str(HERE/'run-one.py'),'1','--check'], 'wrong-affinity', 1)
        run(['taskset','-c','0-7','env','WKSIM_JOINT_CPU_TIMING=1',sys.executable,'-B',str(HERE/'run-one.py'),'1','--check'], 'instrumentation-refused', 1)
        command = ['taskset','-c','0-7','bash','tools/run-wksim.sh',
            'validation/20-rate-candidate-profile/experiment-1.json','--output-root','/root/wksim-rate61-preflight-e2561e27','--preflight']
        done = run(command,'preflight')
        admission = json.loads(done.stdout)
        assert admission['ok'] and admission['children_created'] == 0, admission
        (out/'preflight.json').write_text(json.dumps(admission,indent=2)+'\n')
        run([sys.executable,'-B','-m','unittest','validation.test_joint_rate','-v'], 'timer-boundaries')
        run([sys.executable,'-B','tools/replay_joint_rate_timing.py',
            'validation/joint-rate-flow-p9koy63e/run/epochs/a3e59a3220f5421aa95bddd44b5fd6c1/rate.jsonl',
            '--output',str(out/'red-replay.json')], 'red-replay',1)
        spec = importlib.util.spec_from_file_location('rate61',HERE/'run-one.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module,'sha',return_value='0'*64):
            try:
                module.check(1)
            except ValueError as error:
                assert 'Frozen source/config changed' in str(error)
                results.append(dict(check='changed_source_rejected',error=str(error),passed=True))
            else:
                raise AssertionError('Changed source accepted')
        paths = ['Simulator/wksim_runtime/joint_rate.py','Simulator/wksim_core/joint.py','Simulator/wksim_core/worker.py']
        identities = {}
        epoch = ROOT/'validation/joint-rate-flow-p9koy63e/run/epochs/a3e59a3220f5421aa95bddd44b5fd6c1'
        for name in paths:
            current = ROOT/name
            historical = epoch/'source'/name
            identities[name] = dict(current=hashlib.sha256(current.read_bytes()).hexdigest(),
                historical=hashlib.sha256(historical.read_bytes()).hexdigest(),same_bytes=current.read_bytes()==historical.read_bytes())
            saved = out/'historical-source'/name
            saved.parent.mkdir(parents=True,exist_ok=True)
            saved.write_bytes(historical.read_bytes())
        (out/'historical-source-identity.json').write_text(json.dumps(identities,indent=2)+'\n')
        verdict = 'checks_passed_not_performance'
    except BaseException as error:
        results.append(dict(error=repr(error)))
        verdict = 'failed'
        raise
    finally:
        value=dict(status=verdict,performance_pass=False,argv=sys.argv,checks=results,
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            scheduler_rt_runtime_us=Path('/proc/sys/kernel/sched_rt_runtime_us').read_text().strip(),
            scheduler_rt_period_us=Path('/proc/sys/kernel/sched_rt_period_us').read_text().strip(),
            self_affinity=sorted(os.sched_getaffinity(0)))
        (out/'checks.json').write_text(json.dumps(value,indent=2)+'\n')
        print(json.dumps(dict(status=verdict,output=str(out),performance_pass=False)))


if __name__ == '__main__':
    main()
