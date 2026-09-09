"""Mechanically apply the bounded candidate to a new copy; never edit the sealed source."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BASE = Path('/root/wksim-ap-clock-stop-OXQqdR/src')
PINS = {
    'SIM_JSON.cpp': '8dfcd44f9bb12da648825bff10ce2dabe33c780ec9a5b8d84a60e25e7f9e1f68',
    'SIM_GPS.cpp': 'e692b93506fe1c33757f15167a0a66387f853252781376dc7a71ace5dd814d26',
    'SIM_GPS_UBLOX.cpp': 'a12ddb2163f422040c26cee273c605c242a8591ca55207493a01288ad29dd6e7',
}
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    root = Path(sys.argv[1]).resolve()
    if root.parent != Path('/root') or not root.name.startswith('wksim-ap-gnss-'):
        raise ValueError('new owned /root/wksim-ap-gnss-* required')
    for name, pin in PINS.items():
        if sha(BASE / 'libraries/SITL' / name) != pin:
            raise ValueError('sealed source mismatch: ' + name)
    root.mkdir(exist_ok=False)
    subprocess.run(['cp', '-a', '--reflink=auto', str(BASE), str(root / 'src')], check=True)
    sitl = root / 'src/libraries/SITL'
    shutil.copyfile(HERE / 'SIM_WksimGNSS.h', sitl / 'SIM_WksimGNSS.h')
    def replace(name, old, new):
        path = sitl / name
        data = path.read_text()
        if data.count(old) != 1:
            raise ValueError('nonunique patch anchor: ' + name)
        path.write_text(data.replace(old, new))
    replace('SIM_JSON.cpp', '#include "SIM_JSON.h"', '#include "SIM_JSON.h"\n#include "SIM_WksimGNSS.h"')
    replace('SIM_JSON.cpp', '    const uint64_t received_bitmask = parse_sensors((const char *)(p1+1));',
            '    WksimGNSS::receive((const char *)(p1+1));\n'
            '    const uint64_t received_bitmask = parse_sensors((const char *)(p1+1));\n'
            '    WksimGNSS::timestamp(state.timestamp_s, state.no_lockstep, state.no_time_sync);')
    replace('SIM_GPS.cpp', '#include "SIM_GPS.h"', '#include "SIM_GPS.h"\n#include "SIM_WksimGNSS.h"')
    replace('SIM_GPS.cpp', '    instance{_instance}\n{\n}\n\nuint32_t GPS::device_baud',
            '    instance{_instance}\n{\n    WksimGNSS::sensor_created(_instance);\n}\n\nuint32_t GPS::device_baud')
    replace('SIM_GPS.cpp', '    backend->publish(&d);',
            '    if (WksimGNSS::sample(instance, d, AP_HAL::micros64())) {\n        backend->publish(&d);\n    }')
    replace('SIM_GPS.cpp', '    const double speedD = _sitl->state.speedD;\n    const uint32_t now_ms = AP_HAL::millis();',
            '    const double speedD = _sitl->state.speedD;\n'
            '    const uint32_t now_ms = WksimGNSS::model_ms(_sitl->state.timestamp_us);')
    replace('SIM_GPS.cpp', '    if ((now_ms - last_write_update_ms) < (uint32_t)(1000/params.hertz)) {',
            '    if (!is_equal(float(params.hertz.get()), 5.0f)) { WksimGNSS::fail("gps_rate_not_frozen"); }\n'
            '    if (now_ms % 200 != 0) {')
    replace('SIM_GPS.cpp', '    // the second GPS instance fails in a different way to the first;',
            '    const bool suppressed = WksimGNSS::suppress(instance);\n'
            '    if (suppressed) {\n'
            '        WksimGNSS::written(instance, p, size, 0, true);\n'
            '        return 0;\n'
            '    }\n'
            '    if (!is_zero(_sitl->gps[instance].byteloss) || !_sitl->gps[instance].enabled) {\n'
            '        WksimGNSS::fail("unexpected_gps_configuration");\n'
            '    }\n'
            '    // the second GPS instance fails in a different way to the first;')
    replace('SIM_GPS.cpp', '        return SerialDevice::write_to_autopilot(p, size);',
            '        const ssize_t result = SerialDevice::write_to_autopilot(p, size);\n'
            '        WksimGNSS::written(instance, p, size, result, false);\n'
            '        return result;')
    metadata = {'baseline': str(BASE), 'baseline_pins': PINS, 'root': str(root),
                'candidate': {p.name: sha(p) for p in [sitl / n for n in PINS] + [sitl / 'SIM_WksimGNSS.h']}}
    (root / 'identity.json').write_text(json.dumps(metadata, indent=2) + '\n')
    env = dict(os.environ)
    env['PATH'] = '/root/wksim-dds-VxM6Ni/src/Micro-XRCE-DDS-Gen/scripts:' + env['PATH']
    for name, cmd in [('configure', ['./waf', 'configure', '--board', 'sitl', '--enable-DDS', '--out', str(root / 'build')]),
                      ('build', ['./waf', 'copter', '-j4'])]:
        with (root / (name + '.log')).open('x') as log:
            result = subprocess.run(cmd, cwd=root / 'src', env=env, stdout=log, stderr=subprocess.STDOUT)
        print(name, result.returncode, flush=True)
        if result.returncode:
            return result.returncode
    metadata['binary_sha256'] = sha(root / 'build/sitl/bin/arducopter')
    (root / 'identity.json').write_text(json.dumps(metadata, indent=2) + '\n')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
