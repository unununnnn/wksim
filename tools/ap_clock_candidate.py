"""Opt-in, read-only experimental admission for tools probes (never flight proof).

Seal after a completed build; pass the printed SHA through an independent channel.
No build or flight process is started. Git commands only inspect source/patches.
The ROS environment must retain the fixed baseline state overlay.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.preflight import preflight

COMMIT = '1511f27194f1dcc3728270883047bdf022b3fd53'
BASELINE_ROOT = '/root/wksim-ap-dds-yaw-state-4Wr27s'
BASELINE_SHA256 = '98c003de2a328b3aeb5813583070f4640dc6c935bde9f42fedaaaefad39ac9b5'
BINARY = 'build/sitl/bin/arducopter'
PATCHES = ('patches/arducopter/0001-dds-global-position-yaw.patch',
           'patches/arducopter/0002-dds-local-state.patch',
           'patches/arducopter/0003-json-integer-clock-interruptible-stop.patch')
BUILD_SCRIPT = 'tools/build-ap-dds-yaw.sh'
CACHES = {'.git', '__pycache__', '.pytest_cache', '.mypy_cache', '.wafcache', 'build'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def candidate_root(value):
    if not isinstance(value, str) or not re.fullmatch(r'/root/wksim-ap-clock-stop-[A-Za-z0-9_-]+', value):
        raise ValueError('Candidate must be an absolute /root/wksim-ap-clock-stop-* root')
    root = Path(value)
    if not root.is_dir() or root.is_symlink() or root.resolve(strict=True) != root:
        raise ValueError('Candidate root must exist without symlink ancestors')
    return root


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


def source_snapshot(source):
    """Walk each git index, including initialized submodules and their untracked files."""
    files, deleted, excluded, repositories = {}, [], [], {}

    def visit(directory, expected=None):
        if directory.is_symlink() or directory.resolve(strict=True) != directory:
            raise ValueError(f'Symlink source repository: {directory}')
        if Path(os.fsdecode(git(directory, 'rev-parse', '--show-toplevel')).strip()).resolve() != directory:
            raise ValueError(f'Uninitialized source repository: {directory}')
        head = git(directory, 'rev-parse', 'HEAD').decode().strip()
        if head != (COMMIT if expected is None else expected):
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


def snapshot(root):
    source = root / 'src'
    inputs = {name: file_identity(REPO / name, REPO, nonempty=True)
              for name in (*PATCHES, BUILD_SCRIPT)}
    git(source, 'apply', '--reverse', '--check', *(str(REPO / p) for p in reversed(PATCHES)))
    result = dict(schema_version=1, candidate_root=str(root), commit=COMMIT,
                  baseline_root=BASELINE_ROOT, baseline_binary_sha256=BASELINE_SHA256,
                  source=source_snapshot(source), repository_inputs=inputs,
                  artifacts={name: file_identity(root / name, root, nonempty=True)
                             for name in (BINARY, 'configure.log', 'build.log')})
    if not os.access(root / BINARY, os.X_OK):
        raise ValueError('Candidate binary is not executable')
    return result


def seal(root):
    root = candidate_root(str(root))
    manifest = root / 'wksim-build.json'
    if manifest.exists() or manifest.is_symlink():
        raise FileExistsError(str(manifest))
    record = snapshot(root)
    raw = (json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    with manifest.open('xb') as stream:
        stream.write(raw)
    return manifest, sha(raw)


def admit(config, manifest_path=None, manifest_sha256=None):
    baseline = preflight(copy.deepcopy(config))
    if (manifest_path is None) != (manifest_sha256 is None):
        raise ValueError('Provide both manifest path and external SHA256')
    if manifest_path is None:
        return config, baseline
    if baseline.get('ok') is not True or baseline.get('reasons') != []:
        raise ValueError('Fixed baseline preflight rejected: ' + str(baseline))
    if config.get('stack') != 'arducopter' or config.get('ap_candidate') != BASELINE_ROOT:
        raise ValueError('Experimental admission requires the unchanged fixed AP baseline config')
    if not isinstance(manifest_sha256, str) or not re.fullmatch('[0-9a-f]{64}', manifest_sha256):
        raise ValueError('Invalid external manifest SHA256')
    path = Path(manifest_path)
    raw = path.read_bytes()
    if sha(raw) != manifest_sha256:
        raise ValueError('Manifest SHA256 mismatch')
    record = json.loads(raw)
    if not isinstance(record, dict) or type(record.get('schema_version')) is not int or record['schema_version'] != 1:
        raise ValueError('Invalid manifest schema')
    root = candidate_root(record.get('candidate_root'))
    if path != root / 'wksim-build.json' or path.is_symlink():
        raise ValueError('Manifest must belong to the candidate root')
    # Exact comparison checks all fields and independently re-enumerates every set.
    if record != snapshot(root):
        raise ValueError('Candidate snapshot mismatch')
    updated = copy.deepcopy(config)
    updated['ap_candidate'] = str(root)
    return updated, dict(ok=True, experimental=True, production_admitted=False, flown=False,
                         baseline_preflight=baseline, candidate=record,
                         manifest_path=str(path), manifest_sha256=manifest_sha256,
                         ros_overlay_root=BASELINE_ROOT,
                         scope='tools probes only; baseline flight evidence does not prove candidate flight')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('seal').add_argument('root')
    args = parser.parse_args(argv)
    try:
        path, checksum = seal(args.root)
        print(json.dumps(dict(manifest_path=str(path), sha256=checksum)))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'Candidate rejected: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
