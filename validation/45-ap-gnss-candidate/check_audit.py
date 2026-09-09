"""Tamper copies of actual raw evidence; preserve the original run."""
import json
from pathlib import Path
import shutil
import sys
from probe import audit

source, out = map(lambda p: Path(p).resolve(), sys.argv[1:])
out.mkdir(exist_ok=False)
results = []
for name in ['missing_terminal', 'foreign_epoch', 'missing_tick', 'missing_gps_group', 'outage_write', 'corrupt_ubx']:
    case = out / name
    case.mkdir()
    for filename in ['manifest.json', 'native.tsv', 'wire.jsonl']:
        shutil.copyfile(source / filename, case / filename)
    if name in ['missing_terminal', 'foreign_epoch']:
        path = case / 'manifest.json'
        data = json.loads(path.read_text())
        if name == 'missing_terminal':
            del data['returncode']
        else:
            data['epoch'] = 'f' * 32
        path.write_text(json.dumps(data))
    else:
        path = case / 'native.tsv'
        lines = path.read_text().splitlines()
        if name == 'missing_tick':
            lines.pop(next(i for i, row in enumerate(lines) if row.startswith('JSON\t')))
        elif name == 'missing_gps_group':
            lines = [row for row in lines if not row.startswith('WRITE\t4200\t')]
        else:
            i = next(i for i, row in enumerate(lines) if row.startswith('WRITE\t4000\t'))
            cols = lines[i].split('\t')
            if name == 'outage_write':
                cols[4] = '1'
            else:
                cols[5] = '00' + cols[5][2:]
            lines[i] = '\t'.join(cols)
        path.write_text('\n'.join(lines) + '\n')
    try:
        audit(case)
    except (AssertionError, KeyError, ValueError) as exc:
        results.append({'mutation': name, 'rejected': True, 'error_type': type(exc).__name__})
    else:
        results.append({'mutation': name, 'rejected': False})
(out / 'tests.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results))
raise SystemExit(0 if all(row['rejected'] for row in results) else 1)
