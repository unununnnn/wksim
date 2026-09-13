"""Build reviewable source copies and pins without editing the frozen runtime."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import difflib
import pprint
from unittest.mock import patch

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0,str(ROOT))
from tools import hex_launch_plan, hex_candidate, audit_hex_flight

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

original=(ROOT/'tools/hex_launch_plan.py').read_bytes()
text=original.decode()
old="ap = {('ARMING_SKIPCHK' if k == 'ARMING_CHECK' else k): (0 if k == 'ARMING_CHECK' else v)\n              for k, v in ap.items()}"
new="renamed = {'ARMING_CHECK': 'ARMING_SKIPCHK', 'SR0_POSITION': 'MAV1_POSITION',\n                   'SR0_EXTRA1': 'MAV1_EXTRA1', 'SR0_EXTRA3': 'MAV1_EXTRA3'}\n        ap = {renamed.get(k, k): (0 if k == 'ARMING_CHECK' else v) for k, v in ap.items()}"
assert text.count(old)==1
draft=text.replace(old,new).encode()
(OUT/'hex_launch_plan_proposed.py').write_bytes(draft)
plan_module=load(OUT/'hex_launch_plan_proposed.py','proposed_hex_plan')
plan=plan_module.launch_plan('arducopter')
assert plan_module.launch_plan()==hex_launch_plan.launch_plan()
assert plan_module.launch_plan('px4')==hex_launch_plan.launch_plan('px4')
candidate_old=(ROOT/'tools/hex_candidate.py').read_bytes()
candidate_new=candidate_old.replace(hex_candidate.AP47_PLAN_IDENTITY.encode(),plan['plan_identity'].encode())
(OUT/'hex_candidate_proposed.py').write_bytes(candidate_new)
with patch.dict(sys.modules,{'tools.hex_launch_plan':plan_module}):
    candidate_module=load(OUT/'hex_candidate_proposed.py','proposed_hex_candidate')
assert candidate_module.native_parameters('px4')==hex_candidate.native_parameters('px4')
inventory=json.loads((OUT/'native-parameter-inventory.json').read_text())
proposed=candidate_module.native_parameters('arducopter')
assert len(proposed)==33
for old_name,item in inventory['checks'].items():
    assert item['recorded_proposed_name'],old_name
    assert proposed[item['proposed_name']]==item['expected']
    if not old_name.startswith('SR0_'):
        assert item['recorded_proposed_name'][-1]['value']==item['expected']
assert {k:v for k,v in proposed.items() if k.startswith('MAV1_')}=={'MAV1_POSITION':10,'MAV1_EXTRA1':10,'MAV1_EXTRA3':5}
table=['| Existing planned name | Source-supported name | Required | Actual retained BIN |',
       '|---|---|---:|---:|']
table += [f"| {name} | {item['proposed_name']} | {item['expected']} | {item['recorded_proposed_name'][-1]['value']} |"
          for name,item in inventory['checks'].items()]
(OUT/'all-33-parameters.md').write_text('\n'.join(table)+'\n')
protocol_old=(ROOT/'Simulator/wksim_runtime/hex-flight-ap47-v1.json').read_bytes()
protocol_new=protocol_old.replace(b'wksim.hex-flight-ap47-protocol.v1',b'wksim.hex-flight-ap47-protocol.v2').replace(
    hex_candidate.AP47_PLAN_IDENTITY.encode(),plan['plan_identity'].encode())
(OUT/'hex-flight-ap47-v2.json').write_bytes(protocol_new)
before=json.loads(protocol_old); after=json.loads(protocol_new)
assert {k:v for k,v in before.items() if k not in ('schema','plan_identity')}=={k:v for k,v in after.items() if k not in ('schema','plan_identity')}
task_old=(ROOT/'Simulator/wksim_runtime/hex_task.py').read_bytes()
task_new=task_old.replace(b'hex-flight-ap47-v1.json',b'hex-flight-ap47-v2.json').replace(
    sha(protocol_old).encode(),sha(protocol_new).encode())
(OUT/'hex_task_proposed.py').write_bytes(task_new)
changes=[('tools/hex_launch_plan.py',original,draft),('tools/hex_candidate.py',candidate_old,candidate_new),
         ('Simulator/wksim_runtime/hex_task.py',task_old,task_new)]
audit_old=(ROOT/'tools/audit_hex_flight.py').read_bytes()
audit_text=audit_old.decode()
pairs={name:(pair,) for name,pair in audit_hex_flight.LEGACY_PX4_SOURCE_PAIRS.items()}
for name,revised in [('tools/hex_launch_plan.py',sha(draft)),('tools/hex_candidate.py',sha(candidate_new))]:
    historical,current=pairs[name][0]
    pairs[name]+=((historical,revised),(current,revised))
start=audit_text.index('LEGACY_PX4_SOURCE_PAIRS = ')
end=audit_text.index('\nPUBLIC = ',start)
audit_text=audit_text[:start]+'LEGACY_PX4_SOURCE_PAIRS = '+pprint.pformat(pairs,sort_dicts=False)+audit_text[end:]
audit_text=audit_text.replace('LEGACY_PX4_SOURCE_PAIRS.get(name) == (archived, current)',
                              '(archived, current) in LEGACY_PX4_SOURCE_PAIRS.get(name, ())')
audit_new=audit_text.encode()
(OUT/'audit_hex_flight_proposed.py').write_bytes(audit_new)
audit_module=load(OUT/'audit_hex_flight_proposed.py','proposed_hex_audit')
for name,allowed in pairs.items():
    for old,current in allowed:
        assert audit_module.compatible_source('px4',name,old,current)
        assert not audit_module.compatible_source('px4',name,old,'f'*64)
        assert not audit_module.compatible_source('px4',name,'f'*64,current)
        assert not audit_module.compatible_source('arducopter',name,old,current)
changes.append(('tools/audit_hex_flight.py',audit_old,audit_new))
(OUT/'proposed-runtime.patch').write_text(''.join(''.join(difflib.unified_diff(a.decode().splitlines(True),b.decode().splitlines(True),fromfile='a/'+n,tofile='b/'+n)) for n,a,b in changes))
summary=dict(scope='Proposal only: frozen production files untouched; no DDS or native execution',
    ap_plan_identity=plan['plan_identity'],ap_protocol_sha256=sha(protocol_new),
    preserve_ap47v1_sha256=sha(protocol_old),legacy_px4_plan_identity=hex_launch_plan.launch_plan()['plan_identity'],
    proposed_source_sha256={n:sha(b) for n,a,b in changes},
    full_legacy_plan_equal=True,px4_native_parameters_equal=77,all_proposed_ap_names_in_actual_BIN=33,
    matching_current_values=30,renamed_stream_rates={'MAV1_POSITION':10,'MAV1_EXTRA1':10,'MAV1_EXTRA3':5},
    explicit_compatibility_pairs={name:list(allowed) for name,allowed in pairs.items()},
    compatibility_requirement='Add explicit old5576/current9e2a -> proposed plan pair and old337e/currentae6e -> proposed candidate pair; keep adapter exact pair. Re-audit both PX4 lifetimes after parent release.')
(OUT/'proposal-result.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
