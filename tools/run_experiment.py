"""Resolve or execute a portable experiment with one explicit deployment file."""
import argparse
import json
import os
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_runtime.experiment_bundle import (load_document_with_digest,resolve,
                                                      verify_document_identity)


def canonical_document_path(path):
    """Absolute normalized path used only to detect aliases of one single file."""
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def require_distinct_documents(experiment_path,deployment_path):
    """Experiment intent and local deployment are two independent documents.

    Rejecting an alias of one file (`./`, `..`, links, case variants) keeps the two
    single reads from overwriting each other's digest or mixing their semantics.
    """
    same=canonical_document_path(experiment_path)==canonical_document_path(deployment_path)
    if not same:
        try:
            same=os.path.samefile(experiment_path,deployment_path)
        except OSError:
            same=False
    if same:
        raise ValueError('Experiment and deployment must be two distinct documents')


def resolve_plan(experiment_path,deployment_path):
    """Read each input once so the parsed semantics and the recorded digest share one read.

    Returns the resolved plan plus the `(path,digest)` pairs that execution must re-verify.
    """
    require_distinct_documents(experiment_path,deployment_path)
    documents=[]
    inputs={}
    for path in (experiment_path,deployment_path):
        document,digest=load_document_with_digest(path)
        documents.append(document)
        inputs[str(path)]=digest
    plan=resolve(*documents)
    plan['inputs']=inputs
    return plan,tuple((path,inputs[str(path)]) for path in (experiment_path,deployment_path))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experiment',type=Path)
    parser.add_argument('--deployment',type=Path,required=True)
    parser.add_argument('--resolved-output',type=Path)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args(argv)
    plan,identities=resolve_plan(args.experiment,args.deployment)
    if args.resolved_output:
        with args.resolved_output.open('x',encoding='utf-8') as stream:json.dump(plan,stream,indent=2)
    print(json.dumps(plan),flush=True)
    if not args.execute:return
    for path,digest in identities:verify_document_identity(path,digest)
    if sys.platform!='linux':raise RuntimeError('Execute inside the selected WSL Ubuntu environment')
    exec_argv=[sys.executable,*plan['python_argv']]
    if plan['intent']['kind']=='ground_waypoints':
        exec_argv=['unshare','--net','--ipc','--mount','--propagation','private','bash','-c',
                   'set -euo pipefail; ip link set lo up; mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm; exec "$@"',
                   'wksim-ground',*exec_argv]
    os.chdir(REPO)
    os.execvp(exec_argv[0],exec_argv)


if __name__=='__main__':main()
