"""Real owned SITL/model delay through the formal service; no flight publishers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_runtime.evidence import write_json,json_identity,group_members,process_identity,host_boot_id


def run(target,exit_process=False):
    evidence=Path(tempfile.mkdtemp(prefix='joint-input-stall-',dir=REPO/'validation'))
    output=Path(tempfile.mkdtemp(prefix='wksim-input-stall-',dir='/root'))
    directory=output/'joint-scene-example'
    command=['bash',str(REPO/'tools/run-wksim.sh'),str(REPO/'Simulator/wksim_runtime/examples/joint-scene.json'),
             '--output-root',str(output)]
    print(json.dumps(dict(evidence=str(evidence),output=str(output))),flush=True)
    driver=Path(__file__).read_bytes()
    (evidence/'driver.py').write_bytes(driver)
    record=dict(status='failed',target=target,exit_process=exit_process,command=command,actions=[],host_boot_id=host_boot_id(),
                driver_source_sha256=hashlib.sha256(driver).hexdigest(),
                invocation=[sys.executable,'-B',str(Path(__file__).resolve()),target]+(['--exit-process'] if exit_process else []))
    manager=None;stopped=None
    def status():
        path=directory/'status.json'
        return json.loads(path.read_text()) if path.is_file() else None
    def wait(label,predicate,seconds=180):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=status()
            if value and predicate(value): return value
            if manager.poll() is not None: raise RuntimeError(label+': formal service exited')
            time.sleep(.02)
        raise TimeoutError(label)
    def action(name,epoch,seconds=20):
        argv=[sys.executable,'-B','-m','Simulator.wksim_runtime.joint_actions',str(directory),name,'--epoch',epoch]
        submitted=json.loads(subprocess.check_output(argv,cwd=REPO,text=True))
        response=Path(submitted['result_file']);end=time.monotonic()+seconds
        while time.monotonic()<end:
            if response.is_file():
                value=json.loads(response.read_text())
                if value['state'] in ('failed','rejected'): raise RuntimeError(str(value))
                if value['state']=='completed':
                    record['actions'].append(dict(command=argv,submitted=submitted,response=value));return value
            time.sleep(.02)
        raise TimeoutError(name+' did not complete')
    def model_tail(epoch_dir):
        values={}
        for stack in ('arducopter','px4'):
            with (epoch_dir/(stack+'-truth.jsonl')).open('rb') as stream:
                stream.seek(0,2);stream.seek(max(0,stream.tell()-65536))
                values[stack]=json.loads(stream.read().splitlines()[-1])
        return values
    with (evidence/'service.log').open('w') as log:
        try:
            manager=subprocess.Popen(command,cwd=REPO,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            record['manager']=json_identity(manager.pid)
            ready=wait('ground readiness',lambda s:'start-task' in s['allowed_actions'])
            epoch=ready['epoch'];epoch_dir=Path(ready['epoch_dir'])
            action('start-task',epoch)
            flying=wait('settled real dual airborne task',lambda s:'pause' in s['allowed_actions']
                        and all(value['state']['position'][2]>2.5 for value in s['participants'].values()))
            children=json.loads((epoch_dir/'children.json').read_text())
            victim=children[target];stopped=json_identity(victim['identity']['pid'])
            assert all(stopped[key]==victim['identity'][key] for key in ('pid','pgid','start_ticks'))
            executable=(Path('/proc')/str(stopped['pid'])/'exe').resolve(strict=True)
            assert executable==Path(victim['argv'][0]).resolve(strict=True)
            record['injection']=dict(identity=stopped,executable=str(executable),status=flying,monotonic_s=time.monotonic())
            os.kill(stopped['pid'],signal.SIGKILL if exit_process else signal.SIGSTOP)
            stop_deadline=time.monotonic()+1
            while time.monotonic()<stop_deadline:
                kernel=process_identity(stopped['pid'])
                if (exit_process and (kernel is None or kernel['state']=='Z')
                        or not exit_process and kernel is not None and kernel['state']=='T'):break
                time.sleep(.002)
            if exit_process:
                assert kernel is None or kernel['state']=='Z'
                record['injection']['kernel_exited']=None if kernel is None else {key:kernel[key] for key in ('pid','pgid','start_ticks','state')}
                stopped=None
            else:
                assert kernel is not None and kernel['state']=='T'
                record['injection']['kernel_stopped']={key:kernel[key] for key in ('pid','pgid','start_ticks','state')}
            fault=wait('latched fault with explicit operator actions',lambda s:s['phase']=='faulted'
                       and {'stop','cold-reset'}<=set(s['allowed_actions']),8)
            record['fault']=fault
            before=model_tail(epoch_dir)
            if not exit_process:
                current=json_identity(stopped['pid'])
                assert current and all(current[key]==stopped[key] for key in ('pid','pgid','start_ticks'))
                record['continued_monotonic_s']=time.monotonic()
                os.kill(stopped['pid'],signal.SIGCONT);stopped=None
            time.sleep(1)
            after=model_tail(epoch_dir)
            current_status=status()
            assert current_status['phase']=='faulted'
            if exit_process:
                assert all(current_status['authority'][key]==fault['authority'][key]
                           for key in ('tick','time_ns','last_barrier_tick','last_input_tick','pending_tick','recoverable'))
            else:
                assert current_status['authority']==fault['authority']
            if target.endswith('-fc') or exit_process: assert before==after
            record['late_process_resumed']=dict(before=before,after=after,status=status())
            if target.endswith('-fc') and not exit_process:
                wait('explicit recover available',lambda s:'recover' in s['allowed_actions'],10)
                action('recover',epoch,15)
                wait('new task offer after fresh native recovery',lambda s:'start-recovery-task' in s['allowed_actions'])
                action('start-recovery-task',epoch)
                wait('new task landed',lambda s:s['task_state']=='completed')
            else:
                assert 'recover' not in status()['allowed_actions']
            action('cold-reset',epoch,180)
            fresh=wait('new ready epoch',lambda s:s['epoch']!=epoch and 'start-task' in s['allowed_actions'])
            assert fresh['task_state']=='idle'
            action('stop',fresh['epoch'])
            manager.wait(timeout=20)
            final=json.loads((directory/'result.json').read_text())
            assert all(not row['remaining_group_members'] for row in final['epochs'])
            record.update(status='pass',result=final)
        except BaseException as error:
            record.update(error=repr(error),last_status=status())
        finally:
            if stopped is not None:
                current=json_identity(stopped['pid'])
                if current and all(current[key]==stopped[key] for key in ('pid','pgid','start_ticks')):
                    os.kill(stopped['pid'],signal.SIGCONT)
            if manager is not None and manager.poll() is None:
                os.killpg(manager.pid,signal.SIGTERM)
                try:manager.wait(timeout=15)
                except subprocess.TimeoutExpired:os.killpg(manager.pid,signal.SIGKILL);manager.wait(timeout=5)
            record['returncode']=manager.returncode if manager is not None else None
            if directory.exists():shutil.copytree(directory,evidence/'run')
            record['remaining_manager_group']=group_members(manager.pid) if manager is not None else []
            write_json(evidence/'flow.json',record)
    print(json.dumps(dict(status=record['status'],error=record.get('error'),evidence=str(evidence))))
    return 0 if record['status']=='pass' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target',choices=('arducopter-fc','px4-fc','arducopter-model','px4-model'))
    parser.add_argument('--exit-process',action='store_true',help='Kill the verified owned process to validate cold reset after exit')
    args=parser.parse_args()
    raise SystemExit(run(args.target,args.exit_process))
