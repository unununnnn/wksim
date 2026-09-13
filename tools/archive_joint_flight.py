"""Preserve one joint-flight directory in verified chunks without dependent binaries."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile


FORBIDDEN_SUFFIXES = {'.exe', '.dll', '.so', '.uasset', '.slx', '.p', '.pyc'}
ARCHIVE = 'raw-evidence.tar.gz'


def digest(stream):
    value = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        value.update(chunk)
    return value.hexdigest()


def archive(root):
    root = Path(root).resolve(strict=True)
    target = root / ARCHIVE
    record_path = root / 'archive.json'
    if target.exists() or record_path.exists():
        raise FileExistsError('Evidence already archived')
    files = []
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Symlink in evidence: ' + str(path))
        if path.is_file():
            if path.suffix.lower() in FORBIDDEN_SUFFIXES:
                raise ValueError('Dependent binary in evidence: ' + str(path))
            files.append(path)
    members = {}
    with target.open('xb') as raw, tarfile.open(fileobj=raw, mode='w:gz') as output:
        for path in files:
            name = path.relative_to(root).as_posix()
            with path.open('rb') as stream:
                members[name] = digest(stream)
            output.add(path, arcname=name, recursive=False)
    actual = {}
    with tarfile.open(target, mode='r|gz') as source:
        for item in source:
            if not item.isfile() or item.name in actual:
                raise ValueError('Invalid archive member')
            with source.extractfile(item) as stream:
                actual[item.name] = digest(stream)
    if actual != members:
        raise ValueError('Archive does not reproduce original evidence')
    parts = []
    whole = hashlib.sha256()
    with target.open('rb') as source:
        while data := source.read(32 * 1024 * 1024):
            whole.update(data)
            part = root / f'{ARCHIVE}.part-{len(parts) + 1:03d}'
            with part.open('xb') as output:
                output.write(data)
            parts.append(dict(path=part.name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    record = dict(schema='wksim.joint-flight-archive.v1', archive=ARCHIVE, bytes=target.stat().st_size,
                  sha256=whole.hexdigest(), files=members, parts=parts)
    with record_path.open('x', encoding='utf-8') as output:
        json.dump(record, output, indent=2)
        output.write('\n')
    return dict(root=str(root), bytes=record['bytes'], files=len(members), parts=len(parts), sha256=record['sha256'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    print(json.dumps(archive(parser.parse_args().root)))
