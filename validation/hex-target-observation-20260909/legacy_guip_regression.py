"""Execute the retained pre-fix audit against an explicitly synthetic receipt fixture."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools import audit_hex_flight as current
from validation.test_hex_target_observation import receipts_fixture

source=ROOT/'validation/hex-ap-stream-params-20260909/audit_hex_flight_proposed.py'
assert current.digest(source)=='bf05c8c1c6e2cdbefd04f99542e37af61d48283ad36b9cba364961ab5108beed'
spec=importlib.util.spec_from_file_location('retained_legacy_hex_audit',source)
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
data,messages,phases,guided=receipts_fixture()
# Isolate the old GUIP-unit assertion: let its preceding obsolete global-echo
# assertion pass with SYNTHETIC values. These are never appended to real evidence.
messages[1]['message'].update(lat_int=401540571,lon_int=1162593918,alt=52.97)
native=iter([SimpleNamespace(get_type=lambda:'GUIP',to_dict=lambda row=row:row) for row in guided])
reader=SimpleNamespace(recv_msg=lambda:next(native,None))
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary); (root/'fixture.BIN').touch()
    result=dict(stack='arducopter',raw_native_logs={'fixture.BIN':{'sha256':legacy.digest(root/'fixture.BIN'),'size':0}})
    with patch('pymavlink.DFReader.DFReader_binary',return_value=reader):
        try:
            legacy.native_delivery(root,result,data,messages,phases)
        except ValueError as error:
            assert str(error)=='AP GUIP/MAVLink target differs',str(error)
            old_failure=str(error)
        else:
            raise AssertionError('Old audit should reject source-correct global GUIP units')
new=current.ap_target_receipts(*receipts_fixture())
print(json.dumps(dict(legacy_failure=old_failure,new_source_correct_fixture=new,
    scope='Synthetic regression using actual source-derived representations; no new flight/receipt evidence'),indent=2))
