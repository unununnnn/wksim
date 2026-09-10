import json,hashlib
from pathlib import Path
base=Path('/mnt/c/Users/PC/Documents/odid编译/wksim/validation/44-efficiency-flight');base.mkdir(parents=True,exist_ok=True)
specs=[('px4','baseline','01'),('px4','fault','01'),('px4','fault','02'),('arducopter','baseline','03'),('arducopter','fault','01'),('arducopter','fault','02')]
rows=[]
for stack,case,attempt in specs:
 run=f'efficiency-{stack}-{case}-{attempt}';root=Path('/root')/f'wksim-efficiency-flight-{stack}-{case}-{attempt}'/run
 result=json.loads((root/'result.json').read_text());audit=json.loads((Path('/root')/(run+'-audit.json')).read_text())
 assert audit['status']=='pass' and result['source_unchanged'] and result['candidate_unchanged']
 rows.append(dict(run_id=run,raw_directory=str(root),audit=audit,control_manifest=result['admission']['control_manifest'],
  control_sha256=result['admission']['control_sha256'],control_epoch=result['task']['control_epoch'],
  initial_random_state=result['admission']['efficiency_model']['initial_random_state'],
  library_sha256=result['admission']['efficiency_model']['library_sha256']))
assert len({r['control_epoch'] for r in rows})==6
assert len({r['library_sha256'] for r in rows})==1
assert all(r['initial_random_state']==rows[0]['initial_random_state'] for r in rows)
(base/'matrix.json').write_text(json.dumps(dict(status='pass',runs=rows,same_native_initial_random_state=True,
 new_control_epochs=True,closed_loop_bitwise_replay_claimed=False),indent=2)+'\n')
print({'runs':len(rows),'status':'pass'})
