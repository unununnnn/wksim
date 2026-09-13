"""Bind final audit, current sources and every retained attempt without replacing them."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

final = []
for label, audit_path in [('px4-08', '/root/wksim-global-px408-audit01.json'),
                          ('ap-05', '/root/wksim-global-ap05-audit01.json')]:
    audit = json.loads(Path(audit_path).read_text())
    result = json.loads((ROOT/label/'result.json').read_text())
    assert audit['ok'] and audit['home_change'] and result['source_unchanged']
    assert audit['run_id'] == result['run_id']
    assert audit['files']['result.json'] == digest(ROOT/label/'result.json')
    assert all(digest(REPO/name) == sha for name, sha in result['source_sha256'].items())
    control = json.loads((Path(result['run_dir'])/'control-build.json').read_text())
    assert all(digest(REPO/'ros2/src/prometheus_control/prometheus_control'/name) == sha
               for name, sha in control['python_sha256'].items())
    destination = ROOT/label/'audit.json'
    with destination.open('xb') as stream: stream.write(Path(audit_path).read_bytes())
    final.append(dict(label=label, stack=result['stack'], run_id=result['run_id'],
        archive=json.loads((ROOT/label/'archive.json').read_text()), audit_sha256=digest(destination),
        control_manifest_sha256=audit['files']['control-build.json'], physical_ticks=audit['physical_ticks'],
        raw_dds_records=audit['raw_dds_records'], global_publications=audit['global_publications'],
        maximum_axis_tilt_rad=audit['maximum_axis_tilt_rad'], current_sources_match=True,
        control_epoch=audit['control_epoch'], datum_proof_sha256=audit['files']['datum-proof.json']))
attempts = []
for path in sorted(ROOT.glob('*/archive.json')):
    entry = json.loads(path.read_text())
    assert digest(path.parent/'raw-evidence.tar.gz') == entry['raw_sha256']
    attempts.append(dict(label=path.parent.name, **entry))
value = dict(schema='global-home-flight-matrix-v1', ok=True, experimental=True,
    production_admitted=False, final=final, attempts=attempts,
    superseded=dict(px4_07='Prior passing audit withdrawn: noisy GPS sample used as truth origin'),
    audit_source_sha256={name:digest(REPO/name) for name in ('tools/audit_global_flight.py','tools/audit_global_home_flight.py')},
    limits=['100m native-compatible global envelope', 'AP same-value home reset profile rejected',
            'No G6 numerical equivalence or joint-rate acceptance implied'])
with (ROOT/'final-matrix.json').open('x') as stream: json.dump(value,stream,indent=2); stream.write('\n')
print(json.dumps(dict(ok=True,final=final,retained_attempts=len(attempts)),indent=2))
