"""Verify explicit patched-source identity and offline guards, without admitting a runtime."""
import datetime
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from build_attitude_control_candidate import (BASE, BASE_SHA, MSGS, NATIVE, NATIVE_SHA,
    OVERLAYS, PACKAGE, PATCH_SHA, REPO, apply, base_check, digest, hashes, native_check)


def native_guards(directory):
    """Exact function bodies with recording platform stubs; not a firmware execution."""
    def body(relative, signature):
        text = (NATIVE/'src'/relative).read_text()
        start = text.index(signature)
        end = text.index('\n}', start) + 2
        return text[start:end]
    dds = 'libraries/AP_DDS/AP_DDS_ExternalControl.cpp'
    copter = 'ArduCopter/AP_ExternalControl_Copter.cpp'
    functions = [body(dds, 'bool AP_DDS_External_Control::handle_attitude_control('),
        body(copter, 'bool AP_ExternalControl_Copter::set_attitude_and_thrust('),
        body(copter, 'bool AP_ExternalControl_Copter::ready_for_external_control(')]
    # Quaternion methods and Guided/platform objects below are explicitly stubs. These tests
    # exercise the compiled handler branches, not AP_Math, GUID_OPTIONS storage, or set_angle.
    prefix = r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include "ardupilot_msgs/msg/WksimAttitudeTarget.h"
struct Quaternion {
    float q1, q2, q3, q4;
    Quaternion(float w=1, float x=0, float y=0, float z=0):q1(w),q2(x),q3(y),q4(z){}
    bool is_unit_length() const { return fabsf(q1*q1+q2*q2+q3*q3+q4*q4-1.0f)<1.0e-3f; }
    void normalize() { float n=sqrtf(q1*q1+q2*q2+q3*q3+q4*q4); q1/=n;q2/=n;q3/=n;q4/=n; }
};
struct Vector3f { float x,y,z; Vector3f(float a,float b,float c):x(a),y(b),z(c){} };
struct Guided {
    bool option=false; int calls=0; Quaternion q; float thrust=-1;
    bool set_attitude_target_provides_thrust() const { return option; }
    void set_angle(const Quaternion& v,const Vector3f& rates,float u,bool use_thrust) {
        assert(rates.x==0 && rates.y==0 && rates.z==0 && use_thrust); ++calls; q=v; thrust=u;
    }
};
struct Flightmode { bool guided=true; bool in_guided_mode() const {return guided;} } flightmode;
struct Motors { bool is_armed=true; bool armed() const {return is_armed;} } motors;
struct Copter { Guided mode_guided; Flightmode* flightmode; Motors* motors; } copter{{},&flightmode,&motors};
class AP_ExternalControl_Copter {
public: bool ready_for_external_control(); bool set_attitude_and_thrust(const Quaternion&,float);
};
AP_ExternalControl_Copter external;
namespace AP { AP_ExternalControl_Copter* ptr=&external; AP_ExternalControl_Copter* externalcontrol(){return ptr;} }
namespace AP_HAL { uint64_t now=1000000; uint64_t micros64(){return now;} }
constexpr const char* MAP_FRAME="map";
class AP_DDS_External_Control {
public: static bool handle_attitude_control(const ardupilot_msgs_msg_WksimAttitudeTarget&);
};
'''
    checks = r'''
