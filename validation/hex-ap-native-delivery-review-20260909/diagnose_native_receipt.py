"""Finite raw-only AP receipt diagnostic; no transport, FC, ROS node or model launch."""
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import audit_hex_flight as audit
from pymavlink import DFReader

root = Path('/root/wksim-hex-flight-ap-live-ap47v2-20260909-03/hex-ap-live-ap47v2-20260909-03')
result = audit.read(root/'result.json')
_, data, messages, _, _ = audit.decode(root, result)
phases = {p['phase']:p for p in result['task']['hex']['phases']}
start, end = [phases[p]['observed_monotonic_s'] for p in ('waypoint_accepted','land_accepted')]
targets = [(r,v) for r,v in data['/ap/cmd_gps_pose'] if start <= r['monotonic'] < end]
expected = []
for raw, target in targets:
    homes = [s for _,s in data['/ap/wksim/local_state_v1'] if s['time_boot_us'] == round(audit.stamp(target)*1e6)]
    home = homes[-1]
    lat = home['home_latitude_e7'] + int(3./0.011131884502145034)
    mid = (lat+home['home_latitude_e7'])/2e7
    lon = home['home_longitude_e7'] + int(2./(0.011131884502145034*math.cos(math.radians(mid))))
    lon = (lon+1800000000)%3600000000-1800000000
    assert target['latitude'] == lat/1e7 and target['longitude'] == lon/1e7
    expected.append(dict(dds_native_time_s=audit.stamp(target), received_monotonic_s=raw['monotonic'],
        latitude=target['latitude'], longitude=target['longitude'], altitude=target['altitude'],
        home_latitude_e7=home['home_latitude_e7'],home_longitude_e7=home['home_longitude_e7'],
        home_altitude_cm=home['home_altitude_cm'], expected_global_e7=[lat,lon],
        logger_float32_e7_cm=list(struct.unpack('<3f',struct.pack('<3f',int(target['latitude']*1e7),int(target['longitude']*1e7),int(target['altitude']*100))))))
counts = {kind:sum(m['message']['mavpackettype']==kind for m in messages) for kind in
          ('POSITION_TARGET_GLOBAL_INT','POSITION_TARGET_LOCAL_NED','EXTENDED_SYS_STATE')}
window_counts = {kind:sum(m['message']['mavpackettype']==kind and start<=m['monotonic']<end for m in messages)
                 for kind in ('POSITION_TARGET_GLOBAL_INT','POSITION_TARGET_LOCAL_NED','GLOBAL_POSITION_INT','LOCAL_POSITION_NED')}
reader = DFReader.DFReader_binary(str(root/'logs/00000001.BIN'))
guided = []
while True:
    row = reader.recv_msg()
    if row is None: break
    if row.get_type() == 'GUIP' and phases['waypoint_accepted']['native_boot_s']*1e6 <= row.TimeUS < phases['land_accepted']['native_boot_s']*1e6:
        guided.append(row.to_dict())
print(json.dumps(dict(run_id=result['run_id'], raw_sha256=audit.digest(root/'hex-native.jsonl'),
    bin_sha256=audit.digest(root/'logs/00000001.BIN'), waypoint_monotonic_window=[start,end],
    required_message_counts=counts, waypoint_message_counts=window_counts, dds_targets=len(targets),
    first_target=expected[0], last_target=expected[-1], bin_guided_rows=len(guided), first_guided=guided[:4],
    conclusion='Missing required target/landed telemetry; GUIP global setter stores float32 latE7/lonE7/altCm, not local metres'), indent=2))
