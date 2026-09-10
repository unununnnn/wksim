"""Preserve camera/task evidence in verified chunks; exclude dependent binaries."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile


def digest(stream):
    h=hashlib.sha256()
    while chunk:=stream.read(1024*1024):h.update(chunk)
    return h.hexdigest()


def archive(root):
    root=Path(root).resolve()
    target=root/'raw-evidence.tar.gz'
    if target.exists() or (root/'archive.json').exists():raise FileExistsError('Evidence already archived')
    files=[p for p in root.iterdir() if p.is_file()]
    for folder in ('view','sources'):
        files.extend(p for p in (root/folder).rglob('*') if p.is_file())
    files.extend(p for p in (root/'run').iterdir() if p.is_file() and p.suffix=='.json')
    names={'wire.jsonl','rate.jsonl','clock.jsonl','write-timing.jsonl','public-dds.jsonl','scene-lifecycle.jsonl',
           'arducopter-truth.jsonl','px4-truth.jsonl','children.json','preflight.json','result.json',
           'px4-setup-observer.jsonl','px4-control.log','arducopter-control.log','px4-fc.log','arducopter-fc.log'}
    for epoch in (root/'run/epochs').iterdir():
        files.extend(p for p in epoch.iterdir() if p.is_file() and (p.name in names or p.name.endswith('-maps.txt')))
        for folder in ('tasks','source','aruco'):
            files.extend(p for p in (epoch/folder).rglob('*') if p.is_file())
    members={}
    with target.open('xb') as raw,tarfile.open(fileobj=raw,mode='w:gz') as out:
        for path in sorted(files):
            if path.is_symlink() or path.suffix.lower() in ('.exe','.dll','.so','.uasset','.slx','.p','.pyc'):
                raise ValueError('Dependent binary or symlink in evidence: '+str(path))
            name=path.relative_to(root).as_posix()
            if name in members:raise ValueError('Duplicate archive member: '+name)
            with path.open('rb') as stream:members[name]=digest(stream)
            out.add(path,arcname=name,recursive=False)
    actual={}
    with tarfile.open(target,mode='r|gz') as inp:
        for item in inp:
            if not item.isfile() or item.name in actual:raise ValueError('Invalid archive member')
            with inp.extractfile(item) as stream:actual[item.name]=digest(stream)
    if actual!=members:raise ValueError('Archive does not reproduce original evidence')
    parts=[];whole=hashlib.sha256()
    with target.open('rb') as stream:
        while data:=stream.read(32*1024*1024):
            whole.update(data);path=root/(target.name+f'.part-{len(parts)+1:03d}')
            with path.open('xb') as part:part.write(data)
            parts.append(dict(path=path.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
    record=dict(archive=target.name,bytes=target.stat().st_size,sha256=whole.hexdigest(),files=members,parts=parts)
    with (root/'archive.json').open('x',encoding='utf-8') as stream:json.dump(record,stream,indent=2)
    return dict(root=str(root),bytes=record['bytes'],files=len(members),parts=len(parts),sha256=record['sha256'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path)
    print(json.dumps(archive(parser.parse_args().root)))
