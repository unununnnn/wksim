"""Read-only archive verification before the parent closes RC/efficiency tickets."""
import hashlib
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[2]


def digest(stream):
    value=hashlib.sha256()
    while chunk:=stream.read(1024*1024):value.update(chunk)
    return value.hexdigest()


def verify():
    checked=[]
    for folder,matrix_name in (('38-rc-flight','final-matrix.json'),('44-efficiency-flight','matrix.json')):
        base=ROOT/'validation'/folder
        matrix=json.loads((base/matrix_name).read_text())
        assert matrix['status']=='pass'
        for run in matrix['runs']:
            final=run.get('audit',run);assert final['status']=='pass'
            directory=base/run['run_id'];manifest=json.loads((directory/'archive.json').read_text())
            with (directory/'raw-evidence.tar.gz').open('rb') as stream:archive_sha=digest(stream)
            assert archive_sha==manifest['archive_sha256'],run['run_id']+' archive differs'
            with (directory/'result.json').open('rb') as stream:result_sha=digest(stream)
            assert result_sha==final['result_sha256'],run['run_id']+' result differs'
            hashes={}
            with tarfile.open(directory/'raw-evidence.tar.gz',mode='r|gz') as archive:
                for member in archive:
                    if not member.isfile():continue
                    assert member.name not in hashes,'Duplicate archive member'
                    with archive.extractfile(member) as stream:hashes[member.name]=digest(stream)
            assert hashes==manifest['files'],run['run_id']+' archive members differ'
            assert hashes['result.json']==result_sha
            checked.append(dict(run_id=run['run_id'],archive_sha256=archive_sha,result_sha256=result_sha,
                verified_members=len(hashes),matrix=str((base/matrix_name).relative_to(ROOT))))
    return dict(status='pass',scope='Archive byte identities and recorded final audits; no new flight or physics claim',runs=checked)


if __name__=='__main__':
    result=verify()
    with (ROOT/'validation/coordination/parent-rc-efficiency-archive-check-514743f.json').open('x') as stream:
        json.dump(result,stream,indent=2)
    print(json.dumps(dict(status=result['status'],runs=len(result['runs']),members=sum(r['verified_members'] for r in result['runs']))))