int main() {
    using Target=ardupilot_msgs_msg_WksimAttitudeTarget;
    Target good{}; strcpy(good.header.frame_id,"map"); good.header.stamp.sec=1;
    good.orientation.w=1; good.normalized_thrust=.5f;
    int rejected=0;
    auto reject=[&](const Target& bad) {int n=copter.mode_guided.calls;
        assert(!AP_DDS_External_Control::handle_attitude_control(bad));
        assert(copter.mode_guided.calls==n); ++rejected;};
    reject(good); // explicit thrust option remains closed
    copter.mode_guided.option=true;
    for(float u: {0.0f, .5f, 1.0f}) {
        good.normalized_thrust=u;
        assert(AP_DDS_External_Control::handle_attitude_control(good));
        assert(copter.mode_guided.thrust==u);
        assert(fabsf(copter.mode_guided.q.q1-sqrtf(.5f))<1e-6f);
        assert(fabsf(copter.mode_guided.q.q4-sqrtf(.5f))<1e-6f);
    }
    good.normalized_thrust=.5f;
    AP::ptr=nullptr; reject(good); AP::ptr=&external;
    flightmode.guided=false; reject(good); flightmode.guided=true;
    motors.is_armed=false; reject(good); motors.is_armed=true;
    copter.mode_guided.option=false; reject(good); copter.mode_guided.option=true;
    Target bad=good; strcpy(bad.header.frame_id,"odom"); reject(bad);
    bad=good; bad.header.stamp.sec=-1; reject(bad);
    bad=good; bad.header.stamp.sec=0; reject(bad);
    bad=good; bad.header.stamp.nanosec=1000000000U; reject(bad);
    bad=good; bad.header.stamp.nanosec=1000; reject(bad); // future by 1 us
    bad=good; bad.header.stamp.sec=0; bad.header.stamp.nanosec=749999000; reject(bad);
    bad.header.stamp.nanosec=750000000; // exactly 250 ms accepted
    assert(AP_DDS_External_Control::handle_attitude_control(bad));
    for(double value: {0.0, 2.0, 1e300, std::numeric_limits<double>::quiet_NaN(),
                       std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity()}) {
        bad=good; bad.orientation.w=value; reject(bad);
    }
    for(int axis=0;axis<4;axis++) {
        bad=good; double* fields[]={&bad.orientation.w,&bad.orientation.x,&bad.orientation.y,&bad.orientation.z};
        *fields[axis]=std::numeric_limits<double>::quiet_NaN(); reject(bad);
    }
    for(double norm: {.9989,1.0011}) {bad=good;bad.orientation.w=sqrt(norm);reject(bad);}
    for(float u: {-.001f,1.001f,std::numeric_limits<float>::quiet_NaN(),
                  std::numeric_limits<float>::infinity(),-std::numeric_limits<float>::infinity()}) {
        bad=good;bad.normalized_thrust=u;reject(bad);
    }
    // Bypass DDS to check the actual Copter setter's own boundary.
    auto setter_reject=[&](Quaternion q,float u) {int n=copter.mode_guided.calls;
        assert(!external.set_attitude_and_thrust(q,u)); assert(copter.mode_guided.calls==n); ++rejected;};
    setter_reject(Quaternion(0,0,0,0),.5f); setter_reject(Quaternion(2,0,0,0),.5f);
    for(float value: {std::numeric_limits<float>::quiet_NaN(),std::numeric_limits<float>::infinity()}) {
        setter_reject(Quaternion(value,0,0,0),.5f); setter_reject(Quaternion(1,0,0,0),value);
    }
    setter_reject(Quaternion(),-.001f);setter_reject(Quaternion(),1.001f);
    printf("PASS %d atomic rejects; endpoints, ENU/NED basis, 250 ms exact boundary. Recording stubs only.\n",rejected);
}
'''
    source = directory/'native-guards.cpp'
    source.write_text('#include <cstdio>\n#include <initializer_list>\n'+prefix+'\n'+'\n\n'.join(functions)+'\n'+checks)
    generated = NATIVE/'build/sitl/libraries/AP_DDS/generated'
    command = ['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', str(source),
        '-I'+str(generated), '-I'+str(NATIVE/'src/modules/Micro-CDR/include'),
        '-I'+str(NATIVE/'build/sitl/modules/Micro-CDR/include'), '-o', str(directory/'native-guards')]
    with (directory/'native-compile.log').open('w') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    with (directory/'native-guards.log').open('w') as log:
        subprocess.run([str(directory/'native-guards')], stdout=log, stderr=subprocess.STDOUT, check=True)
    return dict(source_hashes={p: digest(NATIVE/'src'/p) for p in (dds,copter)},
        source_functions=['handle_attitude_control', 'set_attitude_and_thrust', 'ready_for_external_control'],
        limitations='Generated message struct and exact candidate function bodies; Quaternion math, clock, Guided option accessor, motors and set_angle are recording stubs. No firmware scheduler, GUID_OPTIONS storage or flight.')


def main():
    root = Path(sys.argv[1]).resolve(strict=True)
    assert root.parent == Path('/root') and root.name.startswith('wksim-attitude-control-')
    manifest = root/'attitude-control-build.json'
    assert digest(manifest) == sys.argv[2], 'Supply the explicit build manifest SHA256'
    value = json.loads(manifest.read_text())
    assert value['root'] == str(root) and value['base_manifest_sha256'] == BASE_SHA
    assert value['patch_sha256'] == PATCH_SHA and digest(root/'control.patch') == PATCH_SHA
    assert value['native_manifest_sha256'] == NATIVE_SHA
    base_check()
    native = native_check()
    assert hashes(BASE/'src/prometheus_control') == value['base_package_hashes']
    assert hashes(root/'tree'/PACKAGE) == value['patched_package_hashes']
    assert hashes(Path(value['package'])) == value['installed_python_hashes']
    assert hashes(root/'tree'/PACKAGE/'prometheus_control') == value['installed_python_hashes']
    assert hashes(REPO/PACKAGE) == value['original_repository_package_hashes']
    assert digest(root/'build.log') == value['build_log_sha256']
    assert digest(root/'build.sh') == value['build_shell_sha256']
    assert (root/'build.exit').read_text().strip() == '0'
    evidence = root/'verification'
    evidence.mkdir(exist_ok=False)
    reverse_tree = evidence/'reverse-proof'
    shutil.copytree(root/'tree', reverse_tree)
    apply(reverse_tree, root/'control.patch', reverse=True)
    assert hashes(reverse_tree/PACKAGE) == value['base_package_hashes']
    # Native source identity is tied to the previously sealed build artifacts.
    source_manifest = json.loads((NATIVE/'attitude-source.json').read_text())
    assert digest(NATIVE/'attitude-source.json') == native['source_manifest_sha256']
    sys.path.insert(0, str(REPO))
    from Simulator.wksim_runtime.build_identity import source_snapshot
    assert source_snapshot(NATIVE/'src', commit=source_manifest['commit']) == source_manifest['source']
    guards = native_guards(evidence)
    # Build a fresh environment from the exact recorded overlays; the test asserts every import path.
    script = 'set -eo pipefail\n'+''.join('source '+shlex.quote(str(p))+'\n' for p in OVERLAYS)
    script += 'source '+shlex.quote(str(root/'install/local_setup.bash'))+'\n'
    script += 'export PYTHONDONTWRITEBYTECODE=1\n'
    script += shlex.join(['python3', '-B', str(REPO/'validation/test_attitude_control_candidate.py'), str(root)])+'\n'
    (evidence/'verify.sh').write_text(script)
    with (evidence/'adapter-tests.log').open('w') as log:
        subprocess.run(['bash', str(evidence/'verify.sh')], stdout=log, stderr=subprocess.STDOUT, check=True)
    assert json.loads((root/'adapter-results.json').read_text())['successful']
    shutil.copy2(root/'adapter-results.json', evidence/'adapter-results.json')
    base_check()
    assert hashes(REPO/PACKAGE) == value['original_repository_package_hashes']
    assert hashes(root/'tree'/PACKAGE) == value['patched_package_hashes']
    assert hashes(Path(value['package'])) == value['installed_python_hashes']
    result = dict(schema_version=1, status='built-offline-guards-verified-not-admitted',
        completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        root=str(root), build_manifest_sha256=digest(manifest), native_guards=guards,
        installed_import_path=value['package'], messages_overlay=str(MSGS),
        evidence_hashes=hashes(evidence),
        tool_hashes={p: digest(REPO/p) for p in ('tools/build_attitude_control_candidate.py',
            'tools/verify_attitude_control_candidate.py', 'validation/test_attitude_control_candidate.py',
            'validation/test_prometheus_native.py', 'validation/test_ap_pv_adapter.py')},
        reverse_patch_restored_sealed_base=True, original_repository_unchanged=True,
        production_admitted=False, flown=False, ros_nodes_started=False)
    final = root/'attitude-control-verification.json'
    final.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps(dict(manifest=str(final), sha256=digest(final), status=result['status'])))


if __name__ == '__main__':
    main()
