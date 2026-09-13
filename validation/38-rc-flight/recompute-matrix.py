import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from tools.audit_rc_flight import audit,digest
specs=[('px4','movement','03'),('px4','recenter','02'),('px4','yaw','02'),('px4','stream-stall','02'),('px4','mode-out','02'),('px4','new-takeover','01')]+[('arducopter',s,'01') for s in ('movement','recenter','yaw','stream-stall','mode-out','new-takeover')]
out=Path('validation/38-rc-flight/final-matrix.json')
assert not out.exists()
rows=[]
for stack,scenario,attempt in specs:
    run=f'rc-{stack}-{scenario}-{attempt}'
    root=Path('/root')/f'wksim-rc-flight-{stack}-{scenario}-{attempt}'/run
    try: row=audit(root)
    except Exception as error: row=dict(status='failed',error=repr(error),stack=stack,scenario=scenario)
    row.update(run_id=run,raw_directory=str(root)); rows.append(row)
    print(json.dumps(row),flush=True)
result=dict(status='pass' if all(r['status']=='pass' for r in rows) else 'failed',runs=rows,audit_sha256=digest('tools/audit_rc_flight.py'),control_manifest='/root/wksim-joint-control-WjBuqN/build.json',control_sha256='ae5236af5052e81a256566a5e05d1840752fffb4d6f5cc512e0c0a5bb9e88c1d')
out.write_text(json.dumps(result,indent=2)+'\n')
raise SystemExit(0 if result['status']=='pass' else 1)
