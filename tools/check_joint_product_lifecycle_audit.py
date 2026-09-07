"""Corrupt small copies of real retained provenance; never alter a flight package."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import tempfile

from audit_joint_product_lifecycle import retained_identity
from audit_joint_flight import digest
from Simulator.wksim_runtime.evidence import write_json


def run(evidence):
    result=json.loads((evidence/'run/result.json').read_text())
    item=result['epochs'][0];original=evidence/'run/epochs'/item['epoch']
    findings=[]
    for case,expected in (('source','Retained executed source differs'),('maps','Forbidden runtime image'),
                          ('binary','Executed firmware differs')):
        with tempfile.TemporaryDirectory(prefix='wksim-product-audit-negative-') as temporary:
            directory=Path(temporary)
            for path in original.iterdir():
                if path.is_file() and (path.name in ('result.json','preflight.json') or path.name.endswith('-maps.txt')):
                    shutil.copy2(path,directory/path.name)
            shutil.copytree(original/'source',directory/'source')
            changed=copy.deepcopy(item);record=changed['result']
            if case=='source':
                name=next(iter(record['source_sha256']))
                (directory/'source'/name).write_bytes(b'changed retained source\n')
            elif case=='maps':
                image=record['runtime_images']['ready']['px4-fc'];path=directory/image['maps_file']
                path.write_text(path.read_text()+'00000000 /untrusted/libgz-sim8.so\n')
                image['maps_sha256']=digest(path)
            else:
                record['runtime_images']['ready']['px4-fc']['executable_sha256']='0'*64
            write_json(directory/'result.json',record)
            try: retained_identity(directory,changed,result['run_id'])
            except ValueError as error:
                if expected not in str(error): raise
                findings.append(dict(case=case,rejected=str(error)))
            else: raise AssertionError('Corrupt '+case+' accepted')
    return dict(status='pass',source=str(evidence),negative_cases=findings)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=run(args.directory)
    write_json(args.output,result);print(json.dumps(result,indent=2))
