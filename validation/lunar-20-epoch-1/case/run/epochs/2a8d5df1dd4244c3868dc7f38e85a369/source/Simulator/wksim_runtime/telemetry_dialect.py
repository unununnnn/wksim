"""Load separately generated, SHA256-pinned per-firmware MAVLink dialects."""
from functools import lru_cache
import hashlib
import importlib.util
import json
from pathlib import Path

MANIFEST = Path(__file__).with_name('telemetry-dialects.json')


@lru_cache(maxsize=2)
def _module(path, expected):
    source = Path(path)
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Generated telemetry dialect SHA256 differs; rebuild and review its manifest')
    # Execute the checked bytes, not a second path read or stale bytecode cache.
    spec = importlib.util.spec_from_file_location('_wksim_mavlink_' + expected, source)
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(source), 'exec'), module.__dict__)
    return module


@lru_cache(maxsize=2)
def load_dialect(stack):
    raw_manifest = MANIFEST.read_bytes()
    manifest = json.loads(raw_manifest)
    if manifest['schema_version'] != 1 or manifest['generated'] is not True:
        raise ValueError('Invalid telemetry dialect manifest')
    row = manifest['dialects'][stack]
    build_raw = Path(manifest['build_manifest_path']).read_bytes()
    if hashlib.sha256(build_raw).hexdigest() != manifest['build_manifest_sha256']:
        raise ValueError('Telemetry build evidence SHA256 differs')
    built = json.loads(build_raw)['dialects'][stack]
    if any(built.get(key) != value for key, value in row.items()):
        raise ValueError('Telemetry manifest disagrees with its build evidence')
    module = _module(row['path'], row['sha256'])
    return module, dict(source=row['path'], sha256=row['sha256'],
                        version='git:' + row['generator_commit'], dialect=row['dialect'],
                        fc_commit=row['fc_commit'], mavlink_commit=row['mavlink_commit'],
                        manifest_sha256=hashlib.sha256(raw_manifest).hexdigest())
