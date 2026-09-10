"""Explicit global-reference evidence binding; never infer a vertical datum."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from .global_reference import coordinates, number, require


def validate_profile(value):
    require(type(value) is dict and set(value) == {'schema', 'proof_path', 'proof_sha256',
            'require_same_value_home_reset'}, 'global_profile_fields')
    require(value['schema'] == 'global-home-v1', 'schema_unsupported')
    path = value['proof_path']
    require(type(path) is str and path.startswith('/') and not path.startswith('//')
            and '\\' not in path and '..' not in PurePosixPath(path).parts
            and not any(ord(c) < 32 for c in path), 'datum_proof_path')
    require(type(value['proof_sha256']) is str and
            re.fullmatch('[0-9a-f]{64}', value['proof_sha256']) is not None, 'datum_proof_hash')
    require(type(value['require_same_value_home_reset']) is bool, 'invalid_flag')
    return dict(value)


def load_proof(profile, stack, run_id):
    profile = validate_profile(profile)
    require(not (stack == 'arducopter' and profile['require_same_value_home_reset']),
            'ap_same_value_home_reset_unsupported')
    path = Path(profile['proof_path'])
    require(path.resolve(strict=True) == path and not path.is_symlink(), 'datum_proof_path')
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == profile['proof_sha256'], 'datum_proof_hash')
    proof = json.loads(raw)
    require(type(proof) is dict and set(proof) == {'schema', 'stack', 'run_id', 'datum',
            'scene_origin', 'native_binary', 'sources'}, 'datum_proof_fields')
    require((proof['schema'], proof['stack'], proof['run_id'], proof['datum']) ==
            ('global-datum-proof-v1', stack, run_id, 'amsl'), 'datum_unverified')
    origin = proof['scene_origin']
    require(type(origin) is dict and set(origin) == {'id', 'latitude_deg', 'longitude_deg',
            'alt_amsl_m'}, 'scene_origin_invalid')
    require(type(origin['id']) is str and bool(origin['id']), 'scene_origin_invalid')
    coordinates(origin['latitude_deg'], origin['longitude_deg'])
    number(origin['alt_amsl_m'])
    require(type(proof['sources']) is dict and bool(proof['sources']), 'datum_sources_missing')
    native = proof['native_binary']
    require(type(native) is dict and set(native) == {'path', 'sha256'}, 'datum_native_missing')
    for name, checksum in list(proof['sources'].items()) + [(native['path'], native['sha256'])]:
        source = Path(name)
        require(source.is_absolute() and source.resolve(strict=True) == source,
                'datum_source_path')
        require(hashlib.sha256(source.read_bytes()).hexdigest() == checksum, 'datum_source_changed')
    return proof
