"""GNSS experiment resource admission; no source-pinned baseline is replaced."""
import hashlib
import json
from pathlib import Path
import re

from rc_candidate import admit as base_admit
from Simulator.wksim_runtime.build_identity import source_snapshot


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def admit(stack,run_id,manifest,checksum,profile):
    if not re.fullmatch('[0-9a-f]{32}',run_id):raise ValueError('Native GNSS run identity requires 32 hex characters')
    result=base_admit(stack,run_id,manifest,checksum)
    if stack=='arducopter':
        root=Path(profile['ap_root']);seal=root/'flight-seal.json'
        if root.resolve(strict=True)!=root or digest(seal)!=profile['ap_seal_sha256']:
            raise ValueError('GNSS native seal differs')
        value=json.loads(seal.read_text())
        if source_snapshot(root/'src',commit='1511f27194f1dcc3728270883047bdf022b3fd53')!=value['source']:
            raise ValueError('GNSS source snapshot differs')
        for name,sha in value['generated_sha256'].items():
            if digest(root/name)!=sha:raise ValueError('GNSS generated DDS artifact differs')
        for name,key in [('scheduled-build.json','scheduled_build_sha256'),('build.log','build_log_sha256'),
                         ('configure.log','configure_log_sha256')]:
            if digest(root/name)!=value[key]:raise ValueError('GNSS build record differs')
        binary=root/'build/sitl/bin/arducopter'
        if digest(binary)!=value['binary_sha256']:raise ValueError('GNSS binary differs')
        result['native_override']=dict(path=str(binary),sha256=value['binary_sha256'],seal_sha256=digest(seal),root=str(root))
        result['config']=dict(result['config'],ap_candidate=str(root))
    return result
