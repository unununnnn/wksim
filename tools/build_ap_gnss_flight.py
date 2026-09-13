"""Build a separate scheduled AP GNSS candidate using the retained #109 patch recipe."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
BASE_BUILDER=REPO/'validation/45-ap-gnss-candidate/build.py'


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if len(sys.argv)!=2:raise SystemExit('Usage: build_ap_gnss_flight.py /root/wksim-ap-gnss-flight-UNIQUE')
    root=Path(sys.argv[1])
    if root.parent!=Path('/root') or not root.name.startswith('wksim-ap-gnss-flight-') or root.exists():
        raise ValueError('Use a new owned scheduled GNSS candidate root')
    spec=importlib.util.spec_from_file_location('retained_gnss_builder',BASE_BUILDER)
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    builder.HERE=Path(__file__).parent/'ap_gnss_flight'
    before={str(p.relative_to(REPO)):digest(p) for p in (BASE_BUILDER,Path(__file__),builder.HERE/'SIM_WksimGNSS.h')}
    status=1
    try:
        status=builder.main()
    finally:
        if root.is_dir():
            unchanged=all(digest(REPO/name)==value for name,value in before.items())
            record=dict(schema='wksim.ap-gnss-scheduled-build.v1',root=str(root),build_exit=status,
                sources_sha256=before,source_unchanged=unchanged,max_tick=180000,
                minimum_lead_ticks=1000,outage_ticks=15000,recreation_recovery_ticks=30000,
                flown=False,production_admitted=False)
            if (root/'identity.json').exists():record['identity_sha256']=digest(root/'identity.json')
            (root/'scheduled-build.json').write_text(json.dumps(record,indent=2)+'\n')
    return status


if __name__=='__main__':raise SystemExit(main())
