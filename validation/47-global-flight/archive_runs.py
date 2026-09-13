"""Preserve each completed attempt, including failed pre-arm runs, without replacement."""
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import sys

ROOT = Path(__file__).resolve().parent
RUNS = [
    ('ap-01', '/root/wksim-global-flight-ap-20260910-01/8cf47a938c83468b9fbd8d13ad2df1b0'),
    ('ap-02', '/root/wksim-global-flight-ap-20260910-02/ec2017c0418a4ff394ad6bc0a2f54739'),
    ('ap-03', '/root/wksim-global-flight-ap-20260910-03/61341c9f94fc459d889ca248c6a5fe44'),
    ('px4-01', '/root/wksim-global-flight-px4-20260910-01/c6dcff465e334d928cf45dc64f5a4487'),
    ('px4-03', '/root/wksim-global-flight-px4-20260910-03/b3b93d6c9d494c888055824783616e6f'),
    ('px4-04', '/root/wksim-global-flight-px4-20260910-04/db534f952c5b4d8eb2a75c1b52888876'),
    ('px4-05', '/root/wksim-global-flight-px4-20260910-05/0dd48c76ba29448bbfb0b42c65987a23'),
    ('px4-06', '/root/wksim-global-flight-px4-20260910-06/4fb91f0971554c82b2747e546fedb4b6'),
    ('px4-07', '/root/wksim-global-flight-px4-20260910-07/e7a841c544b547e88a7c4f1be3a4dabc'),
    ('ap-04', '/root/wksim-global-flight-ap-20260910-04/7056e7d6d681474f9722e9ebdf3d113d'),
    ('px4-08', '/root/wksim-global-flight-px4-20260910-08/d8bc659871d44a18a1846cc5a4412245'),
    ('ap-05', '/root/wksim-global-flight-ap-20260910-05/834e4b7a51b44793a2eafc885640a91e')]

if set(sys.argv[1:]) - {label for label, _ in RUNS}: raise ValueError('Unknown retained run label')

for label, directory in RUNS:
    if len(sys.argv) > 1 and label not in sys.argv[1:]: continue
    source = Path(directory)
    result = json.loads((source/'result.json').read_text())
    if not result['children_reaped']: raise RuntimeError('Cannot archive a live run')
    destination = ROOT/label
    destination.mkdir()
    shutil.copy2(source/'result.json', destination/'result.json')
    archive = destination/'raw-evidence.tar.gz'
    with tarfile.open(archive, 'x:gz', compresslevel=6) as tar:
        tar.add(source, arcname=source.name)
    record = dict(source=str(source), run_id=result['run_id'], status=result['status'],
        raw_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        bytes=archive.stat().st_size, result_sha256=hashlib.sha256((source/'result.json').read_bytes()).hexdigest())
    (destination/'archive.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(record), flush=True)
