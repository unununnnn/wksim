"""Corruption checks against retained real death evidence; no simulator or mocks."""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
import tempfile

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
import audit_joint_retirement as audit


def rejected(operation, text):
    try: operation()
    except ValueError as error:
        if text not in str(error):raise
        return str(error)
    raise AssertionError('Corrupt retained evidence was accepted')


def check(evidence, output):
    flow=audit.read(evidence/'flow.json');item=flow['result']['epochs'][0]
    directory=evidence/'run/epochs'/item['epoch']
    result=audit.death_identity(directory,item,flow['result']['run_id'],flow['target'])
    fault,incomplete=audit.freeze_boundary(flow,result,directory)
    timeline,_=audit.retirement_timeline(audit.ProductTimeline(directory),dict(final_authority=result['authority'],
        scene_epoch=result['epoch'],clock_publications=result['clock_publications']),incomplete)
    corrupt=copy.deepcopy(flow)
    corrupt['late_process_resumed']['status']['authority']['tick']+=1
    physical_error=rejected(lambda:audit.freeze_boundary(corrupt,result,directory),'status resumed or advanced authority')
    output.mkdir(parents=True,exist_ok=True)
    # Real immutable retained files are linked; only result.json is separately
    # written. Temporary directory is verified under our named audit directory.
    temporary=tempfile.TemporaryDirectory(prefix='corrupt-identity-',dir=output)
    temp=Path(temporary.name).resolve()
    assert temp.is_relative_to(output.resolve()) and temp!=output.resolve()
    try:
        for path in directory.rglob('*'):
            relative=path.relative_to(directory)
            if relative==Path('result.json'):continue
            if relative.parts[0]!='source' and path.name!='preflight.json' and not path.name.endswith('-maps.txt'):continue
            target=temp/relative
            if path.is_dir():target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                os.link(path,target)
        changed=copy.deepcopy(item)
        other=next(name for name in sorted(audit.RUNTIME_NAMES) if name!=flow['target'])
        changed['result']['children'][other]['returncode']=-9
        audit.write_json(temp/'result.json',changed['result'])
        identity_error=rejected(lambda:audit.death_identity(temp,changed,flow['result']['run_id'],flow['target']),
                                'victim/normal exit identity differs')
    finally:temporary.cleanup()
    report=dict(status='pass',scope='Real retained identity and physics/wire/clock boundary checks plus two corruptions; full ROS DDS audit is separate',
        evidence=str(evidence),target=flow['target'],committed_tick=timeline['total_ticks'],
        baseline_raw_boundary='pass',corruptions=[dict(change='late authority tick +1',rejection=physical_error),
        dict(change='second runtime process returncode -9',rejection=identity_error)],
        source_sha256=audit.digest(Path(__file__)),audit_sha256=audit.digest(Path(audit.__file__)))
    audit.write_json(output/(flow['target']+'-negative-tests.json'),report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directories',nargs='+',type=Path)
    parser.add_argument('--output',type=Path,default=REPO/'validation/retirement-audit-20260907')
    args=parser.parse_args()
    print(json.dumps([check(path,args.output) for path in args.directories],indent=2))
