"""Retain real airborne image/state evidence; exclude engine/FC/model binaries."""
import hashlib
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[2]


def digest(stream):
    h=hashlib.sha256()
    while chunk:=stream.read(1024*1024):h.update(chunk)
    return h.hexdigest()


results=[]
for number in (1,2,3):
    case=ROOT/f'validation/40-aruco-flight-scene-{number:02d}'
    files=[p for p in case.iterdir() if p.is_file()]
    for folder in ('view','sources'):
        files.extend(p for p in (case/folder).rglob('*') if p.is_file())
    files.extend(p for p in (case/'run').iterdir() if p.is_file() and p.suffix=='.json')
    for epoch in (case/'run/epochs').iterdir():
        names={'wire.jsonl','rate.jsonl','clock.jsonl','public-dds.jsonl','scene-lifecycle.jsonl',
            'arducopter-truth.jsonl','px4-truth.jsonl','children.json','preflight.json','result.json',
            'px4-setup-observer.jsonl','px4-control.log','arducopter-control.log','px4-fc.log','arducopter-fc.log'}
        files.extend(p for p in epoch.iterdir() if p.is_file() and p.name in names)
        for folder in ('tasks','source'):
            if (epoch/folder).is_dir():files.extend(p for p in (epoch/folder).rglob('*') if p.is_file())
    archive=case/'raw-evidence.tar.gz';hashes={}
    with archive.open('xb') as raw,tarfile.open(fileobj=raw,mode='w:gz') as out:
        for p in sorted(files):
            assert not p.is_symlink() and p.suffix.lower() not in ('.so','.dll','.exe','.uasset','.slx','.p','.pyc')
            name=p.relative_to(case).as_posix();assert name not in hashes
            with p.open('rb') as stream:hashes[name]=digest(stream)
            out.add(p,arcname=name,recursive=False)
    actual={}
    with tarfile.open(archive,mode='r|gz') as inp:
        for member in inp:
            assert member.isfile() and member.name not in actual
            with inp.extractfile(member) as stream:actual[member.name]=digest(stream)
    assert actual==hashes
    with archive.open('rb') as stream:archive_sha=digest(stream)
    record=dict(archive=archive.name,bytes=archive.stat().st_size,sha256=archive_sha,files=hashes)
    with (case/'archive.json').open('x') as stream:json.dump(record,stream,indent=2)
    results.append(dict(case=case.name,bytes=record['bytes'],files=len(hashes)))
print(json.dumps(results))
