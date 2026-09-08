import json,subprocess
from pathlib import Path
cases=['depth-lifecycle-20260908-run1','depth-lifecycle-20260908-run2','joint-velocity-yaw-nnh00wfp','joint-velocity-yaw-x8mozm0m']
ids=[];summary=[]
for name in cases:
 p=Path('validation')/name/'run'; r=json.loads((p/'result.json').read_text()); count=0
 for e in r['epochs']:
  assert not e['remaining_group_members']
  c=json.loads((p/'epochs'/e['epoch']/'children.json').read_text())
  for item in c.values():
   x=item['identity']; ids.append(dict(pid=x['pid'],start_ticks=x['start_ticks'],boot=r['host_boot_id']));count+=1
 summary.append(dict(case=name,status=r['status'],children=count))
probe='''import json,pathlib,sys
boot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(); live=[]
for x in json.loads(sys.argv[1]):
 if x['boot']!=boot:continue
 p=pathlib.Path('/proc')/str(x['pid'])/'stat'
 try:t=p.read_text().rsplit(')',1)[1].split()[19]
 except FileNotFoundError:continue
 if t==str(x['start_ticks']):live.append(x)
print(json.dumps(dict(boot=boot,remaining=live)))'''
result=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--exec','python3','-c',probe,json.dumps(ids)],capture_output=True,text=True,check=True)
x=json.loads(result.stdout);assert not x['remaining']
report=dict(cases=summary,identities=len(ids),current=x,scope='Read-only exact owned PID/start_ticks/boot checks')
Path('validation/migration-followup-20260908/process-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(identities=len(ids),remaining=x['remaining'])))
