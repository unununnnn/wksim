"""Contained build identity snapshots shared by runtime and build tools."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

CACHES = {'.wafcache', '__pycache__', 'build', '.mypy_cache', '.pytest_cache', '.git'}

def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def file_identity(path, boundary, *, nonempty=False, directory_links=False, seen=()):
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(boundary.resolve(strict=True)):
        raise ValueError(f'Path escapes source boundary: {path}')
    if directory_links and path.is_symlink() and resolved.is_dir():
        if resolved in seen:
            raise ValueError(f'Cyclic source directory link: {path}')
        # MAVLink's tracked node_modules links point at its own local_modules.
        # Record both link text and all target content; never just skip the link.
        members = {p.relative_to(resolved).as_posix(): file_identity(
            p, boundary, directory_links=True, seen=(*seen, resolved))
            for p in sorted(resolved.rglob('*')) if p.is_file() or p.is_symlink()}
        return dict(kind='directory_symlink', symlink=os.readlink(path), members=members,
                    sha256=sha(json.dumps(members, sort_keys=True).encode()))
    if not resolved.is_file():
        raise ValueError(f'Not a contained regular file: {path}')
    raw = path.read_bytes()
    if nonempty and not raw:
        raise ValueError(f'Empty required file: {path}')
    return dict(sha256=sha(raw), size=len(raw),
                symlink=os.readlink(path) if path.is_symlink() else None)


def source_snapshot(source, *, commit):
    """Walk each git index, including initialized submodules and their untracked files."""
    files, deleted, excluded, repositories = {}, [], [], {}

    def visit(directory, expected=None):
        if directory.is_symlink() or directory.resolve(strict=True) != directory:
            raise ValueError(f'Symlink source repository: {directory}')
        if Path(os.fsdecode(git(directory, 'rev-parse', '--show-toplevel')).strip()).resolve() != directory:
            raise ValueError(f'Uninitialized source repository: {directory}')
        head = git(directory, 'rev-parse', 'HEAD').decode().strip()
        if head != (commit if expected is None else expected):
            raise ValueError(f'Unexpected source commit: {directory}: {head}')
        prefix = directory.relative_to(source).as_posix()
        diff = git(directory, 'diff', '--binary', '--no-ext-diff', '--no-textconv',
                   '--ignore-submodules=none', 'HEAD', '--')
        repositories[prefix] = dict(commit=head, diff_sha256=sha(diff))
        tracked = {}
        for entry in git(directory, 'ls-files', '--stage', '-z').split(b'\0'):
            if not entry:
                continue
            metadata, name = entry.split(b'\t', 1)
            mode, object_id, stage = metadata.decode().split()
            if stage != '0':
                raise ValueError('Unmerged source index')
            tracked[os.fsdecode(name)] = (mode, object_id)
        others = {os.fsdecode(n) for n in git(directory, 'ls-files', '--others',
                                            '--exclude-standard', '-z').split(b'\0') if n}
        for name in sorted(set(tracked) | others):
            relative = PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts or '\\' in name:
                raise ValueError('Unsafe source path')
            path = directory / name
            key = path.relative_to(source).as_posix()
            if any(p in CACHES for p in relative.parts) or path.suffix == '.pyc':
                excluded.append(key)
                continue
            mode, object_id = tracked.get(name, (None, None))
            if mode == '160000':
                # An absent submodule must not silently produce an empty snapshot.
                visit(path, object_id)
            elif not path.exists() and not path.is_symlink() and name in tracked:
                deleted.append(key)
            else:
                files[key] = file_identity(path, source, directory_links=True)
    visit(source)
    if not files:
        raise ValueError('Empty source file set')
    return dict(files=files, deleted_tracked=sorted(deleted), excluded=sorted(excluded),
                repositories=repositories,
                diff_sha256=sha(json.dumps(repositories, sort_keys=True).encode()))


