"""Compare actual UE-imported mesh bounds to the frozen converted source.

The 0.002 cm bound is an asset import diagnostic (float conversion/removed
degenerate tips), not a vehicle dynamics or sensor-equivalence budget.
"""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--import-report',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    source=json.loads(args.source.read_text(encoding='utf-8'))
    imported=json.loads(args.import_report.read_text(encoding='utf-8'))
    checks=[]
    for row in source['files']:
        if 'obj_path' not in row:
            continue
        name=Path(row['obj_path']).stem
        asset=next((a for a in imported['assets'] if a['name']==name),None)
        errors=[] if asset is None else [abs(asset['bounds_cm'][key][i]-row['converted_bounds_cm'][key][i])
                                        for key in ('min','max') for i in range(3)]
        checks.append(dict(name=name,max_bounds_error_cm=max(errors) if errors else None,
            passed=bool(asset and len(errors)==6 and max(errors)<=.002 and asset['source_sha256']==row['obj_sha256'])))
    report=dict(status='pass' if len(checks)==3 and all(c['passed'] for c in checks) else 'failed',
                limit_cm=.002,checks=checks,source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),
                import_report_sha256=hashlib.sha256(args.import_report.read_bytes()).hexdigest())
    with args.report.open('x',encoding='utf-8') as output:
        json.dump(report,output,indent=2,allow_nan=False)
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='pass' else 1


if __name__=='__main__':
    raise SystemExit(main())
