"""Retain the three completed diagnostic attempts and the self-only canary."""
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

root=Path(__file__).resolve().parent
archives=[]
for label,source in [(f'probe-{i:02d}',Path(f'/root/wksim-scheduler-probe-35728b1-{i:02d}')) for i in (1,2,3)]:
    result=json.loads((source/'report.json').read_text())
    assert result['manager_returncode'] is not None and result['remaining_manager_group']==[]
    assert result['product_result']['epochs'] and all(e['remaining_group_members']==[] for e in result['product_result']['epochs'])
    target=root/label;target.mkdir()
    shutil.copy2(source/'report.json',target/'report.json')
    if (source/'analysis-final.json').exists():shutil.copy2(source/'analysis-final.json',target/'analysis.json')
    archive=target/'raw-evidence.tar.gz'
    with tarfile.open(archive,'x:gz',compresslevel=6) as stream:stream.add(source,arcname=source.name)
    item=dict(label=label,source=str(source),sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),bytes=archive.stat().st_size,
        status=result['status'],all_epoch_groups_retired=True,
        disposition=('superseded_empty_capture_not_valid_evidence' if label=='probe-01' else
                     'mapping_ambiguity_rejected' if label=='probe-02' else 'loss_free_ground_diagnostic_only'))
    (target/'archive.json').write_text(json.dumps(item,indent=2)+'\n');archives.append(item)
    print(json.dumps(item),flush=True)
source=Path('/root/wksim-trace-canary-35728b1-01')
target=root/'canary';target.mkdir()
for name in ('result.json','trace.txt'):shutil.copy2(source/name,target/name)
(root/'archives.json').write_text(json.dumps(archives,indent=2)+'\n')
