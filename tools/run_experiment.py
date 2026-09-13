"""Resolve or execute a portable experiment with one explicit deployment file."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_runtime.experiment_bundle import load_document,resolve


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experiment',type=Path)
    parser.add_argument('--deployment',type=Path,required=True)
    parser.add_argument('--resolved-output',type=Path)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    plan=resolve(load_document(args.experiment),load_document(args.deployment))
    plan['inputs']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.experiment,args.deployment)}
    if args.resolved_output:
        with args.resolved_output.open('x',encoding='utf-8') as stream:json.dump(plan,stream,indent=2)
    print(json.dumps(plan),flush=True)
    if not args.execute:return
    if sys.platform!='linux':raise RuntimeError('Execute inside the selected WSL Ubuntu environment')
    argv=[sys.executable,*plan['python_argv']]
    if plan['intent']['kind']=='ground_waypoints':
        argv=['unshare','--net','--ipc','--mount','--propagation','private','bash','-c',
              'set -euo pipefail; ip link set lo up; mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm; exec "$@"',
              'wksim-ground',*argv]
    os.chdir(REPO)
    os.execvp(argv[0],argv)


if __name__=='__main__':main()
