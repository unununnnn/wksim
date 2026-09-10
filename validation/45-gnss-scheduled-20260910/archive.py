import hashlib,json,shutil,tarfile
from pathlib import Path
out=Path('/mnt/c/Users/PC/Documents/odid编译/wksim/validation/45-gnss-scheduled-20260910')
out.mkdir(exist_ok=False)
build=Path('/root/wksim-ap-gnss-flight-20260910-01')
for name in ('identity.json','scheduled-build.json','flight-seal.json','configure.log','build.log'):
 shutil.copy2(build/name,out/name)
files={}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
with tarfile.open(out/'ground-raw.tar.gz','w:gz') as tar:
 for run in ('wksim-ap-gnss-scheduled-ground-01','wksim-ap-gnss-scheduled-dds-01'):
  root=Path('/root')/run
  for path in root.iterdir():
   if path.is_file():
    name=run+'/'+path.name;files[name]=sha(path);tar.add(path,arcname=name)
with tarfile.open(out/'ground-raw.tar.gz') as tar:
 for member in tar:
  assert hashlib.sha256(tar.extractfile(member).read()).hexdigest()==files[member.name]
shutil.copy2('/root/wksim-ap-gnss-scheduled-dds-01-final-audit.json',out/'final-audit.json')
(out/'archive.json').write_text(json.dumps(dict(files=files,archive_sha256=sha(out/'ground-raw.tar.gz'),
 source_roots=['/root/wksim-ap-gnss-scheduled-ground-01','/root/wksim-ap-gnss-scheduled-dds-01']),indent=2)+'\n')
print(out)
