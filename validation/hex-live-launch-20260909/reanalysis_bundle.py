"""New immutable-data review bundle; never overwrite original failed reports."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

base = Path(__file__).resolve().parents[2]/'validation'
original, destination, report = (Path(p).resolve() for p in sys.argv[1:4])
assert original.is_relative_to(base) and destination.is_relative_to(base) and report.is_relative_to(base)
assert not destination.exists()
physical = json.loads(report.read_text())
assert physical['passed'] is True
destination.mkdir()
copies = {}


def copy(source, relative):
    source = source.resolve()
    assert source.is_relative_to(base)
    target = destination/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    assert not target.exists()
    shutil.copy2(source, target)
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == sha
    copies[str(relative)] = dict(source=str(source), sha256=sha)


for name in ('manifest.json','completion.json','ue.log','readback.jsonl'):
    copy(original/name,Path(name))
for directory in ('frames','run-source'):
    for source in (original/directory).rglob('*'):
        if source.is_file():
            copy(source,source.relative_to(original))
copy(original/'flight-audit.json',Path('original-flight-audit.json'))
copy(original/'automatic-audit.json',Path('original-automatic-audit.json'))
copy(report,Path('flight-audit.json'))
with (destination/'reanalysis-provenance.json').open('x') as f:
    json.dump(dict(kind='Reaudit of unchanged run, not a new flight',original_directory=str(original),
        physical_report=str(report),run_id=physical['checks']['result']['run_id'],copies=copies),f,indent=2)
print(destination)
