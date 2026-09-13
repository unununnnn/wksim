import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
coord = root.parent
consumer = coord/'ds-perf-stream-consumer-20260913-01/perf_stream_consumer.py'
fixtures = coord/'ds-perf-stream-fixtures-20260913-01/fixtures'
index = json.loads((fixtures/'index.json').read_bytes())
outputs = root/'outputs'
outputs.mkdir(exist_ok=False)
results = []
for entry in index['cases']:
    case = fixtures/entry['case']
    for name, pin in entry['files'].items():
        assert hashlib.sha256((case/name).read_bytes()).hexdigest() == pin['sha256']
    expected = json.loads((case/'expected.json').read_bytes())
    output = outputs/(entry['case']+'.json')
    argv = [sys.executable, '-B', str(consumer), '--raw', str(case/'raw.bin'),
            '--metadata', str(case/'metadata.json'), '--output', str(output)]
    if (case/'windows.json').exists():
        argv += ['--windows', str(case/'windows.json')]
    run = subprocess.run(argv, text=True, capture_output=True, timeout=10)
    passed = run.returncode == (3 if expected['rejected'] else 0)
    if not expected['rejected'] and run.returncode == 0:
        report = json.loads(output.read_bytes())
        passed &= report['decoded']['pairs'] == expected['pairs']
        passed &= report['full_acceptance'] is False
        passed &= report['stream_completeness_proven'] is False
        if 'intersections_ns' in expected:
            passed &= [w['intersection_total_ns'] for w in report['windows']] == expected['intersections_ns']
    results.append(dict(case=entry['case'], expected_rejected=expected['rejected'],
                        exit_code=run.returncode, passed=passed,
                        stdout=run.stdout, stderr=run.stderr))
receipt = dict(synthetic=True, consumer_sha256=hashlib.sha256(consumer.read_bytes()).hexdigest(),
               fixtures_index_sha256=hashlib.sha256((fixtures/'index.json').read_bytes()).hexdigest(),
               cases=len(results), failures=sum(not r['passed'] for r in results), results=results)
(root/'receipt.json').write_bytes((json.dumps(receipt, indent=2)+'\n').encode())
print(json.dumps({k: receipt[k] for k in ('synthetic', 'cases', 'failures')}))
raise SystemExit(1 if receipt['failures'] else 0)
