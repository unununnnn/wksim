import json,hashlib,tarfile,shutil
from pathlib import Path
base=Path('/mnt/c/Users/PC/Documents/odid编译/wksim/validation/45-gnss-flight');base.mkdir(exist_ok=True)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
for label in ('px4-01','px4-02','px4-03','ap-01','ap-02','ap-03','ap-04','ap-05','px4-04','px4-05'):
 parent=Path('/root/wksim-gnss-flight-'+label)
 results=(list(parent.glob('*/result.json')) or list(parent.glob('*/incomplete-result.json'))) if parent.exists() else []
 if not results or (base/label).exists():continue
 root=results[0].parent;out=base/label;out.mkdir()
 files=[p for p in root.iterdir() if p.is_file() and p.suffix in ('.json','.jsonl','.log','.tsv','.parm','.bson')]
 for directory in ('run-source','control-source','log','logs'):
  if (root/directory).is_dir():files.extend(p for p in (root/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
 checks={p.relative_to(root).as_posix():sha(p) for p in files}
 archive=out/'raw-evidence.tar.gz'
 with tarfile.open(archive,'w:gz') as tar:
  for p in files:tar.add(p,arcname=p.relative_to(root).as_posix(),recursive=False)
 with tarfile.open(archive) as tar:
  for member in tar:assert hashlib.sha256(tar.extractfile(member).read()).hexdigest()==checks[member.name]
 shutil.copy2(results[0],out/results[0].name)
 (out/'archive.json').write_text(json.dumps(dict(raw_directory=str(root),files=checks,archive_sha256=sha(archive)),indent=2)+'\n')
 print(json.dumps(dict(label=label,status=json.loads(results[0].read_text())['status'],bytes=archive.stat().st_size)),flush=True)
