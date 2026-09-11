"""Recheck retained #75 raw evidence without loading a model or DLL."""
import hashlib
import json
import math
from pathlib import Path
import subprocess


root = Path(__file__).resolve().parent
repo = root.parents[2]
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
audit = json.loads((root / 'audit.json').read_text())
contract = json.loads((root / 'contract.json').read_text())
assert contract['dt_s'] == .001 and contract['clock_absolute_error_s'] == 1e-8
assert contract['validator_sha256'] == sha(repo / 'tools/validate_generated_e0_lifecycle.py')
assert contract['build_manifest_sha256'] == sha(repo / 'validation/codegen-e0-build-short-cycle-01/build-manifest.json')
all_hashes = []
identities = []
for run in audit['runs']:
    name = run['name']
    process = json.loads((root / name / 'process.json').read_text())
    exit_record = json.loads((root / (name + '-exit.json')).read_text())
    assert run['returncode'] == exit_record['returncode'] == 0
    assert exit_record == run and process['identity'] == run['identity']
    assert process['library_sha256'] == audit['library_sha256']
    assert process['library'] in run['command']
    identities.append(run['identity'])
    for maps in process['maps']:
        paths = [line.split(None, 5)[-1] for line in maps.splitlines() if len(line.split(None, 5)) == 6]
        assert process['library'] in paths
        assert not any(token in path.casefold() for path in paths
                       for token in ('.dll', '.pyd', 'coptersim', 'matlab', 'simulink', 'libmw', 'libgz', 'gazebo'))
    for cycle in (0, 1):
        path = root / name / f'cycle-{cycle}.jsonl'
        digest = sha(path)
        assert digest == audit['raw_sha256'][f'{name}/cycle-{cycle}.jsonl'] == process['cycles'][cycle]
        all_hashes.append(digest)
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        assert len(rows) == 1000
        for tick, row in enumerate(rows, 1):
            level = 0. if tick <= 100 else .5 if tick <= 600 else .45
            assert row['tick'] == tick and row['commands'] == [level] * 4 + [0.] * 12
            assert len(row['output']) == 120 and all(math.isfinite(v) for v in row['output'])
            assert abs(row['output'][2] - tick * .001) <= 1e-8
assert len(all_hashes) == 4 and len(set(all_hashes)) == 1
assert len({identity['pid'] for identity in identities}) == 2
assert json.loads((root / 'build.json').read_text())['returncode'] == 0
for identity in identities:
    for task in Path('/proc').iterdir():
        if not task.name.isdigit():
            continue
        try:
            fields = (task / 'stat').read_text().rsplit(')', 1)[1].split()
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        assert int(fields[2]) != identity['pgid'], 'Recorded model process group remains alive'
report = dict(status='pass', rows=4000, compared_values=480000,
              raw_sha256=all_hashes[0], model_groups_remaining=[],
              no_vendor_dll_in_recorded_maps=True,
              source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
              auditor_sha256=sha(Path(__file__)),
              boundary='Fresh no-vendor model lifecycle only; no ABI compatibility, flight or G6 acceptance')
with (root / 'independent-audit.json').open('x') as stream:
    json.dump(report, stream, indent=2)
print(json.dumps(report))
