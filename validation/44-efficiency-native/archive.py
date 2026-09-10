import hashlib,json,tarfile
from pathlib import Path
base=Path('/mnt/c/Users/PC/Documents/odid编译/wksim/validation/44-efficiency-native')
base.mkdir(parents=True,exist_ok=False)
roots=[Path('/root/wksim-efficiency-native-'+s) for s in ('reference-02','normal-02','event-02','event-03','revoke-pending-02','revoke-active-02','tamper-02','cold-01')]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
checks={}
with tarfile.open(base/'native-raw.tar.gz','w:gz',compresslevel=6) as tar:
 for root in roots:
  for name in ('result.json','raw.jsonl','event.json'):
   path=root/name
   if not path.exists():continue
   member=root.name+'/'+name
   checks[member]=digest(path);tar.add(path,arcname=member)
model=Path('/root/wksim-efficiency-model-r97g_cit')
(base/'efficiency-build.json').write_bytes((model/'efficiency-build.json').read_bytes())
(base/'audit.json').write_bytes(Path('/root/wksim-efficiency-native-audit-02.json').read_bytes())
with tarfile.open(base/'native-raw.tar.gz') as tar:
 for member in tar:
  assert hashlib.sha256(tar.extractfile(member).read()).hexdigest()==checks[member.name]
(base/'archive.json').write_text(json.dumps(dict(files=checks,archive_sha256=digest(base/'native-raw.tar.gz'),
    cold_library_same=digest('/root/wksim-efficiency-model-h48ywro3/libwksim_efficiency.so')==digest(model/'libwksim_efficiency.so'),
    cold_raw_same=digest(roots[-1]/'raw.jsonl')==digest(roots[1]/'raw.jsonl')),indent=2)+'\n')
print(base)
