"""Archive generated evidence and source identities; omit build/vendor source copies."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
dest = Path(__file__).resolve().parent / root.name
dest.mkdir(exist_ok=False)
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

for name in ['identity.json', 'configure.log', 'build.log', 'manifest.json', 'native.tsv', 'wire.jsonl',
             'process.log', 'ground.parm', 'audit.json', 'hashes.json', 'tests.json']:
    path = root / name
    if path.is_file():
        shutil.copyfile(path, dest / name)
for path in root.glob('*.tsv'):
    if not (dest / path.name).exists():
        shutil.copyfile(path, dest / path.name)
if (root / 'src').is_dir():
    source = root / 'src'
    delta = subprocess.check_output(['git', '-C', str(source), 'diff', '--binary'])
    (dest / 'source.patch').write_bytes(delta)
    (dest / 'SIM_WksimGNSS.h').write_bytes((source / 'libraries/SITL/SIM_WksimGNSS.h').read_bytes())
    seal_path = Path('/root/wksim-ap-clock-stop-OXQqdR/wksim-build.json')
    seal = json.loads(seal_path.read_text())
    inventory = {}
    missing = []
    changed = []
    symlinks = {}
    for name, record in seal['source']['files'].items():
        path = source / name
        if path.is_symlink():
            target = str(path.readlink())
            symlinks[name] = target
            if target != record['symlink']:
                changed.append(name)
            continue
        if not path.is_file():
            missing.append(name)
            continue
        value = sha(path)
        inventory[name] = value
        if value != record['sha256']:
            changed.append(name)
    inventory['libraries/SITL/SIM_WksimGNSS.h'] = sha(source / 'libraries/SITL/SIM_WksimGNSS.h')
    data = {'baseline_manifest': str(seal_path), 'baseline_manifest_sha256': sha(seal_path),
            'head': subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip(),
            'changed_from_baseline_manifest': changed, 'missing_from_baseline_manifest': missing,
            'files_sha256': inventory, 'symlinks': symlinks,
            'compiler': subprocess.check_output(['g++', '--version'], text=True)}
    (dest / 'source-inventory.json').write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps({'source_files': len(inventory), 'changed': changed, 'missing': missing}))
else:
    print(str(dest))
(dest / 'archive-hashes.json').write_text(json.dumps({p.name: sha(p) for p in dest.iterdir() if p.is_file()}, indent=2) + '\n')
