import json,subprocess,hashlib
from pathlib import Path
root=Path('.').resolve()
cases=[Path('validation/joint-stale-20260908')/n for n in ('arducopter-run1','arducopter-run2','px4-run1')]
cases += [Path(f'validation/depth-live-20260908-run{n}') for n in range(1,6)]
identities=[]
summary=[]
for case in cases:
    result=case/'run/result.json'
    if not result.exists(): continue
    data=json.loads(result.read_text())
    count=0
    for epoch in data.get('epochs',[]):
        children=case/'run/epochs'/epoch['epoch']/'children.json'
        for child in json.loads(children.read_text()).values():
            identity=child.get('identity')
            if identity:
                identities.append(dict(pid=identity['pid'],start_ticks=identity['start_ticks'],host_boot_id=data['host_boot_id']))
                count+=1
        assert not epoch['remaining_group_members']
    summary.append(dict(case=str(case),status=data['status'],owned_children=count))
for case in (Path('validation/gcs-bridge-20260908')/n for n in ('live-px4-run1','live-px4-run2','live-px4-run3','live-px4-run4','live-arducopter-run1','live-arducopter-run2')):
    data=json.loads((case/'report.json').read_text())
    assert data['linux_remaining_owned_identities']==[]
    result=case/'formal/run/result.json'
    if result.exists():
        run=json.loads(result.read_text())
        assert run['children_reaped'] and not run['cleanup_errors']
    summary.append(dict(case=str(case),status=data['status'],wrapper_identity_check='empty'))
probe="""import json,pathlib,sys
boot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(); live=[]
for row in json.loads(sys.argv[1]):
 if row['host_boot_id']!=boot: continue
 p=pathlib.Path('/proc')/str(row['pid'])/'stat'
 try: ticks=p.read_text().rsplit(')',1)[1].split()[19]
 except FileNotFoundError: continue
 if ticks==str(row['start_ticks']): live.append(row)
print(json.dumps(dict(current_boot_id=boot,remaining_owned=live)))
"""
checked=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--exec','python3','-c',probe,json.dumps(identities)],capture_output=True,text=True,check=True)
live=json.loads(checked.stdout)
assert live['remaining_owned']==[]
record=dict(cases=summary,identity_count=len(identities),live_check=live,cleanup_scope='Exact identities only; no process termination by this audit')
Path('validation/gcs-bridge-20260908/final-process-audit.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(dict(cases=len(summary),identities=len(identities),remaining=live['remaining_owned'])))

