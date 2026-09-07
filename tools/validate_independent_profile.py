"""Run one formal independent candidate, retaining owned process images and truth."""
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
from Simulator.wksim_runtime.config import load_config
from Simulator.wksim_runtime.evidence import write_json,json_identity,group_members,host_boot_id
from Simulator.wksim_runtime.runtime import launch_spec,digest


def run(config_path,output):
    config=load_config(config_path)
    if config.get('runtime_profile')!='independent_quad_dds_v1':
        raise ValueError('Explicit independent candidate required')
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    runs=Path(tempfile.mkdtemp(prefix='wksim-independent-',dir='/root'))
    directory=runs/config['run_id']
    write_json(output/'config.json',config)
    plan=launch_spec(config,directory,Path(config['model_library']))
    command=['bash',str(REPO/'tools/run-wksim.sh'),str(config_path.resolve()),'--output-root',str(runs)]
    record=dict(command=command,host_boot_id=host_boot_id(),started_unix_s=time.time(),images={},
                driver_sha256=digest(__file__),config_sha256=digest(config_path))
    child=None
    try:
        with (output/'service.log').open('w') as log:
            child=subprocess.Popen(command,cwd=REPO,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            record['manager']=json_identity(child.pid)
            deadline=time.monotonic()+360
            while child.poll() is None:
                if time.monotonic()>deadline:raise TimeoutError('Independent product entry exceeded 360s')
                members=Path(f'/proc/{child.pid}/task/{child.pid}/children')
                try:pids=[int(value) for value in members.read_text().split()]
                except FileNotFoundError:pids=[]
                for pid in (child.pid,*pids):
                    identity=json_identity(pid)
                    if identity is None:continue
                    args=identity['argv'];role=None
                    if pid==child.pid:role='supervisor'
                    elif args and Path(args[0]).resolve()==Path(plan['fc'][0]).resolve():role='fc'
                    elif args and Path(args[0]).resolve()==Path(plan['agent'][0]).resolve():role='agent'
                    elif any(value.startswith('Simulator.wksim_core.') for value in args):role='physics'
                    elif 'prometheus_control.node' in args:role='control'
                    if role is None or role in record['images']:continue
                    try:
                        proc=Path('/proc')/str(pid);maps=(proc/'maps').read_text()
                        executable=str((proc/'exe').resolve(strict=True))
                        if role=='physics' and 'libwksim_model.so' not in maps:continue
                        if role in ('supervisor','control') and 'librcl.so' not in maps:continue
                        if json_identity(pid)!=identity:continue
                        path=output/(role+'-maps.txt');path.write_text(maps)
                        record['images'][role]=dict(identity=identity,executable=executable,
                            executable_sha256=digest(executable),maps_sha256=digest(path),
                            observed_unix_s=time.time(),namespaces={name:os.readlink(proc/'ns'/name) for name in ('net','ipc','mnt')})
                    except FileNotFoundError:continue
                time.sleep(.05)
            record['returncode']=child.returncode
        result=json.loads((directory/'result.json').read_text())
        record['result']=result
        record['remaining_groups']={name:group_members(row['pgid']) for name,row in result['children'].items()}
        record['changed_runtime_sources']=[name for name,sha in result['runtime_sha256'].items() if digest(REPO/name)!=sha]
        record['forbidden_mappings']={role:[line for line in (output/(role+'-maps.txt')).read_text().splitlines()
            if any(name in line.lower() for name in ('libgazebo','libgz-','libmwmcr','libmatlab','coptersim.exe'))]
            for role in record['images']}
        assert record['returncode']==0 and result['status']=='pass' and result['safe_landing'] and result['children_reaped']
        assert not any(record['remaining_groups'].values()) and not record['changed_runtime_sources']
        assert set(record['images'])=={'supervisor','physics','fc','agent','control'}
        assert not any(record['forbidden_mappings'].values())
        assert all(row['identity']['pid'] in (child.pid,*[r['pid'] for r in result['children'].values()]) for row in record['images'].values())
        record['status']='pass'
    except BaseException as error:
        record.update(status='failed',error=repr(error))
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:child.wait(timeout=25)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
            record['aborted_manager_returncode']=child.returncode
        if directory.exists():shutil.copytree(directory,output/'run')
        record['finished_unix_s']=time.time()
        write_json(output/'report.json',record)
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config',type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();result=run(args.config,args.output)
    print(json.dumps({key:result.get(key) for key in ('status','error','remaining_groups','forbidden_mappings')}))
    raise SystemExit(0 if result['status']=='pass' else 1)
