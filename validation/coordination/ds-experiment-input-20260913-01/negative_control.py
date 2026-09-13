"""Negative control for experiment input identity binding (evidence only).

Replays the pre-change two-read pattern from `HEAD:Simulator/wksim_runtime/experiment_bundle.py`
plus the pre-change `tools/run_experiment.py` body against a mutated input file, then replays
the delivered single-read path on the same fixture.

Pure Python standard library; no firmware, model, SITL, ROS, UE, MATLAB or build action runs,
and no real process is started (the legacy exec decision is counted, not executed).

Run from the repository root:
    python validation/coordination/ds-experiment-input-20260913-01/negative_control.py
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

REPO=Path(__file__).resolve().parents[3]
EXAMPLES=REPO/'Simulator/wksim_runtime/examples/experiments'
NEW_INTENT={'schema_version':1,'id':'rewritten-intent','kind':'body_rate_comparison',
            'vehicle_model':'quad_x','firmware':'quad_rate_candidate','algorithms':['pid']}


def load_head_bundle(directory):
    """Import the pre-change parser straight from the delivered HEAD blob."""
    source=subprocess.run(['git','show','HEAD:Simulator/wksim_runtime/experiment_bundle.py'],
                          cwd=REPO,check=True,capture_output=True).stdout
    path=directory/'head_experiment_bundle.py';path.write_bytes(source)
    spec=importlib.util.spec_from_file_location('head_experiment_bundle',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def head_runner_source():
    return subprocess.run(['git','show','HEAD:tools/run_experiment.py'],
                          cwd=REPO,check=True,capture_output=True).stdout.decode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    sys.path.insert(0,str(REPO))
    from Simulator.wksim_runtime.experiment_bundle import (load_document_with_digest,resolve,
                                                           verify_document_identity)
    with tempfile.TemporaryDirectory() as name:
        directory=Path(name)
        experiment=directory/'rate-control.json';deployment=directory/'local-deployment.json'
        original=(EXAMPLES/'rate-control.json').read_bytes()
        experiment.write_bytes(original)
        deployment.write_bytes((EXAMPLES/'local-deployment.json').read_bytes())
        old=load_head_bundle(directory)

        # Pre-change flow: parse (read 1), resolve, then hash the file again (read 2).
        intent=old.load_document(experiment);deployment_document=old.load_document(deployment)
        plan=old.resolve(intent,deployment_document)
        experiment.write_bytes(json.dumps(NEW_INTENT).encode('utf-8'))
        plan['inputs']={str(p):digest(p.read_bytes()) for p in (experiment,deployment)}
        runner=head_runner_source()
        old_exec_reached='os.execvp' in runner and 'verify_document_identity' not in runner
        rewritten=json.loads(experiment.read_bytes())
        print('pre-change recorded digest == digest of the rewritten file:',
              plan['inputs'][str(experiment)]==digest(experiment.read_bytes()))
        print('pre-change plan semantics came from the original file:',
              plan['intent']['id']==json.loads(original)['id'])
        print('pre-change recorded digest == digest of the parsed bytes:',
              plan['inputs'][str(experiment)]==digest(original))
        print('pre-change identity therefore describes a document with id',
              repr(rewritten['id']),'while the plan executes id',repr(plan['intent']['id']))
        print('pre-change execute would start a process:',old_exec_reached)

        intent['algorithms'].clear()
        print('pre-change caller mutation rewrote the resolved plan:',
              plan['intent']['algorithms']!=['native','pid','lqr','mpc'])

        # Delivered flow: one read for semantics and digest, then a fail-closed guard.
        experiment.write_bytes(original)
        document,recorded=load_document_with_digest(experiment)
        delivered=resolve(document,load_document_with_digest(deployment)[0])
        experiment.write_bytes(json.dumps(NEW_INTENT).encode('utf-8'))
        print('delivered recorded digest == digest of the parsed bytes:',
              recorded==digest(original))
        print('delivered recorded digest == digest of the rewritten file:',
              recorded==digest(experiment.read_bytes()))
        try:
            verify_document_identity(experiment,recorded)
            print('delivered execute would start a process: True')
        except RuntimeError as error:
            print('delivered execute would start a process: False')
            print('delivered fail-closed reason:',error)
        document['algorithms'].clear()
        print('delivered caller mutation rewrote the resolved plan:',
              delivered['intent']['algorithms']!=['native','pid','lqr','mpc'])

        # Alias boundary: one file given as both documents.
        experiment.write_bytes(original)
        first,first_digest=load_document_with_digest(experiment)
        experiment.write_bytes(json.dumps(NEW_INTENT).encode('utf-8'))
        second,second_digest=load_document_with_digest(experiment)
        alias_inputs={str(p):value for p,value in ((experiment,first_digest),(experiment,second_digest))}
        print('unchecked one-file alias has a single inputs key:',list(alias_inputs)==[str(experiment)])
        print('unchecked one-file alias records only the second hash:',
              alias_inputs[str(experiment)]==second_digest)
        print('unchecked alias semantics come from the first read while the digest is the second:',
              first['id']==json.loads(original)['id'] and alias_inputs[str(experiment)]!=first_digest)
        from tools.run_experiment import require_distinct_documents
        for label,deployment_path in (('identical path',experiment),
                                      ('dot alias',Path(str(directory)+'/./rate-control.json')),
                                      ('dotdot detour',directory/'nested'/'..'/'rate-control.json')):
            try:
                require_distinct_documents(experiment,deployment_path)
                print('delivered rejects',label,'pair: False')
            except ValueError as error:
                print('delivered rejects',label,'pair: True ->',error)


if __name__=='__main__':main()
