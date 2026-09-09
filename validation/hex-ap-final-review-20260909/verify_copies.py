"""Read-only independent copied-evidence/hash review of AP04."""
import hashlib
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
BUNDLE=ROOT/'validation/25-ap-live-observed-20260909-04-reviewed'

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

provenance=read(BUNDLE/'reanalysis-provenance.json')
checked={}
for name,item in provenance['copies'].items():
    src,dst=Path(item['source']),BUNDLE/name
    assert sha(src)==sha(dst)==item['sha256'],name
    checked[name]=item['sha256']
assert sha(BUNDLE/'flight-audit.json')==sha(Path(provenance['physical_report']))
review=read(BUNDLE/'render-review.json')
visual=read(BUNDLE/'reviewed-audit.json')
assert visual['render_review_sha256']==sha(BUNDLE/'render-review.json')
for name,hash in review['captures'].items():
    assert sha(BUNDLE/'frames'/name)==hash==visual['captures'][name]['sha256']
assert review['binding']==visual['binding']==read(BUNDLE/'manifest.json')['binding']
original=Path(provenance['original_directory'])
old={name:dict(sha256=sha(original/name),status=read(original/name).get('status'))
     for name in ('flight-audit.json','automatic-audit.json') if (original/name).exists()}
summary=dict(copied_files=len(checked),all_source_copy_hashes_equal=True,
    physical_report_equal=True,reviewed_capture_hashes_equal=True,
    old_reports_retained=old,reviewed_visual_sha256=sha(BUNDLE/'reviewed-audit.json'),
    physical_sha256=sha(BUNDLE/'flight-audit.json'),binding=review['binding'])
(OUT/'copy-verification.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
