"""Retain acquisition evidence without shipping UE/FC/model binaries or vendor assets."""
import hashlib
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'validation/40-aruco-live-scene'


def digest(stream):
    value=hashlib.sha256()
    while chunk:=stream.read(1024*1024):value.update(chunk)
    return value.hexdigest()


entries=[]
for number in (1,2,3):
    case=BASE/f'run-514743f-{number:02d}'
    selected=[p for p in case.iterdir() if p.is_file()]
    for folder in ('sources','view'):
        selected.extend(p for p in (case/folder).rglob('*') if p.is_file())
    selected.extend(p for p in (case/'run').iterdir() if p.is_file() and p.suffix=='.json')
    # These are the actual authority/input/display and process ownership records.
    for epoch in (case/'run/epochs').iterdir():
        selected.extend(p for p in epoch.iterdir() if p.is_file() and p.name in
            ('wire.jsonl','rate.jsonl','authority.jsonl','status.json','result.json','children.json'))
    archive=BASE/f'aruco-514743f-{number:02d}.tar.gz'
    hashes={}
    with archive.open('xb') as raw,tarfile.open(fileobj=raw,mode='w:gz') as target:
        for path in sorted(selected):
            assert not path.is_symlink()
            name=path.relative_to(case).as_posix()
            assert path.suffix.lower() not in ('.dll','.so','.exe','.uasset','.slx','.p')
            with path.open('rb') as stream:hashes[name]=digest(stream)
            target.add(path,arcname=name,recursive=False)
    observed={}
    with tarfile.open(archive,mode='r|gz') as source:
        for member in source:
            assert member.isfile() and member.name not in observed
            with source.extractfile(member) as stream:observed[member.name]=digest(stream)
    assert observed==hashes
    with archive.open('rb') as stream:sha=digest(stream)
    entries.append(dict(case=case.name,original_root=str(case),archive=archive.name,
        bytes=archive.stat().st_size,sha256=sha,files=hashes))
with (BASE/'archives-514743f.json').open('x') as stream:json.dump(entries,stream,indent=2)
print(json.dumps([dict(case=e['case'],bytes=e['bytes'],files=len(e['files'])) for e in entries]))
