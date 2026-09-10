import json,hashlib,tarfile,shutil
from pathlib import Path
base=Path('/mnt/c/Users/PC/Documents/odid编译/wksim/validation/44-efficiency-flight')
specs=[('px4','baseline','01'),('px4','fault','01'),('px4','fault','02'),('arducopter','baseline','01'),('arducopter','baseline','02'),('arducopter','baseline','03'),('arducopter','fault','01'),('arducopter','fault','02')]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
for stack,case,attempt in specs:
 run=f'efficiency-{stack}-{case}-{attempt}';root=Path('/root')/f'wksim-efficiency-flight-{stack}-{case}-{attempt}'/run
 out=base/run;out.mkdir(exist_ok=False)
 names=['result.json','admission.json','config.json','isolation.json','control-build.json','control.log','fc.log','agent.log','physics.log','rc-dds.jsonl','prometheus.jsonl','truth.jsonl','physics-1ms.jsonl','physics-actuator-packets.jsonl','efficiency-profile.json','efficiency-arm.json','efficiency-event.json','efficiency-origin.json','efficiency-revoked.json','efficiency-failure.json']
 files=[root/n for n in names if (root/n).is_file()]
 for directory in ('run-source','control-source','logs','log'):
  if (root/directory).is_dir():files.extend(p for p in (root/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
 hashes={p.relative_to(root).as_posix():digest(p) for p in files}
 archive=out/'raw-evidence.tar.gz'
 with tarfile.open(archive,'w:gz',compresslevel=6) as tar:
  for p in files:tar.add(p,arcname=p.relative_to(root).as_posix(),recursive=False)
 with tarfile.open(archive) as tar:
  for member in tar:assert hashlib.sha256(tar.extractfile(member).read()).hexdigest()==hashes[member.name]
 shutil.copy2(root/'result.json',out/'result.json')
 audit=Path('/root')/(run+'-audit.json')
 if audit.exists():shutil.copy2(audit,out/'audit.json')
 (out/'archive.json').write_text(json.dumps(dict(raw_directory=str(root),files=hashes,archive_sha256=digest(archive)),indent=2)+'\n')
 print(json.dumps(dict(run=run,bytes=archive.stat().st_size)),flush=True)
