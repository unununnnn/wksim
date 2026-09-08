import json
from pathlib import Path
from Simulator.wksim_runtime.build_identity import source_snapshot,sha
p=Path('/root/wksim-ap-pv-vn04950x')
record=json.loads((p/'pv-source.json').read_text())
base=Path(record['baseline_root'])
baseline_raw=(base/'wksim-build.json').read_bytes()
assert sha(baseline_raw)==record['baseline_manifest_sha256']
assert source_snapshot(base/'src',commit=record['commit'])==json.loads(baseline_raw)['source']
assert source_snapshot(p/'src',commit=record['commit'])==record['source']
build=json.loads((p/'pv-build.json').read_text())
assert sha(Path(build['binary']).read_bytes())==build['binary_sha256']
build.update(source_unchanged_during_build=True,fixed_baseline_unchanged=True)
(p/'pv-build.json').write_text(json.dumps(build,indent=2)+'\n')
Path('validation/migration-followup-20260908/ap-pv-sealed.json').write_text(json.dumps(build,indent=2)+'\n')
print(json.dumps({'status':build['status'],'source_unchanged':True,'baseline_unchanged':True,'binary_sha256':build['binary_sha256']}))
