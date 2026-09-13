"""Read retained AP BIN parameters and pinned source registrations; no native run."""
import hashlib
import json
from pathlib import Path
from pymavlink import DFReader

OUT = Path(__file__).resolve().parent
RUN = Path('/root/wksim-hex-flight-ap-live-ap47-20260909-02/hex-ap-live-ap47-20260909-02')
SOURCE = Path('/root/wksim-ap-clock-stop-OXQqdR/src')
result = json.loads((RUN/'result.json').read_text())
bin_path = RUN/'logs/00000001.BIN'
decoder = DFReader.DFReader_binary(str(bin_path))
params = {}
while True:
    item = decoder.recv_match(type='PARM')
    if item is None:
        break
    params.setdefault(item.Name, []).append(dict(value=item.Value, time_us=item.TimeUS))
mapping = {'SR0_POSITION':'MAV1_POSITION','SR0_EXTRA1':'MAV1_EXTRA1','SR0_EXTRA3':'MAV1_EXTRA3'}
checks = {}
for name, expected in result['admission']['parameters'].items():
    proposed = mapping.get(name,name)
    checks[name] = dict(proposed_name=proposed,expected=expected,
        recorded_old_name=params.get(name),recorded_proposed_name=params.get(proposed))
files = ['ArduCopter/Parameters.cpp','libraries/GCS_MAVLink/GCS.cpp',
         'libraries/GCS_MAVLink/GCS_MAVLink_Parameters.cpp','libraries/AP_Arming/AP_Arming.cpp',
         'libraries/AP_Motors/AP_MotorsMulticopter.cpp','libraries/SRV_Channel/SRV_Channels.cpp',
         'libraries/SRV_Channel/SRV_Channel.cpp','libraries/AP_DDS/AP_DDS_Client.cpp',
         'libraries/AP_Logger/AP_Logger.cpp','libraries/SITL/SITL.cpp','libraries/AP_Vehicle/AP_Vehicle.cpp']
source = {}
for name in files:
    path = SOURCE/name
    if not path.exists():
        source[name] = dict(missing=True)
        continue
    lines = path.read_text().splitlines()
    source[name] = dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        registrations=[dict(line=i+1,text=line) for i,line in enumerate(lines)
        if any(token in line for token in ('AP_GROUPINFO','AP_SUBGROUP','GOBJECT(', 'GOBJECTVARPTR(', 'GSCALAR(', 'SR0 through'))])
data = dict(scope='Read-only retained native BIN PARM plus fixed source registrations; not DDS readback',
            run_id=result['run_id'],bin_sha256=hashlib.sha256(bin_path.read_bytes()).hexdigest(),
            native_parameter_names=len(params),checks=checks,source=source)
(OUT/'native-parameter-inventory.json').write_text(json.dumps(data,indent=2)+'\n')
print(json.dumps(dict(native_names=len(params),planned=len(checks),
                     proposed_missing=[k for k,v in checks.items() if not v['recorded_proposed_name']],
                     observations={k:v for k,v in checks.items() if k.startswith('SR')})))
