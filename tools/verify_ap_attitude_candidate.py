"""Verify built candidate and ROS/native CDR compatibility; never starts ROS nodes."""
import datetime
import json
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.build_identity import source_snapshot, sha


def main():
    root = Path(sys.argv[1]).resolve(strict=True)
    assert root.parent == Path('/root') and root.name.startswith('wksim-ap-attitude-')
    source_manifest = root/'attitude-source.json'
    manifest = json.loads(source_manifest.read_text())
    assert source_snapshot(root/'src', commit=manifest['commit']) == manifest['source']
    assert sha((root/'candidate.patch').read_bytes()) == manifest['patch_sha256']
    assert sha((root/'attitude-extra.hwdef').read_bytes()) == manifest['extra_hwdef_sha256']
    assert (root/'native-build.exit').read_text().strip() == '0'
    assert (root/'messages-build.exit').read_text().strip() == '0'
    msgs = Path((root/'messages-root.txt').read_text().strip()).resolve(strict=True)
    assert msgs.parent == Path('/root') and msgs.name.startswith('wksim-ap-attitude-msgs-')
    from ardupilot_msgs.msg import WksimAttitudeTarget, WksimState
    from rclpy.serialization import serialize_message, deserialize_message
    import ardupilot_msgs
    assert Path(ardupilot_msgs.__file__).resolve().is_relative_to(msgs)
    evidence = root/'codec'
    evidence.mkdir(exist_ok=False)
    c_source = evidence/'codec.c'
    c_source.write_text(r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <ucdr/microcdr.h>
#include "ardupilot_msgs/msg/WksimAttitudeTarget.h"
int main(int argc, char **argv) {
    assert(argc == 3);
    unsigned char bytes[512] = {0};
    FILE *input = fopen(argv[1], "rb"); assert(input);
    size_t count = fread(bytes, 1, sizeof(bytes), input); fclose(input);
    assert(count > 4 && bytes[0] == 0 && bytes[1] == 1);
    ucdrBuffer reader; ucdr_init_buffer(&reader, bytes + 4, count - 4);
    ardupilot_msgs_msg_WksimAttitudeTarget msg = {0};
    assert(ardupilot_msgs_msg_WksimAttitudeTarget_deserialize_topic(&reader, &msg));
    assert(msg.header.stamp.sec == 123 && msg.header.stamp.nanosec == 456789);
    assert(strcmp(msg.header.frame_id, "map") == 0);
    assert(msg.orientation.x == 0.5 && msg.orientation.y == -0.5);
    assert(msg.orientation.z == 0.5 && msg.orientation.w == 0.5);
    assert(msg.normalized_thrust == 0.375f);
    unsigned char output[512] = {0,1,0,0};
    ucdrBuffer writer; ucdr_init_buffer(&writer, output + 4, sizeof(output) - 4);
    assert(ardupilot_msgs_msg_WksimAttitudeTarget_serialize_topic(&writer, &msg));
    FILE *out = fopen(argv[2], "wb"); assert(out);
    fwrite(output, 1, 4 + ucdr_buffer_length(&writer), out); fclose(out);
    return 0;
}
''')
    generated = root/'build/sitl/libraries/AP_DDS/generated'
    micro = root/'src/modules/Micro-CDR'
    command = ['gcc', '-std=c99', '-o', str(evidence/'codec'), str(c_source),
        '-I'+str(generated), '-I'+str(micro/'include'), '-I'+str(micro/'src/c'),
        '-I'+str(root/'build/sitl/modules/Micro-CDR/include')]
    command += [str(generated/p) for p in ['ardupilot_msgs/msg/WksimAttitudeTarget.c',
        'std_msgs/msg/Header.c', 'builtin_interfaces/msg/Time.c', 'geometry_msgs/msg/Quaternion.c']]
    command += [str(p) for p in sorted((micro/'src').rglob('*.c'))]
    with (evidence/'compile.log').open('w') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    msg = WksimAttitudeTarget()
    msg.header.stamp.sec, msg.header.stamp.nanosec = 123, 456789
    msg.header.frame_id = 'map'
    msg.orientation.x, msg.orientation.y = 0.5, -0.5
    msg.orientation.z, msg.orientation.w = 0.5, 0.5
    msg.normalized_thrust = 0.375
    (evidence/'ros.cdr').write_bytes(serialize_message(msg))
    subprocess.run([str(evidence/'codec'), str(evidence/'ros.cdr'), str(evidence/'native.cdr')], check=True)
    assert deserialize_message((evidence/'native.cdr').read_bytes(), WksimAttitudeTarget) == msg
    assert deserialize_message(serialize_message(WksimState()), WksimState) == WksimState()
    artifacts = {str(p.relative_to(root)): sha(p.read_bytes()) for p in [
        root/'build/sitl/bin/arducopter', root/'configure.log', root/'build.log',
        root/'messages-build.log', root/'attitude-extra.hwdef', root/'candidate.patch',
        root/'build-ap-attitude-candidate.sh']}
    artifacts.update({str(p.relative_to(root)): sha(p.read_bytes()) for p in sorted(evidence.rglob('*')) if p.is_file()})
    generated_hashes = {str(p.relative_to(generated)): sha(p.read_bytes()) for p in sorted(generated.rglob('*')) if p.is_file()}
    overlay_hashes = {str(p.relative_to(msgs)): sha(p.read_bytes()) for p in sorted(msgs.rglob('*')) if p.is_file()}
    result = dict(schema_version=1, status='built-codec-verified-not-admitted',
        completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        candidate_root=str(root), messages_root=str(msgs),
        source_manifest_sha256=sha(source_manifest.read_bytes()), artifacts=artifacts,
        generated_hashes=generated_hashes, overlay_hashes=overlay_hashes,
        verifier_sha256=sha(Path(__file__).read_bytes()), native_build_exit=0, messages_build_exit=0,
        codec='ROS serialize -> native generated deserialize/serialize -> ROS deserialize passed',
        production_admitted=False, flown=False)
    (root/'attitude-build.json').write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps(dict(manifest=str(root/'attitude-build.json'), sha256=sha((root/'attitude-build.json').read_bytes()), **{k: result[k] for k in ('status','candidate_root','messages_root')})))


if __name__ == '__main__':
    main()
