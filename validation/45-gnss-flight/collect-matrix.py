import json,shutil,hashlib
from pathlib import Path
base=Path('/mnt/c/Users/PC/Documents/odid编译/wksim/validation/45-gnss-flight');rows=[]
for stack,label in [('px4','px4-05'),('arducopter','ap-05')]:
 parent=Path('/root/wksim-gnss-flight-'+label);path=next(parent.glob('*/result.json'));r=json.loads(path.read_text())
 audit=json.loads(Path('/root/wksim-gnss-flight-'+label+'-audit-final-v3.json').read_text())
 assert audit['status']=='pass'
 rows.append(dict(stack=stack,run_id=r['run_id'],raw_directory=str(path.parent),audit=audit,
   control_manifest=r['admission']['control_manifest'],control_sha256=r['admission']['control_sha256'],
   control_epoch=r['task']['control_epoch'],scene_epoch=r['scene_epoch']))
(base/'final-matrix.json').write_text(json.dumps(dict(status='pass',runs=rows),indent=2)+'\n')
for name in ('gnss-preflight-px4.json','gnss-preflight-ap.json','gnss-safe-land-tests.log'):
 shutil.copy2(Path('work')/name,base/name)
print({'status':'pass','runs':len(rows)})
