"""Archive one completed RC run without modifying its retained raw directory."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

p=argparse.ArgumentParser();p.add_argument('run');p.add_argument('audit');a=p.parse_args()
source=Path(a.run).resolve(strict=True)
assert source.parent.parent==Path('/root') and source.parent.name.startswith('wksim-rc-flight-')
target=Path('/mnt/c/Users/PC/Documents/odid编译/wksim/validation/38-rc-flight')/source.name
target.mkdir(parents=True,exist_ok=False)
selected=['result.json','config.json','admission.json','isolation.json','control.log','rc-dds.jsonl','prometheus.jsonl','truth.jsonl','physics-1ms.jsonl','physics.log','agent.log','fc.log','control-build.json','control-source','run-source']
files=[]
for name in selected:
    path=source/name
    if path.is_file(): files.append(path)
    elif path.is_dir(): files.extend(p for p in path.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
for base in ('log','logs'):
    path=source/base
    if path.is_dir(): files.extend(p for p in path.rglob('*') if p.is_file())
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
checks={str(path.relative_to(source)):digest(path) for path in files}
archive=target/'raw-evidence.tar.gz'
with tarfile.open(archive,'w:gz',compresslevel=6) as tar:
    for path in files: tar.add(path,arcname=str(path.relative_to(source)),recursive=False)
with tarfile.open(archive,'r:gz') as tar:
    for member in tar:
        assert hashlib.sha256(tar.extractfile(member).read()).hexdigest()==checks[member.name]
shutil.copy2(source/'result.json',target/'result.json')
if a.audit!='none': shutil.copy2(a.audit,target/'audit.json')
(target/'archive.json').write_text(json.dumps(dict(raw_directory=str(source),files=checks,
    archive_sha256=digest(archive),audit_sha256=digest(target/'audit.json') if a.audit!='none' else None),indent=2)+'\n')
print(json.dumps(dict(path=str(target),files=len(files),compressed_bytes=archive.stat().st_size)))
